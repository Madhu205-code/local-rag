from __future__ import annotations

import re
from typing import Iterable

from config import CHUNK_OVERLAP, CHUNK_WORDS

PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+")

CODE_HINT = re.compile(
    r"^\s*(def |class |import |from |function |const |let |var |public |private |"
    r"#include|package |func |fn |struct |impl |SELECT |CREATE |INSERT |UPDATE )",
    re.MULTILINE,
)


def _split_long(text: str, max_words: int) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    pieces: list[str] = []
    for start in range(0, len(words), max_words):
        pieces.append(" ".join(words[start : start + max_words]))
    return pieces


def chunk_text(
    text: str,
    max_words: int = CHUNK_WORDS,
    overlap: int = CHUNK_OVERLAP,
    is_code: bool = False,
) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    if is_code:
        return _chunk_code(text, max_words=max_words, overlap=overlap)

    paragraphs = [p.strip() for p in PARAGRAPH_SPLIT.split(text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[str] = []
    buffer: list[str] = []
    buffer_words = 0

    def flush() -> None:
        nonlocal buffer, buffer_words
        if buffer:
            chunks.append("\n\n".join(buffer).strip())
            buffer = []
            buffer_words = 0

    for paragraph in paragraphs:
        words = paragraph.split()
        if len(words) > max_words:
            sentences = [s for s in SENTENCE_SPLIT.split(paragraph) if s.strip()]
            units: list[str] = []
            for sentence in sentences:
                units.extend(_split_long(sentence, max_words))
        else:
            units = [paragraph]

        for unit in units:
            unit_words = len(unit.split())
            if buffer_words + unit_words > max_words and buffer:
                tail = " ".join(buffer[-1].split()[-overlap:]) if overlap > 0 else ""
                flush()
                if tail:
                    buffer = [tail]
                    buffer_words = len(tail.split())
            buffer.append(unit)
            buffer_words += unit_words

    flush()
    return _dedupe(chunks)


def _chunk_code(text: str, max_words: int, overlap: int) -> list[str]:
    lines = text.split("\n")
    if CODE_HINT.search(text):
        blocks: list[str] = []
        current: list[str] = []
        for line in lines:
            if CODE_HINT.match(line) and current:
                blocks.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            blocks.append("\n".join(current))
        if len(blocks) > 1:
            chunks: list[str] = []
            buffer: list[str] = []
            for block in blocks:
                if len("\n".join(buffer).split()) + len(block.split()) > max_words and buffer:
                    chunks.append("\n".join(buffer))
                    buffer = block.split("\n")[-overlap:] if overlap > 0 else []
                buffer.extend(block.split("\n"))
            if buffer:
                chunks.append("\n".join(buffer))
            return _dedupe(chunks)
    return _dedupe(_split_long(text, max_words))


def _dedupe(chunks: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for chunk in chunks:
        normalized = chunk.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out
