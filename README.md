# Big Banana

Private retrieval-augmented Q&A over your own files. CLI only, 100% offline:
embeddings and answers are produced locally, nothing is sent anywhere.

- Embeddings: `all-MiniLM-L6-v2` via ChromaDB's ONNX runtime (downloaded once, then cached)
- Vector store: ChromaDB, persistent at `data/chroma`
- Answers: local Ollama model, default `qwen3:4b`

The logo auto-fits your terminal width and falls back to ASCII art on consoles
that cannot render block characters, so it never garbles or crashes.

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
ollama pull qwen3:4b
```

Ollama must be running (`ollama serve`).

## Commands

```
rag chat                              # interactive conversation
rag ask "what did I write about X"    # one question, one answer
rag search "keyword" -k 5             # raw excerpts, no LLM
rag index                             # index your profile folder
rag index --root D:\docs              # index a specific folder instead
rag files --filter pdf                # list what is indexed
rag stats
rag models
rag reset --yes                       # wipe the index
```

If `rag` is not found, either call it as `.\rag.cmd` from inside the folder, or
add the folder to your user PATH and open a new terminal.

Useful flags on `ask` / `chat`:

| flag | meaning |
| --- | --- |
| `-k 8` | how many excerpts to read (default 6) |
| `--domain medical` | clinical answer style instead of general file QA |
| `--model deepseek-r1:14b` | use a different local model |
| `--include pdf` | only paths containing this |
| `--exclude node_modules` | skip paths containing this |
| `--ext .pdf --ext .txt` | only these extensions |
| `--context 16384` | ollama context window |
| `--no-stream` | render the answer at once instead of streaming |

Inside `chat`: `/sources` re-shows the excerpts behind the last answer,
`/files` lists the index, `/reset` clears the conversation, `/quit` exits.

## How it works

1. `indexer.py` walks the scan roots, skipping caches, dependency folders and
   hidden directories. Each file is fingerprinted by size + mtime, so re-running
   only re-embeds what actually changed. Deleted files are dropped from the index.
2. `loaders.py` extracts text per format: PDF pages, DOCX headings + tables,
   XLSX sheets, PPTX slides, EPUB chapters, HTML, CSV rows, JSON leaves, notebooks
   and source code. Everything else is read as text with encoding fallback.
3. `chunker.py` packs paragraphs (or code blocks) into ~180-word chunks with
   overlap, so a fact near a boundary still survives retrieval.
4. `engine.py` pulls 40 candidates, fuses vector similarity with keyword overlap
   (0.65 / 0.35), caps repeats per file, and sends the top ones to the model with
   numbered citations. The model is instructed to answer only from those excerpts.

## Medical corpus

`fetch_medical.py` downloads a text corpus from PubMed via NCBI E-utilities
(public, no API key). Default output is `Downloads\medical-Rag\corpus-text`,
one `.txt` per abstract with title, authors, journal, year, PMID, DOI and MeSH
keywords, filed under 30 topic folders.

```
python fetch_medical.py --per-topic 120
python cli.py index --root "~/Downloads/medical-Rag/corpus-text"
python cli.py ask "first line therapy for metastatic NSCLC" --domain medical
```

Note: the lung-cancer CT scans in that folder are images and are **not** indexed
by this text pipeline. A CT set needs a vision model, not embeddings.

## Files

| file | role |
| --- | --- |
| `cli.py` | command line entry point |
| `banner.py` | the Big Banana logo, theme colours, panels and source tables |
| `config.py` | scan roots, excluded folders, extensions, chunk sizes, model |
| `indexer.py` | folder walk, change detection, ChromaDB writes |
| `loaders.py` | per-format text extraction |
| `chunker.py` | chunking with overlap |
| `engine.py` | retrieval, reranking, prompting, citations |
| `store.py` | ChromaDB client and index manifest |
| `fetch_medical.py` | PubMed corpus downloader |

## Notes

- Your files never leave the machine. Ollama runs locally, ChromaDB is local, and
  ChromaDB telemetry is disabled in `store.py`.
- The index in `data/` is deliberately **not** committed to this repo. It contains
  excerpts of your personal files, so it is git-ignored; rebuild it with `rag index`.
- `DEFAULT_ROOTS` in `config.py` is your home folder. Narrow it with
  `LOCAL_RAG_HOME`, or just pass `--root` to `index`.
- Medical answers are literature summaries, not diagnosis or dosing advice.
- Delete the index any time with `python cli.py reset --yes`; your files are never modified.
- Answers are only as good as the excerpts retrieved. If `search` returns nothing
  useful for a question, the model cannot invent the answer either.

## License

MIT. See [LICENSE](LICENSE).
