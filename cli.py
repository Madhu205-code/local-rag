from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

import banner
import config
from config import DATA_DIR, DEFAULT_ROOTS, LLM_MODEL
from engine import Engine

console = Console()


def _paths(args: argparse.Namespace) -> list[Path]:
    if args.root:
        return [Path(r).expanduser() for r in args.root]
    return list(DEFAULT_ROOTS)


def _subtitle(engine: Engine | None = None) -> str:
    if engine is None:
        return ""
    summary = engine.summary()
    domain = "clinical" if summary.get("domain") == "medical" else "general"
    return (
        f"{summary['model']}  |  {summary['chunks']:,} chunks  |  "
        f"{summary['files']:,} files  |  {domain}"
    )


def _print_sources(hits, show_text: bool = True) -> None:
    if not hits:
        return
    console.print()
    banner.header(console, f"sources  ({len(hits)})", "score")
    console.print(banner.sources_table(hits))
    if show_text:
        for number, hit in enumerate(hits, start=1):
            console.print(
                Panel(
                    hit.text.strip(),
                    title=f" [bold][{number}][/bold] {hit.rel}  -  {hit.header} ",
                    title_align="left",
                    border_style=banner.BROWN_DIM,
                    padding=(0, 2),
                )
            )


def cmd_index(args: argparse.Namespace) -> int:
    from indexer import index

    roots = _paths(args)
    banner.print_banner(console, "building the index")
    for root in roots:
        banner.dim(console, f"root  {root}")
    stats = index(
        roots=roots,
        force=args.force,
        include_hidden=args.hidden,
        limit=args.limit,
    )
    console.print()
    banner.ok(console, stats.as_line())
    for error in stats.errors[:10]:
        console.print(f"    [yellow]{error}[/yellow]")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    engine = Engine(model=args.model, domain=getattr(args, "domain", "general"))
    with console.status(f"[{banner.MUTED}]searching {engine.count:,} chunks...", spinner="dots"):
        hits = engine.search(
            args.query,
            k=args.k,
            include=args.include,
            exclude=args.exclude,
            extensions=args.ext or None,
        )
    if not hits:
        banner.warn(console, "no matches")
        return 0
    _print_sources(hits, show_text=not args.no_text)
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    engine = Engine(model=args.model, domain=getattr(args, "domain", "general"))
    if engine.count == 0:
        banner.fail(console, "index is empty. run: rag index")
        return 1

    question = args.question
    console.print()
    banner.header(console, "question", engine.model)
    console.print(f"  [bold white]{question}[/bold white]")
    console.print()

    with console.status(f"[{banner.MUTED}]retrieving...", spinner="dots"):
        hits = engine.search(
            question, k=args.k, include=args.include, exclude=args.exclude,
            extensions=args.ext or None,
        )
    banner.dim(console, f"{len(hits)} sources  |  {engine.count:,} chunks searched")

    if args.stream:
        with console.status(f"[{banner.BROWN_DIM}]{engine.model} is thinking...", spinner="dots"):
            for piece in engine.stream_answer(
                question, k=args.k, history=[], temperature=args.temperature,
                context_tokens=args.context, include=args.include, exclude=args.exclude,
                extensions=args.ext or None,
            ):
                sys.stdout.write(piece)
                sys.stdout.flush()
        console.print()
    else:
        with console.status(f"[{banner.BROWN_DIM}]{engine.model} is thinking...", spinner="dots"):
            result = engine.answer(
                question, k=args.k, history=[], temperature=args.temperature,
                context_tokens=args.context, include=args.include, exclude=args.exclude,
                extensions=args.ext or None,
            )
        banner.answer_panel(console, result.text or "_no answer_")
        _print_sources(result.hits, show_text=not args.no_text)
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    engine = Engine(model=args.model, domain=getattr(args, "domain", "general"))
    banner.print_banner(console, _subtitle(engine))
    if engine.count == 0:
        banner.fail(console, "index is empty. run: rag index")
        return 1

    style = "clinical" if args.domain == "medical" else "general"
    banner.dim(console, f"style  {style}   |   type /sources  /files  /reset  /quit")
    console.print()

    history: list[dict[str, str]] = []
    while True:
        try:
            question = console.input(f"  [bold {banner.PEEL}]you[/bold {banner.PEEL}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not question:
            continue
        lowered = question.lower()
        if lowered in {"/quit", "/exit", "quit", "exit"}:
            break
        if lowered == "/reset":
            history.clear()
            banner.warn(console, "conversation reset")
            continue
        if lowered == "/sources":
            context = " ".join(m["content"] for m in history[-4:]).strip()
            if not context:
                banner.warn(console, "no question asked yet")
                continue
            with console.status(f"[{banner.MUTED}]searching...", spinner="dots"):
                hits = engine.search(context, k=args.k)
            _print_sources(hits, show_text=True)
            continue
        if lowered == "/files":
            banner.header(console, "indexed files", "chunks")
            room = max(console.width - 12, 24)
            for row in engine.files(limit=60):
                console.print(
                    f"  [{banner.MUTED}]{row['chunks']:>5}[/{banner.MUTED}]  "
                    f"{banner.shorten_path(row['rel'], room)}"
                )
            continue

        history.append({"role": "user", "content": question})
        with console.status(f"[{banner.BROWN_DIM}]{engine.model} is thinking...", spinner="dots"):
            result = engine.answer(
                question, k=args.k, history=history[:-1], temperature=args.temperature,
                context_tokens=args.context,
            )
        history.append({"role": "assistant", "content": result.text})
        banner.answer_panel(console, result.text or "_no answer_")
        _print_sources(result.hits, show_text=False)

    return 0


def cmd_files(args: argparse.Namespace) -> int:
    engine = Engine(model=args.model, domain=getattr(args, "domain", "general"))
    rows = engine.files(limit=100000)
    if args.filter:
        needle = args.filter.lower()
        rows = [r for r in rows if needle in str(r["rel"]).lower()]
    console.print()
    banner.header(console, f"indexed files  ({len(rows):,})", "chunks")
    room = max(console.width - 22, 24)
    for row in rows[: args.limit]:
        console.print(
            f"  [{banner.MUTED}]{row['chunks']:>5}[/{banner.MUTED}]  "
            f"[{banner.PEEL}]{(row['ext'] or '-'):<6}[/{banner.PEEL}]  "
            f"{banner.shorten_path(row['rel'], room)}"
        )
    if len(rows) > args.limit:
        banner.dim(console, f"... {len(rows) - args.limit:,} more, use --limit")
    console.print()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    engine = Engine(model=args.model, domain=getattr(args, "domain", "general"))
    summary = engine.summary()
    banner.print_banner(console, _subtitle(engine))
    banner.header(console, "runtime")
    console.print(f"  model    {summary['model']}")
    console.print(f"  ollama   {config.OLLAMA_HOST}")
    console.print(f"  store    {config.CHROMA_DIR}")
    console.print(f"  vector   all-MiniLM-L6-v2 (384d, cosine)")
    banner.header(console, "collection")
    console.print(f"  chunks   {summary['chunks']:,}")
    console.print(f"  files    {summary['files']:,}")
    if summary["by_ext"]:
        banner.header(console, "by extension", "files")
        for ext, count in summary["by_ext"].items():
            bar_len = max(1, int(28 * count / max(summary["by_ext"].values())))
            console.print(
                f"  [{banner.PEEL}]{(ext or 'none'):<9}[/{banner.PEEL}] "
                f"{count:>5}  [{banner.BROWN_DIM}]{'#' * bar_len}[/{banner.BROWN_DIM}]"
            )
    console.print()
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    import ollama

    client = ollama.Client(host=config.OLLAMA_HOST)
    console.print()
    banner.header(console, "local models", f"{config.OLLAMA_HOST}")
    for row in client.list().get("models", []):
        size = row.get("size", 0)
        active = " in use" if row.get("model", "").startswith(LLM_MODEL) else ""
        console.print(
            f"  [{banner.PEEL}]{row.get('model', ''):<28}[/{banner.PEEL}] "
            f"[{banner.MUTED}]{f'{size / 1e9:.1f} GB' if size else '-':>8}[/{banner.MUTED}]"
            f"[{banner.GREEN}]{active}[/{banner.GREEN}]"
        )
    console.print()
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        banner.warn(console, "this deletes the whole index. re-run with --yes to confirm")
        return 1
    from store import get_client

    get_client().delete_collection(config.COLLECTION_NAME)
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR, ignore_errors=True)
    banner.ok(console, "index deleted")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag",
        description="Big Banana - private RAG over your own files. Offline, local, cited.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_model(p: argparse.ArgumentParser) -> None:
        p.add_argument("--model", default=LLM_MODEL, help=f"ollama model (default {LLM_MODEL})")
        p.add_argument(
            "--domain",
            default="general",
            choices=["general", "medical"],
            help="answer style: general file QA, or clinical literature",
        )

    p_index = sub.add_parser("index", help="scan folders and (re)build the index")
    p_index.add_argument("--root", action="append", help="folder to scan, repeatable (default: profile)")
    p_index.add_argument("--force", action="store_true", help="re-index even if unchanged")
    p_index.add_argument("--hidden", action="store_true", help="also walk dot-folders and dot-files")
    p_index.add_argument("--limit", type=int, help="only process first N files (testing)")
    p_index.set_defaults(func=cmd_index)

    p_search = sub.add_parser("search", help="show matching excerpts, no LLM")
    p_search.add_argument("query")
    p_search.add_argument("-k", type=int, default=8)
    p_search.add_argument("--include", default="", help="substring the path must contain")
    p_search.add_argument("--exclude", default="", help="substring to skip")
    p_search.add_argument("--ext", action="append", help="limit to extension, repeatable")
    p_search.add_argument("--no-text", action="store_true", help="table only")
    add_model(p_search)
    p_search.set_defaults(func=cmd_search)

    p_ask = sub.add_parser("ask", help="one question, one answer")
    p_ask.add_argument("question")
    p_ask.add_argument("-k", type=int, default=6)
    p_ask.add_argument("--temperature", type=float, default=0.25)
    p_ask.add_argument("--context", type=int, default=8192, help="ollama num_ctx")
    p_ask.add_argument("--include", default="")
    p_ask.add_argument("--exclude", default="")
    p_ask.add_argument("--ext", action="append")
    p_ask.add_argument("--no-stream", dest="stream", action="store_false")
    p_ask.add_argument("--no-text", action="store_true")
    add_model(p_ask)
    p_ask.set_defaults(func=cmd_ask, stream=True)

    p_chat = sub.add_parser("chat", help="interactive conversation")
    p_chat.add_argument("-k", type=int, default=6)
    p_chat.add_argument("--temperature", type=float, default=0.25)
    p_chat.add_argument("--context", type=int, default=8192)
    add_model(p_chat)
    p_chat.set_defaults(func=cmd_chat)

    p_files = sub.add_parser("files", help="list indexed files")
    p_files.add_argument("--limit", type=int, default=100)
    p_files.add_argument("--filter", default="")
    add_model(p_files)
    p_files.set_defaults(func=cmd_files)

    p_stats = sub.add_parser("stats", help="index statistics")
    add_model(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    p_models = sub.add_parser("models", help="list local ollama models")
    p_models.set_defaults(func=cmd_models)

    p_reset = sub.add_parser("reset", help="delete the index")
    p_reset.add_argument("--yes", action="store_true")
    p_reset.set_defaults(func=cmd_reset)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
