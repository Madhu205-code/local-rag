from __future__ import annotations

import sys
from typing import Sequence

from rich import box as rbox
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

YELLOW = "bold yellow"
PEEL = "gold1"
BROWN = "orange3"
BROWN_DIM = "orange4"
MUTED = "grey50"
GREEN = "bold green"
CYAN = "bold cyan"
RED = "bold red"

GLYPH_W = 7

_GLYPHS_UNICODE: dict[str, list[str]] = {
    "B": ["██████ ", "██  ██ ", "██████ ", "██  ██ ", "██████ "],
    "I": ["██████ ", "  ██  ", "  ██  ", "  ██  ", "██████ "],
    "G": [" ██████", "██    █", "██   ██", "██    █", " ██████"],
    "A": [" ██████", "██   ██", "██████ ", "██   ██", "██   ██"],
    "N": ["██   ██", "███  ██", "████ ██", "██ ███", "██  ██"],
    " ": ["       "] * 5,
}

_GLYPHS_ASCII: dict[str, list[str]] = {
    "B": ["###### ", "##  ## ", "###### ", "##  ## ", "###### "],
    "I": ["  ##   ", "  ##   ", "  ##   ", "  ##   ", "  ##   "],
    "G": [" #####", "##    ", "##  ##", "##    ", " #####"],
    "A": [" #####", "##  ##", "##### ", "##  ##", "##  ##"],
    "N": ["##   ##", "###  ##", "## # ##", "##  ###", "##   ##"],
    " ": ["       "] * 5,
}


def _normalize(glyphs: dict[str, list[str]]) -> dict[str, list[str]]:
    return {char: [row.ljust(GLYPH_W) for row in rows] for char, rows in glyphs.items()}


UNICODE_BLOCKS = _normalize(_GLYPHS_UNICODE)
ASCII_BLOCKS = _normalize(_GLYPHS_ASCII)

SPLASH_UNICODE = [
    r"        _     _                       _                 ",
    r"  __ _ | |__ (_) __ _ _ __  __ _ _ __ | |__   ___  __ _ ",
    r" / _` | '_ \| |/ _` | '__|/ _` | '_ \| '_ \ / _ \/ _` |",
    r"| (_| | |_) | | (_| | |  | (_| | |_) | |_) |  __/ (_| |",
    r" \__,_|_.__/|_|\__,_|_|   \__,_| .__/|_.__/ \___|\__, |",
    r"                            |___/                    |___/ ",
]

SPLASH_ASCII = [
    r"        _     _                       _                 ",
    r"  __ _ | |__ (_) __ _ _ __  __ _ _ __ | |__   ___  __ _ ",
    r" / _` | '_ \| |/ _` | '__|/ _` | '_ \| '_ \ / _ \/ _` |",
    r"| (_| | |_) | | (_| | |  | (_| | |_) | |_) |  __/ (_| |",
    r" \__,_|_.__/|_|\__,_|_|   \__,_| .__/|_.__/ \___|\__, |",
    r"                            |___/                    |___/ ",
]

TAGLINE = "ask your own files  |  private  |  offline"


def unicode_supported(encoding: str | None = None) -> bool:
    encoding = encoding or (getattr(sys.stdout, "encoding", None) or "ascii")
    try:
        "█·─╭╮╰╯".encode(encoding)
    except (UnicodeEncodeError, LookupError, TypeError):
        return False
    return True


class Theme:
    def __init__(self, encoding: str | None = None) -> None:
        self.unicode = unicode_supported(encoding)
        self.glyphs = UNICODE_BLOCKS if self.unicode else ASCII_BLOCKS
        self.splash = SPLASH_UNICODE if self.unicode else SPLASH_ASCII
        self.title = "BIG BANANA" if self.unicode else "big banana"
        self.sep = "─" if self.unicode else "-"


THEME = Theme()


def word_art(word: str, gap: int = 1) -> str:
    rows = ["", "", "", "", ""]
    for char in word.upper():
        glyph = THEME.glyphs.get(char, THEME.glyphs[" "])
        for row in range(5):
            rows[row] += glyph[row] + " " * gap
    return "\n".join(row.rstrip() for row in rows)


def art_width(word: str, gap: int = 2) -> int:
    if not word:
        return 0
    return len(word) * GLYPH_W + (len(word) - 1) * gap


