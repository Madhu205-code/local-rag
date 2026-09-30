from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from config import CHROMA_DIR, COLLECTION_NAME, DATA_DIR, HOME, MANIFEST_PATH

DATA_DIR.mkdir(parents=True, exist_ok=True)

_client: chromadb.ClientAPI | None = None


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )
    return _client


def get_collection(name: str = COLLECTION_NAME):
    return get_client().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine", "description": "personal local file index"},
    )


def path_key(path: Path) -> str:
    return Path(os.path.normpath(str(path.resolve()))).as_posix().lower()


def display_path(path: Path) -> str:
    resolved = Path(os.path.normpath(str(path.resolve())))
    try:
        return resolved.relative_to(HOME).as_posix()
    except ValueError:
        return resolved.as_posix()


def chunk_id(key: str, index: int) -> str:
    return f"{key}#{index}"


def load_manifest() -> dict[str, dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_manifest(manifest: dict[str, dict[str, Any]]) -> None:
    tmp_path = MANIFEST_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=1, sort_keys=True)
    os.replace(tmp_path, MANIFEST_PATH)


def delete_document(collection, key: str) -> int:
    existing = collection.get(where={"path_key": key}, include=[])
    ids = existing.get("ids", [])
    if ids:
        collection.delete(ids=ids)
    return len(ids)


def collection_count(collection) -> int:
    return int(collection.count())
