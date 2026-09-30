from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import ollama

from config import LLM_MODEL, OLLAMA_HOST
from store import collection_count, get_collection

TOKEN_RE = re.compile(r"[a-z0-9_]+")
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "at", "by", "from", "as", "it",
    "this", "that", "these", "those", "i", "me", "my", "we", "our", "you", "your",
    "do", "does", "did", "how", "what", "which", "when", "where", "who", "why", "can",
    "could", "would", "should", "will", "shall", "about", "into", "than", "then",
    "there", "here", "have", "has", "had", "not", "no", "so", "such", "also", "any",
    "tell", "give", "show", "find", "know", "please", "file", "files", "document",
}

SYSTEM_PROMPT = """You are a personal document assistant. You answer strictly from the numbered CONTEXTS provided, which are excerpts from the user's own local files.

Rules:
- Use only facts present in the contexts. Never invent, guess, or use outside knowledge as if it came from the files.
- Cite every claim with the matching source number, like [2] or [1][3]. Put the citation right after the sentence it supports.
- If the contexts do not contain the answer, say exactly what is missing and name the closest files you did find.
- If several files conflict, state the conflict and cite each side.
- Be concise and factual. Quote short key phrases in quotes rather than paraphrasing loosely.
- Never mention "chunks", "contexts", "embeddings", or "the index". Refer to "your files".
- Answer in the same language as the question.
- Reply with the answer straight away. Do not restate the question, do not plan, do not explain your reasoning process."""

NO_CONTEXT_HINT = "No matching excerpts were found in the indexed files."

MEDICAL_SYSTEM_PROMPT = """You are a clinical knowledge assistant answering questions from a medical literature corpus (PubMed abstracts and patient-health references) held locally on this computer.

Rules:
- Ground every statement in the numbered CONTEXTS. Never add facts that are not in them, even if you know them.
- Cite each claim with its source number, e.g. [3] or [1][4], immediately after the claim.
- Use correct clinical terminology and spell out abbreviations on first use. Keep units and units' precision exactly as given; never convert or estimate doses, never infer a dose, frequency, or duration that is not written in the context.
- Distinguish study types when it matters (RCT, meta-analysis, cohort, case report, narrative review) and say if the evidence is preliminary, in vitro, animal, or retrospective.
- If the contexts do not answer the question, say so plainly and name what is missing. Never fabricate a citation.
- If sources conflict, present both sides with their citations.
- If a question describes symptoms or asks what to do, explain the documented material and state that it is information, not a diagnosis, and that a qualified clinician should decide.
- Keep it structured and concise: short paragraphs or bullets. No preamble, no restating the question.
- Start with the answer itself. Do not plan, restate, or narrate your reasoning.
- Never mention "chunks", "contexts", "embeddings" or "the index"; say "the sources" or "the literature".
- Answer in the same language as the question."""

SYSTEM_PROMPTS = {"general": SYSTEM_PROMPT, "medical": MEDICAL_SYSTEM_PROMPT}


@dataclass
class Hit:
    id: str
    text: str
    score: float
    vector_rank: int = 0
    path: str = ""
    rel: str = ""
    name: str = ""
    ext: str = ""
    title: str = ""
    header: str = ""
    chunk: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "score": round(self.score, 4),
            "path": self.path,
            "rel": self.rel,
            "name": self.name,
            "ext": self.ext,
            "title": self.title,
            "header": self.header,
            "chunk": self.chunk,
        }


@dataclass
class Answer:
    text: str
    hits: list[Hit] = field(default_factory=list)
    used: set[int] = field(default_factory=set)
    citations: dict[int, Hit] = field(default_factory=dict)


def _tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    raw = TOKEN_RE.findall(text)
    out: list[str] = []
    for token in raw:
        stem = token[:-1] if len(token) > 4 and token.endswith("s") else token
        if stem in STOPWORDS or len(stem) < 2:
            continue
        out.append(stem)
    return out


