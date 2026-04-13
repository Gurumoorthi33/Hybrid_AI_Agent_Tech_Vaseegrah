#!/usr/bin/env python3
"""
setup.py — one-time setup.
1. Creates the data/default/ directory
2. Copies vaseegrah_veda.txt (and sample.txt) from uploads into data/default/
3. Ingests them into the default FAISS knowledge base
Run: python setup.py
"""

import os, shutil, sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv()

# ── Directory scaffolding ─────────────────────────────────────────
os.makedirs("data/default",    exist_ok=True)
os.makedirs("data/customers",  exist_ok=True)

# ── Copy knowledge files from sandbox uploads ─────────────────────
UPLOADS = "/mnt/user-data/uploads"
KB_FILES = ["vaseegrah_veda.txt", "sample.txt"]

for fname in KB_FILES:
    src = os.path.join(UPLOADS, fname)
    dst = os.path.join("data/default", fname)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy(src, dst)
        print(f"📋 Copied {fname} → data/default/")
    elif os.path.exists(dst):
        print(f"✅ {fname} already in data/default/")
    else:
        print(f"⚠️  {fname} not found in uploads — add it to data/default/ manually")

# ── Ingest into FAISS ─────────────────────────────────────────────
print("\n🔄 Ingesting default knowledge base...")
from memory.ingestor import ingest_default
ingest_default()

print("\n✅ Setup complete!")
print("   Start CLI:    python main.py")
print("   Start server: python server.py")