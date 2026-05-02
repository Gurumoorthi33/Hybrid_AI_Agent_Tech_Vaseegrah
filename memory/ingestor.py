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
from memory.vector_store import VectorStore
from config.settings import (
    DEFAULT_RAG_DIR, DEFAULT_INDEX, DEFAULT_DOCS,
    CUSTOMER_RAG_BASE,
)

CHUNK_SIZE    = 500
CHUNK_OVERLAP = 100


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
    """Ingest a single file into a customer's private vector store."""
    cust_dir   = os.path.join(CUSTOMER_RAG_BASE, api_key)
    index_path = os.path.join(cust_dir, "index.bin")
    docs_path  = os.path.join(cust_dir, "docs.pkl")
    os.makedirs(cust_dir, exist_ok=True)

    vs = VectorStore(index_path, docs_path, label=f"customer:{api_key[:8]}")
    print(f"📄 Customer [{api_key[:8]}] — ingesting: {file_path}")
    docs = _extract_docs(file_path)
    if docs:
        vs.add_documents(docs)
        print(f"✅ Customer KB updated. {len(docs)} chunks added.")
        return len(docs)
    else:
        print("⚠️  No content extracted from file.")
        return 0


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