class Engine:
    def __init__(
        self,
        model: str = LLM_MODEL,
        host: str = OLLAMA_HOST,
        domain: str = "general",
    ) -> None:
        self.model = model
        self.host = host
        self.domain = domain if domain in SYSTEM_PROMPTS else "general"
        self.collection = get_collection()
        self._client = ollama.Client(host=host)
        self._warm()

    def _warm(self) -> None:
        try:
            models = {m.get("model", "") for m in self._client.list().get("models", [])}
        except Exception:
            return
        if self.model not in models and models:
            fallback = next(
                (m for m in models if any(tag in m for tag in ("qwen", "llama", "mistral", "gemma"))),
                None,
            )
            if fallback:
                self.model = fallback

    @property
    def count(self) -> int:
        return collection_count(self.collection)

    def search(
        self,
        query: str,
        k: int = 6,
        candidates: int = 40,
        include: str = "",
        exclude: str = "",
        extensions: list[str] | None = None,
    ) -> list[Hit]:
        query = (query or "").strip()
        if not query or self.count == 0:
            return []

        where: dict[str, Any] = {}
        if extensions:
            where["ext"] = {"$in": [e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions]}

        fetch = min(max(candidates, k), 200)
        raw = self.collection.query(
            query_texts=[query],
            n_results=fetch,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )

        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]
        ids = (raw.get("ids") or [[]])[0]

        query_terms = set(_tokens(query))
        hits: list[Hit] = []
        for rank, (doc_id, doc, meta, dist) in enumerate(zip(ids, docs, metas, dists)):
            rel = meta.get("rel") or meta.get("path", "")
            lowered = rel.lower()
            if include and include.lower() not in lowered:
                continue
            if exclude and exclude.lower() in lowered:
                continue
            lexical = self._lexical(query_terms, doc or "")
            vector_score = max(0.0, 1.0 - float(dist))
            hits.append(
                Hit(
                    id=doc_id,
                    text=doc or "",
                    score=0.65 * vector_score + 0.35 * lexical,
                    vector_rank=rank,
                    path=meta.get("path", ""),
                    rel=rel,
                    name=meta.get("name", ""),
                    ext=meta.get("ext", ""),
                    title=meta.get("title", ""),
                    header=meta.get("header", ""),
                    chunk=int(meta.get("chunk", 0) or 0),
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return self._diversify(hits, k)

    def _lexical(self, query_terms: set[str], doc: str) -> float:
        if not query_terms:
            return 0.0
        doc_terms = set(_tokens(doc))
        if not doc_terms:
            return 0.0
        overlap = query_terms & doc_terms
        if not overlap:
            return 0.0
        return len(overlap) / len(query_terms)

    def _diversify(self, hits: list[Hit], k: int) -> list[Hit]:
        picked: list[Hit] = []
        seen_files: dict[str, int] = {}
        for hit in hits:
            key = hit.path or hit.id
            if seen_files.get(key, 0) >= 2:
                continue
            seen_files[key] = seen_files.get(key, 0) + 1
            picked.append(hit)
            if len(picked) >= k:
                break
        return picked

    def build_context(self, hits: list[Hit], char_budget: int = 14000) -> tuple[str, list[Hit]]:
        blocks: list[str] = []
        used: list[Hit] = []
        total = 0
        for number, hit in enumerate(hits, start=1):
            body = hit.text.strip()
            block = f"[{number}] FILE: {hit.rel}\n    SECTION: {hit.header}\n{body}"
            if total + len(block) > char_budget and used:
                break
            blocks.append(block)
            total += len(block)
            used.append(hit)
        return "\n\n".join(blocks), used

    def _messages(
        self,
        question: str,
        context: str,
        history: list[dict[str, str]] | None,
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": SYSTEM_PROMPTS[self.domain]}]
        for turn in (history or [])[-4:]:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        if context:
            user = f"CONTEXTS\n{context}\n\nQUESTION: {question}"
        elif self.domain == "medical":
            user = (
                "The retrieved literature does not cover this question.\n\n"
                f"QUESTION: {question}\n\n"
                "State clearly that the indexed sources do not cover this, do not answer from "
                "memory, and suggest what search terms or source types would be needed."
            )
        else:
            user = (
                f"{NO_CONTEXT_HINT}\n\nQUESTION: {question}\n\n"
                "Tell the user you could not find that in their indexed files."
            )
        messages.append({"role": "user", "content": user})
        return messages

    def _options(self, temperature: float, context_tokens: int, num_predict: int = 4000) -> dict[str, Any]:
        return {
            "temperature": temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.05,
            "num_ctx": context_tokens,
            "num_predict": num_predict,
        }

    def _chat(self, messages: list[dict[str, str]], temperature: float, context_tokens: int) -> str:
        best = ""
        for num_predict in (4000, 8000):
            try:
                response = self._client.chat(
                    model=self.model,
                    messages=messages,
                    options=self._options(temperature, context_tokens, num_predict),
                )
            except Exception as exc:
                return best or f"[model error] {type(exc).__name__}: {exc}"
            content = strip_thinking(response.get("message", {}).get("content", "") or "")
            if len(content) > len(best):
                best = content
            if content.strip() and not looks_truncated(content):
                return content
        return best

    def stream_answer(
        self,
        question: str,
        k: int = 6,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.25,
        context_tokens: int = 8192,
        include: str = "",
        exclude: str = "",
        extensions: list[str] | None = None,
    ) -> Iterator[str]:
        hits = self.search(
            question, k=k, include=include, exclude=exclude, extensions=extensions
        )
        context, used = self.build_context(hits)
        messages = self._messages(question, context, history)
        raw = ""
        produced = False
        for num_predict in (4000, 8000):
            produced = False
            raw = ""
            try:
                stream = self._client.chat(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    options=self._options(temperature, context_tokens, num_predict),
                )
                for part in stream:
                    piece = part.get("message", {}).get("content", "") or ""
                    if piece:
                        raw += piece
                        produced = True
                        yield piece
            except Exception as exc:
                yield f"\n[model error] {type(exc).__name__}: {exc}"
                return
            if produced or strip_thinking(raw).strip():
                return

    def answer(
        self,
        question: str,
        k: int = 6,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.25,
        context_tokens: int = 8192,
        include: str = "",
        exclude: str = "",
        extensions: list[str] | None = None,
    ) -> Answer:
        hits = self.search(
            question, k=k, include=include, exclude=exclude, extensions=extensions
        )
        context, used = self.build_context(hits)
        messages = self._messages(question, context, history)
        text = self._chat(messages, temperature, context_tokens)
        citations = {i: hit for i, hit in enumerate(used, start=1)}
        return Answer(
            text=text,
            hits=used,
            used=set(citations),
            citations=citations,
        )

    def files(self, limit: int = 5000) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        page = 2000
        offset = 0
        while True:
            data = self.collection.get(include=["metadatas"], limit=page, offset=offset)
            metadatas = data.get("metadatas") or []
            if not metadatas:
                break
            for meta in metadatas:
                if not meta:
                    continue
                key = meta.get("path_key", "")
                entry = seen.get(key)
                if entry is None:
                    seen[key] = {
                        "path_key": key,
                        "path": meta.get("path", ""),
                        "rel": meta.get("rel", ""),
                        "ext": meta.get("ext", ""),
                        "title": meta.get("title", ""),
                        "mtime": meta.get("mtime", 0),
                        "chunks": 1,
                    }
                else:
                    entry["chunks"] += 1
            if len(metadatas) < page:
                break
            offset += page
        rows = sorted(seen.values(), key=lambda r: str(r["rel"]).lower())
        return rows[:limit]

    def summary(self) -> dict[str, Any]:
        rows = self.files(limit=100000)
        by_ext: dict[str, int] = {}
        for row in rows:
            by_ext[row["ext"] or "(none)"] = by_ext.get(row["ext"] or "(none)", 0) + 1
        return {
            "chunks": self.count,
            "files": len(rows),
            "by_ext": dict(sorted(by_ext.items(), key=lambda kv: -kv[1])),
            "model": self.model,
            "domain": self.domain,
        }


def looks_truncated(text: str) -> bool:
    stripped = text.rstrip().rstrip('"\'`)]>*_ ')
    if not stripped:
        return True
    return stripped[-1] not in ".!?;:)]>*`\"'"


def strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"^<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    return text.strip()


def read_snippet(path: str, max_chars: int = 6000) -> str:
    try:
        from loaders import load_sections

        _, sections = load_sections(Path(path))
        return "\n\n".join(body for _, body in sections)[:max_chars]
    except Exception as exc:
        return f"[could not read file: {type(exc).__name__}: {exc}]"
