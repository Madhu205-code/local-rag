from __future__ import annotations

import fnmatch
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from chunker import chunk_text
from config import (
    CODE_EXTENSIONS,
    DEFAULT_ROOTS,
    EXCLUDED_DIR_NAMES,
    INDEXABLE_EXTENSIONS,
    MAX_FILE_MB,
    MIN_CHUNK_CHARS,
    SKIP_FILENAMES,
)
from loaders import is_probably_binary, load_sections
from store import (
    chunk_id,
    delete_document,
    display_path,
    get_collection,
    load_manifest,
    path_key,
    save_manifest,
)

console = Console()


@dataclass
class IndexStats:
    scanned: int = 0
    indexed: int = 0
    updated: int = 0
    skipped: int = 0
    removed_files: int = 0
    removed_chunks: int = 0
    failed: int = 0
    chunks: int = 0
    errors: list[str] = field(default_factory=list)

    def as_line(self) -> str:
        return (
            f"scanned {self.scanned} | new {self.indexed} | updated {self.updated} | "
            f"unchanged {self.skipped} | deleted {self.removed_files} ({self.removed_chunks} chunks) | "
            f"failed {self.failed} | chunks written {self.chunks}"
        )


def _is_excluded_dir(name: str) -> bool:
    return name.lower() in EXCLUDED_DIR_NAMES


def _should_index(path: Path) -> bool:
    if path.name.lower() in SKIP_FILENAMES:
        return False
    name_lower = path.name.lower()
    if path.suffix.lower() not in INDEXABLE_EXTENSIONS:
        if name_lower in {".gitignore", ".env", ".editorconfig", "dockerfile", "makefile"}:
            return True
        return False
    if not path.is_file():
        return False
    return path.stat().st_size <= MAX_FILE_MB * 1024 * 1024


def iter_files(roots: Iterable[Path], include_hidden: bool = False) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        root = Path(root)
        if root.is_file():
            if _should_index(root):
                found.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=lambda e: None):
            here = Path(dirpath)
            if not include_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            else:
                dirnames[:] = [
                    d for d in dirnames if not d.startswith(".") or d in {"Documents", "Desktop", "Downloads"}
                ]
            dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d) and not _is_junction(here / d)]
            for filename in filenames:
                if not include_hidden and filename.startswith("."):
                    if filename.lower() not in {".gitignore", ".env", ".editorconfig"}:
                        continue
                candidate = here / filename
                if _should_index(candidate):
                    found.append(candidate)
    return found


def _is_junction(path: Path) -> bool:
    try:
        return path.is_symlink() or (path.exists() and path.is_junction())
    except OSError:
        return False


def index(
    roots: list[Path] | None = None,
    force: bool = False,
    include_hidden: bool = False,
    limit: int | None = None,
    workers: int = 4,
) -> IndexStats:
    roots = [Path(r) for r in (roots or DEFAULT_ROOTS)]
    roots = [r for r in roots if r.exists()]
    if not roots:
        console.print("[red]No valid scan roots.[/red]")
        return IndexStats()

    collection = get_collection()
    manifest = load_manifest()
    stats = IndexStats()

    files = iter_files(roots, include_hidden=include_hidden)
    files.sort(key=lambda p: str(p).lower())
    if limit:
        files = files[:limit]

    console.print(
        f"[cyan]Scanning[/cyan] {len(roots)} root(s), {len(files)} indexable files found."
    )

    seen_keys: set[str] = set()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("indexing", total=len(files))
        for path in files:
            key = path_key(path)
            seen_keys.add(key)
            stats.scanned += 1
            try:
                stat = path.stat()
            except OSError:
                stats.failed += 1
                progress.advance(task)
                continue

            record = manifest.get(key)
            unchanged = (
                record is not None
                and record.get("size") == stat.st_size
                and abs(float(record.get("mtime", 0)) - stat.st_mtime) < 1e-6
            )
            if unchanged and not force:
                stats.skipped += 1
                progress.advance(task)
                continue

            if is_probably_binary(path):
                stats.skipped += 1
                progress.advance(task)
                continue

            try:
                title, sections = load_sections(path)
            except Exception as exc:
                stats.failed += 1
                stats.errors.append(f"{path}: {type(exc).__name__}: {exc}")
                progress.advance(task)
                continue

            is_code = path.suffix.lower() in CODE_EXTENSIONS
            ids: list[str] = []
            documents: list[str] = []
            metadatas: list[dict] = []
            headers: list[str] = []
            counter = 0

            for header, body in sections:
                body = body.strip()
                if len(body) < MIN_CHUNK_CHARS:
                    continue
                for piece in chunk_text(body, is_code=is_code):
                    piece = piece.strip()
                    if len(piece) < MIN_CHUNK_CHARS:
                        continue
                    ids.append(chunk_id(key, counter))
                    documents.append(
                        f"FILE: {path.name}\nTITLE: {title}\nSECTION: {header}\n\n{piece}"
                    )
                    metadatas.append(
                        {
                            "path_key": key,
                            "path": str(path),
                            "rel": display_path(path),
                            "name": path.name,
                            "ext": path.suffix.lower(),
                            "title": title,
                            "header": header,
                            "chunk": counter,
                            "size": int(stat.st_size),
                            "mtime": float(stat.st_mtime),
                            "indexed_at": time.time(),
                        }
                    )
                    headers.append(header)
                    counter += 1

            delete_document(collection, key)
            if ids:
                collection.add(ids=ids, documents=documents, metadatas=metadatas)

            manifest[key] = {
                "size": int(stat.st_size),
                "mtime": float(stat.st_mtime),
                "chunks": counter,
                "headers": headers[:40],
                "title": title,
            }
            stats.chunks += counter
            if record is None:
                stats.indexed += 1
            else:
                stats.updated += 1
            progress.advance(task)

        if not force:
            prefixes = tuple(_root_prefix(r) for r in roots)
            stale = [k for k in manifest if k not in seen_keys and k.startswith(prefixes)]
            for key in stale:
                stats.removed_chunks += delete_document(collection, key)
                stats.removed_files += 1
                manifest.pop(key, None)

    save_manifest(manifest)
    console.print(f"[green]{stats.as_line()}[/green]")
    for error in stats.errors[:15]:
        console.print(f"  [yellow]{error}[/yellow]")
    if len(stats.errors) > 15:
        console.print(f"  [dim]... and {len(stats.errors) - 15} more[/dim]")
    return stats


def _root_prefix(root: Path) -> str:
    return path_key(root).rstrip("/") + "/"


def matches_filters(path: str, include: str = "", exclude: str = "") -> bool:
    lowered = path.lower()
    if include and not fnmatch.fnmatch(lowered, f"*{include.lower()}*"):
        return False
    if exclude and fnmatch.fnmatch(lowered, f"*{exclude.lower()}*"):
        return False
    return True
