"""
Shared MongoDB connection helper.

The app has multiple modules that need MongoDB at startup. This centralizes the
connection attempt so Atlas/TLS failures are reported once instead of once per
module, and every caller uses the same DB name and TLS options.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config.settings import (
    MONGO_CONNECT_TIMEOUT_MS,
    MONGO_DB_NAME,
    MONGO_SERVER_SELECTION_TIMEOUT_MS,
    MONGO_SOCKET_TIMEOUT_MS,
    MONGO_TLS_ALLOW_INVALID_CERTIFICATES,
    MONGO_URI,
)


@dataclass
class MongoConnection:
    ok: bool
    client: Optional[MongoClient] = None
    db: object = None
    error: str = ""


_status_printed = False


def _mongo_options() -> dict:
    options = {
        "serverSelectionTimeoutMS": MONGO_SERVER_SELECTION_TIMEOUT_MS,
        "connectTimeoutMS": MONGO_CONNECT_TIMEOUT_MS,
        "socketTimeoutMS": MONGO_SOCKET_TIMEOUT_MS,
        "tls": True,
        "tlsAllowInvalidCertificates": MONGO_TLS_ALLOW_INVALID_CERTIFICATES,
    }

    try:
        import certifi
        options["tlsCAFile"] = certifi.where()
    except Exception:
        pass

    return options


def _short_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ")
    if "SSL handshake failed" in text:
        return (
            "SSL handshake failed before MongoDB authentication. Check MongoDB "
            "Atlas Network Access/IP allowlist, outbound access to port 27017, "
            "and any proxy/firewall TLS inspection."
        )
    if "All nameservers failed" in text or "DNS" in text:
        return "DNS resolution failed for the MongoDB Atlas SRV record."
    first = text.split("Topology Description:", 1)[0].strip()
    return first[:700]


@lru_cache(maxsize=1)
def get_mongo_connection() -> MongoConnection:
    if not MONGO_URI:
        return MongoConnection(ok=False, error="MONGO_URI is not set")

    try:
        client = MongoClient(MONGO_URI, **_mongo_options())
        client.admin.command("ping")
        return MongoConnection(ok=True, client=client, db=client[MONGO_DB_NAME])
    except PyMongoError as e:
        return MongoConnection(ok=False, error=_short_error(e))


def mongo_health_summary() -> str:
    conn = get_mongo_connection()
    if conn.ok:
        return f"MongoDB connected: database={MONGO_DB_NAME}"
    return f"MongoDB unavailable: {conn.error}"


def print_mongo_status_once() -> None:
    global _status_printed
    if _status_printed:
        return

    conn = get_mongo_connection()
    if conn.ok:
        print(f"✅ MongoDB connected: database={MONGO_DB_NAME}")
    else:
        print(
            "⚠️  MongoDB unavailable; features that require persistence are disabled: "
            f"{conn.error}"
        )
    _status_printed = True
