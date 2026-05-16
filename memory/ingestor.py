"""
memory/ingestor.py
Knowledge ingestion for both the default shared KB and per-customer files.

Usage:
  # Ingest default knowledge base (vaseegrah_veda.txt etc.)
  python -m memory.ingestor --default

  # Ingest a customer's uploaded files
  python -m memory.ingestor --customer <api_key> --file path/to/file.txt
"""

import os
import re
import argparse
import shutil
from memory.vector_store import VectorStore
from memory.customer_config import customer_dir, validate_customer_id
from config.settings import (
    DEFAULT_RAG_DIR, DEFAULT_INDEX, DEFAULT_DOCS,
)

CHUNK_SIZE    = 500
CHUNK_OVERLAP = 100
SUPPORTED_EXTS = {".txt", ".pdf", ".md", ".csv"}
CUSTOMER_SOURCE_DIR = "documents"


# ── text splitting ────────────────────────────────────────────────

def _chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    text = text.strip()
    while start < len(text):
        chunk = text[start : start + CHUNK_SIZE].strip()
        if chunk:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _parse_qa_file(text: str) -> list[str]:
    """
    Parses the VaseegrahVeda CSV-style Q&A file into natural-language strings.
    Each pair becomes:  "Q: ...\nA: ..."
    This phrasing dramatically improves semantic retrieval for user questions.
    """
    docs = []
    # Match "question text", "answer text"  (possibly multi-line)
    pattern = re.compile(r'"([^"]{5,}?)"\s*,\s*"([^"]{5,}?)"', re.DOTALL)
    for q, a in pattern.findall(text):
        q = q.strip().replace("\r\n", " ").replace("\n", " ")
        a = a.strip().replace("\r\n", " ").replace("\n", " ")
        docs.append(f"Q: {q}\nA: {a}")
    return docs if docs else _chunk_text(text)


def _read_txt(path: str) -> str:
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def _read_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    except Exception as e:
        print(f"⚠️  PDF error {path}: {e}")
        return ""


def _extract_docs(path: str) -> list[str]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        raw = _read_pdf(path)
        return _chunk_text(raw)
    elif ext in (".txt", ".md", ".csv"):
        raw = _read_txt(path)
        # Auto-detect Q&A style (contains  "...", "..."  pattern)
        if raw.count('","') > 20:
            docs = _parse_qa_file(raw)
            print(f"   → Q&A mode: {len(docs)} pairs extracted")
            return docs
        return _chunk_text(raw)
    else:
        print(f"   ⏭  Skipping unsupported format: {path}")
        return []


def _safe_filename(filename: str, fallback_ext: str = "") -> str:
    name = os.path.basename(filename or "").strip()
    if not name:
        name = f"document{fallback_ext}"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = name.strip("._")
    return name or f"document{fallback_ext}"


def _customer_paths(api_key: str) -> tuple[str, str, str, str]:
    api_key = validate_customer_id(api_key)
    cust_dir = customer_dir(api_key)
    docs_dir = os.path.join(cust_dir, CUSTOMER_SOURCE_DIR)
    index_path = os.path.join(cust_dir, "index.bin")
    docs_path = os.path.join(cust_dir, "docs.pkl")
    return cust_dir, docs_dir, index_path, docs_path


def _customer_source_files(api_key: str) -> list[str]:
    _, docs_dir, _, _ = _customer_paths(api_key)
    if not os.path.isdir(docs_dir):
        return []
    paths = []
    for fname in sorted(os.listdir(docs_dir)):
        path = os.path.join(docs_dir, fname)
        if os.path.isfile(path) and os.path.splitext(fname)[1].lower() in SUPPORTED_EXTS:
            paths.append(path)
    return paths


# ── ingest default KB ─────────────────────────────────────────────

def ingest_default():
    """Ingest all files in data/default/ into the shared company vector store."""
    os.makedirs(DEFAULT_RAG_DIR, exist_ok=True)
    vs = VectorStore(DEFAULT_INDEX, DEFAULT_DOCS, label="default")

    all_docs = []
    for fname in os.listdir(DEFAULT_RAG_DIR):
        if fname.endswith((".txt", ".pdf", ".md", ".csv")):
            path = os.path.join(DEFAULT_RAG_DIR, fname)
            print(f"📄 Default KB — ingesting: {fname}")
            docs = _extract_docs(path)
            all_docs.extend(docs)

    if all_docs:
        vs.add_documents(all_docs)
        print(f"✅ Default KB ingestion complete. {len(all_docs)} chunks stored.")
    else:
        print("⚠️  No files found in data/default/  — add vaseegrah_veda.txt there.")


# ── ingest customer file ──────────────────────────────────────────

def ingest_customer_file(api_key: str, file_path: str) -> int:
    """
    Ingest one customer file by replacing the matching stored source file and
    rebuilding that customer's private vector store from all stored documents.
    """
    result = upsert_customer_file(api_key, file_path)
    return result["chunks"]


def rebuild_customer_store(api_key: str) -> dict:
    """Rebuild a customer's private vector DB from their stored source files."""
    cust_dir, docs_dir, index_path, docs_path = _customer_paths(api_key)
    os.makedirs(cust_dir, exist_ok=True)
    os.makedirs(docs_dir, exist_ok=True)

    vs = VectorStore(index_path, docs_path, label=f"customer:{api_key[:8]}")
    all_docs = []
    files = _customer_source_files(api_key)

    for path in files:
        print(f"📄 Customer [{api_key[:8]}] — reading: {os.path.basename(path)}")
        docs = _extract_docs(path)
        all_docs.extend(docs)

    vs.replace_documents(all_docs)
    return {
        "customer_id": api_key,
        "files": [os.path.basename(path) for path in files],
        "file_count": len(files),
        "chunks": len(all_docs),
        "index_path": index_path,
        "docs_path": docs_path,
        "documents_dir": docs_dir,
    }


def upsert_customer_file(
    api_key: str,
    file_path: str,
    filename: str | None = None,
) -> dict:
    """
    Save or replace a customer's source document, then rebuild their vector DB.
    Uploading the same filename updates the file and removes stale embeddings.
    """
    ext = os.path.splitext(filename or file_path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported file type '{ext}'. Allowed: {sorted(SUPPORTED_EXTS)}")

    _, docs_dir, _, _ = _customer_paths(api_key)
    os.makedirs(docs_dir, exist_ok=True)

    stored_name = _safe_filename(filename or os.path.basename(file_path), ext)
    stored_path = os.path.join(docs_dir, stored_name)
    if os.path.abspath(file_path) != os.path.abspath(stored_path):
        shutil.copyfile(file_path, stored_path)

    result = rebuild_customer_store(api_key)
    result["uploaded_file"] = stored_name
    print(
        f"✅ Customer [{api_key[:8]}] KB rebuilt: "
        f"{result['chunks']} chunks from {result['file_count']} files"
    )
    return result


# ── CLI entry ─────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YoWhats Knowledge Ingestor")
    parser.add_argument("--default",  action="store_true", help="Ingest default company KB")
    parser.add_argument("--customer", type=str, help="Customer API key")
    parser.add_argument("--file",     type=str, help="Path to customer file to ingest")
    args = parser.parse_args()

    if args.default:
        ingest_default()
    elif args.customer and args.file:
        ingest_customer_file(args.customer, args.file)
    else:
        print("Usage:\n  --default\n  --customer <api_key> --file <path>")
