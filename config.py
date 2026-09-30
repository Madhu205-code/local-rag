from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.environ.get("LOCAL_RAG_HOME", Path.home())).resolve()
ROOT = Path(__file__).resolve().parent

DATA_DIR = Path(os.environ.get("LOCAL_RAG_DATA", ROOT / "data"))
CHROMA_DIR = DATA_DIR / "chroma"
MANIFEST_PATH = DATA_DIR / "manifest.json"
INGEST_LOG = DATA_DIR / "ingest.log"

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL = os.environ.get("LOCAL_RAG_MODEL", "qwen3:4b")
COLLECTION_NAME = "local_files"

CHUNK_WORDS = int(os.environ.get("LOCAL_RAG_CHUNK_WORDS", "180"))
CHUNK_OVERLAP = int(os.environ.get("LOCAL_RAG_CHUNK_OVERLAP", "40"))
MAX_FILE_MB = float(os.environ.get("LOCAL_RAG_MAX_FILE_MB", "24"))
MIN_CHUNK_CHARS = 40

DEFAULT_ROOTS = [HOME]

EXCLUDED_DIR_NAMES = {
    "appdata",
    "node_modules",
    "bower_components",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "site-packages",
    "dist-packages",
    "miniconda3",
    "anaconda3",
    "miniconda",
    "anaconda",
    ".conda",
    ".anaconda",
    ".cache",
    ".local",
    ".vscode",
    ".vscode-shared",
    ".antigravity-ide",
    ".cline",
    ".codex",
    ".gemini",
    ".junie",
    ".cagent",
    ".pi",
    ".ssh",
    ".gnupg",
    ".ollama",
    ".docker",
    ".npm",
    ".yarn",
    ".pnpm-store",
    ".gradle",
    ".m2",
    ".nuget",
    ".cargo",
    ".rustup",
    ".ivy2",
    ".sbt",
    ".stack",
    ".dotnet",
    "windows",
    "system volume information",
    "recovery",
    "programdata",
    "$recycle.bin",
    "system volume",
    "my documents",
    "application data",
    "local settings",
    "cookies",
    "nethood",
    "printhood",
    "recent",
    "sendto",
    "searches",
    "favorites",
    "templates",
    "start menu",
    "desktop.ini",
}

TEXT_EXTENSIONS = {
    ".txt", ".log", ".text", ".md", ".markdown", ".mdx", ".rst", ".adoc",
    ".tex", ".bib", ".org", ".srt", ".vtt", ".ics", ".eml",
}

DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".epub", ".rtf", ".odt"}

DATA_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".ipynb"}

WEB_EXTENSIONS = {".html", ".htm", ".xhtml"}

CODE_EXTENSIONS = {
    ".py", ".pyi", ".ipynb", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".java", ".kt", ".kts", ".scala", ".groovy", ".c", ".h", ".cc", ".cpp",
    ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".m", ".mm",
    ".dart", ".lua", ".pl", ".pm", ".r", ".jl", ".sh", ".bash", ".zsh", ".fish",
    ".ps1", ".psm1", ".bat", ".cmd", ".vb", ".fs", ".clj", ".ex", ".exs",
    ".erl", ".hs", ".ml", ".sql", ".html", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte", ".graphql", ".gql", ".proto", ".tf", ".tfvars",
    ".cmake", ".mk", ".gradle", ".properties", ".env", ".dockerfile",
    ".gitignore", ".editorconfig", ".diff", ".patch",
}

INDEXABLE_EXTENSIONS = (
    TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | DATA_EXTENSIONS | WEB_EXTENSIONS | CODE_EXTENSIONS
)

SKIP_FILENAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
