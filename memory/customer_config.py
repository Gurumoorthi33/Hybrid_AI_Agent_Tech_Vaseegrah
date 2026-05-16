"""
Per-customer RAG configuration stored under data/customers/<client_id>/.

This module intentionally never reads from or writes to data/default. It is
used only for client-specific website fallback and API readiness metadata.
"""

import json
import os
import re
from datetime import datetime, UTC
from urllib.parse import urlparse

from config.settings import CUSTOMER_RAG_BASE

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_customer_id(client_id: str) -> str:
    client_id = (client_id or "").strip()
    if not client_id or not _SAFE_ID.fullmatch(client_id):
        raise ValueError("Invalid client_id")
    return client_id


def customer_dir(client_id: str) -> str:
    client_id = validate_customer_id(client_id)
    base = os.path.abspath(CUSTOMER_RAG_BASE)
    path = os.path.abspath(os.path.join(base, client_id))
    if os.path.commonpath([base, path]) != base:
        raise ValueError("Invalid client_id path")
    return path


def customer_config_path(client_id: str) -> str:
    return os.path.join(customer_dir(client_id), "config.json")


def normalize_website_url(website_url: str | None) -> str | None:
    raw = (website_url or "").strip()
    if not raw:
        return None

    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Website URL must use http or https")
    if not parsed.netloc:
        raise ValueError("Website URL must include a valid host")

    path = parsed.path.rstrip("/")
    return parsed._replace(path=path, params="", query="", fragment="").geturl()


def load_customer_config(client_id: str) -> dict:
    path = customer_config_path(client_id)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_customer_config(
    client_id: str,
    *,
    website_url: str | None = None,
    client_name: str | None = None,
) -> dict:
    cust_dir = customer_dir(client_id)
    os.makedirs(cust_dir, exist_ok=True)

    config = load_customer_config(client_id)
    config["client_id"] = client_id
    if client_name:
        config["client_name"] = client_name
    if website_url is not None:
        config["website_url"] = normalize_website_url(website_url)
    config["updated_at"] = datetime.now(UTC).isoformat()

    with open(customer_config_path(client_id), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, sort_keys=True)
    return config


def get_customer_website(client_id: str | None) -> str | None:
    if not client_id:
        return None
    try:
        return load_customer_config(client_id).get("website_url")
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def customer_rag_status(client_id: str) -> dict:
    cust_dir = customer_dir(client_id)
    docs_dir = os.path.join(cust_dir, "documents")
    index_path = os.path.join(cust_dir, "index.bin")
    docs_path = os.path.join(cust_dir, "docs.pkl")
    config = load_customer_config(client_id)

    files = []
    if os.path.isdir(docs_dir):
        files = sorted(
            fname for fname in os.listdir(docs_dir)
            if os.path.isfile(os.path.join(docs_dir, fname))
        )

    return {
        "client_id": client_id,
        "client_name": config.get("client_name", ""),
        "website_url": config.get("website_url"),
        "documents_dir": docs_dir,
        "files": files,
        "file_count": len(files),
        "index_path": index_path,
        "docs_path": docs_path,
        "vector_ready": os.path.exists(index_path) and os.path.exists(docs_path),
        "updated_at": config.get("updated_at"),
    }