def logo_lines(available: int) -> str:
    title = "BIG BANANA" if THEME.unicode else "big banana"
    parts = title.split(" ")

    for gap in (1, 0):
        if art_width(title, gap) <= available:
            return word_art(title, gap)

    for join in ("   ", " ", "", "  "):
        for gap in (1, 0):
            blocks = [word_art(part, gap).split("\n") for part in parts]
            widths = [max(len(row) for row in block) for block in blocks]
            if sum(widths) + len(join) * (len(blocks) - 1) > available:
                continue
            rows = []
            for row in range(5):
                pieces = [block[row].ljust(width) for block, width in zip(blocks, widths)]
                rows.append(join.join(pieces).rstrip())
            return "\n".join(rows)

    if all(art_width(part, 0) <= available for part in parts):
        return "\n".join(word_art(part, 0) for part in parts)

    return title


def banner_text(subtitle: str = "", available: int = 76) -> str:
    body = logo_lines(available) + "\n\n  " + TAGLINE
    if subtitle:
        body += "\n\n  " + subtitle
    return body


def print_banner(console: Console, subtitle: str = "") -> None:
    available = max(console.width - 8, 20)
    art = Text(banner_text(subtitle, available), style=f"bold {PEEL}")
    console.print()
    console.print(
        Panel(
            Align.center(art, vertical="middle"),
            box=rbox.ROUNDED,
            border_style=PEEL,
            padding=(1, 2),
        )
    )
    console.print()


def print_splash(console: Console) -> None:
    text = Text()
    for index, row in enumerate(THEME.splash):
        text.append(row + "\n", style=BROWN if index in (1, 2) else BROWN_DIM)
    console.print(Align.center(text))
    console.print()


def header(console: Console, left: str, right: str = "") -> None:
    line = Text()
    line.append(left, style=f"bold {PEEL}")
    if right:
        pad = max(console.width - len(left) - len(right) - 2, 1)
        line.append(" " * pad + right, style=MUTED)
    console.print(line)
    console.print(Text(THEME.sep * console.width, style=BROWN_DIM))


def answer_panel(console: Console, markdown_text: str) -> None:
    from rich.markdown import Markdown

    console.print()
    console.print(
        Panel(
            Markdown(markdown_text),
            title=Text(" answer ", style=f"bold {BROWN}"),
            title_align="left",
            border_style=PEEL,
            box=rbox.ROUNDED,
            padding=(1, 2),
        )
    )


def sources_table(hits: Sequence, limit: int | None = None) -> Table:
    table = Table(box=None, pad_edge=False, show_edge=False, expand=True)
    table.add_column("", width=4, justify="right", style=f"bold {BROWN}")
    table.add_column("source", overflow="ellipsis", max_width=48, style=PEEL)
    table.add_column("where", overflow="ellipsis", max_width=24, style=MUTED)
    table.add_column("score", justify="right", width=6, style=MUTED)
    for number, hit in enumerate(hits, start=1):
        if limit and number > limit:
            break
        table.add_row(f"[{number}]", hit.rel or hit.name, hit.header, f"{hit.score:.3f}")
    return table


def preview(console: Console, text: str, limit: int = 700) -> None:
    body = text.strip()
    if len(body) > limit:
        body = body[:limit].rstrip() + " ..."
    console.print(
        Panel(
            Text(body, style="white"),
            title=Text(" excerpt ", style=f"bold {BROWN}"),
            title_align="left",
            border_style=BROWN_DIM,
            box=rbox.ROUNDED,
            padding=(0, 2),
        )
    )


def shorten_path(path: str, width: int) -> str:
    if width <= 4 or len(path) <= width:
        return path
    if width <= 2:
        return path[-width:]
    return ".." + path[-(width - 2):]


def ok(console: Console, message: str) -> None:
    console.print(f"  [{GREEN}]done[/{GREEN}]  {message}")


def warn(console: Console, message: str) -> None:
    console.print(f"  [bold yellow]note[/bold yellow]  {message}")


def fail(console: Console, message: str) -> None:
    console.print(f"  [{RED}]fail[/{RED}]  {message}")


def dim(console: Console, message: str) -> None:
    console.print(f"  [{MUTED}]{message}[/{MUTED}]")
