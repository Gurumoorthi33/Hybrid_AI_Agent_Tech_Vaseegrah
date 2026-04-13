"""
auth/key_manager.py
All API key lifecycle operations — create, validate, revoke, rotate, list, usage logging.

Key format:
  ywk_live_<role_char><32 random hex chars>
  e.g.  ywk_live_a1b2c3d4e5f6...   (admin)
        ywk_live_c1b2c3d4e5f6...   (client)
        ywk_live_u1b2c3d4e5f6...   (user)

We store only the SHA-256 hash in the DB.
The full key is returned exactly ONCE — at creation time.
"""

import os
import secrets
import hashlib
import uuid
from datetime import datetime, UTC, timedelta
from typing import Optional
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, PyMongoError
from pymongo.read_preferences import SecondaryPreferred

from auth.models import APIKey, ROLE_HIERARCHY
from config.settings import MONGO_URI, MONGO_DB_NAME

# MongoDB collection names
KEYS_COLLECTION  = "api_keys"
USAGE_COLLECTION = "usage_logs"

# Role prefix chars embedded in the key for quick visual identification
ROLE_CHAR = {"admin": "a", "client": "c", "user": "u"}


class KeyManager:
    """
    Singleton-friendly class that manages all API key operations.
    Gracefully degrades when MongoDB is unavailable.
    """

    def __init__(self):
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            db = client[MONGO_DB_NAME]
            self._client = client
            self._keys  = db[KEYS_COLLECTION]
            self._usage = db[USAGE_COLLECTION]
            self._keys_read = self._keys.with_options(read_preference=SecondaryPreferred())
            self._usage_read = self._usage.with_options(read_preference=SecondaryPreferred())
            self._ok    = True
            self._ensure_indexes()
            print("✅ KeyManager connected to MongoDB")
        except (ConnectionFailure, PyMongoError) as e:
            print(f"⚠️  KeyManager: MongoDB unavailable — {e}")
            self._ok = False
            self._client = None
            self._keys = None
            self._usage = None
            self._keys_read = None
            self._usage_read = None

    # ── indexes ───────────────────────────────────────────────────

    def _ensure_indexes(self):
        self._keys.create_index( [("key_hash", ASCENDING)], unique=True)
        self._keys.create_index( [("role",     ASCENDING)])
        self._keys.create_index( [("owner_id", ASCENDING)])
        self._keys.create_index( [("client_id",ASCENDING)])
        self._usage.create_index([("key_id",   ASCENDING)])
        self._usage.create_index([("ts",       DESCENDING)])

    # ── key generation helpers ────────────────────────────────────

    @staticmethod
    def _generate_raw_key(role: str) -> str:
        rc  = ROLE_CHAR.get(role, "x")
        rnd = secrets.token_hex(32)        # 64 hex chars = 256 bits entropy
        return f"ywk_live_{rc}{rnd}"

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _prefix(key: str) -> str:
        """Display-safe prefix: first 16 chars + ****"""
        return key[:16] + "****"

    # ── create ────────────────────────────────────────────────────

    def create_key(
        self,
        role:          str,
        label:         str,
        owner_id:      Optional[str]  = None,
        client_id:     Optional[str]  = None,
        expires_in_days: Optional[int] = None,
        monthly_limit: Optional[int]  = None,
        metadata:      Optional[dict] = None,
    ) -> dict:
        """
        Generate a new API key.
        Returns { "key": <full key — show once>, "key_id": ..., ...safe fields }

        Rules enforced by callers (routers), not here:
          - Only admins can create client keys
          - Only admins/clients can create user keys
          - client_id must be provided when role == "user"
        """
        if role not in ROLE_HIERARCHY:
            raise ValueError(f"Invalid role '{role}'. Must be one of {ROLE_HIERARCHY}")

        raw_key = self._generate_raw_key(role)
        key_id  = str(uuid.uuid4())
        now     = datetime.now(UTC)

        doc = {
            "key_id":        key_id,
            "key_hash":      self._hash(raw_key),
            "key_prefix":    self._prefix(raw_key),
            "role":          role,
            "label":         label,
            "owner_id":      owner_id,
            "client_id":     client_id,
            "is_active":     True,
            "created_at":    now,
            "expires_at":    (now + timedelta(days=expires_in_days)) if expires_in_days else None,
            "last_used_at":  None,
            "usage_count":   0,
            "monthly_limit": monthly_limit,
            "metadata":      metadata or {},
        }

        if self._ok:
            self._keys.insert_one(doc)

        # Return the full key ONCE — it is never retrievable again
        return {
            "key":           raw_key,          # ← show to user now, never again
            "key_id":        key_id,
            "key_prefix":    doc["key_prefix"],
            "role":          role,
            "label":         label,
            "owner_id":      owner_id,
            "client_id":     client_id,
            "is_active":     True,
            "created_at":    now.isoformat(),
            "expires_at":    doc["expires_at"].isoformat() if doc["expires_at"] else None,
            "monthly_limit": monthly_limit,
            "metadata":      metadata or {},
        }

    # ── validate ──────────────────────────────────────────────────

    def validate_key(self, raw_key: str) -> Optional[APIKey]:
        """
        Validate an incoming API key.
        Returns an APIKey dataclass if valid and active, None otherwise.
        Also increments usage_count and updates last_used_at.
        """
        if not raw_key or not raw_key.startswith("ywk_live_"):
            return None

        key_hash = self._hash(raw_key)

        if not self._ok:
            # Offline fallback — allow root admin key from env
            root = os.getenv("ROOT_ADMIN_KEY", "")
            if root and raw_key == root:
                return APIKey(
                    key_id="root", key=raw_key, key_prefix="root",
                    key_hash=key_hash, role="admin", label="Root Admin",
                    owner_id=None, client_id=None, is_active=True,
                    created_at=datetime.now(UTC), expires_at=None,
                    last_used_at=None, usage_count=0, monthly_limit=None,
                )
            return None

        doc = self._keys.find_one({"key_hash": key_hash})
        if not doc:
            return None

        now = datetime.now(UTC)

        # Check active flag
        if not doc["is_active"]:
            return None

        # Check expiry
        if doc.get("expires_at") and doc["expires_at"] < now:
            # Auto-deactivate
            self._keys.update_one({"key_hash": key_hash}, {"$set": {"is_active": False}})
            return None

        # Check monthly limit
        if doc.get("monthly_limit"):
            # Count usage this calendar month
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            monthly_use = self._usage.count_documents({
                "key_id": doc["key_id"],
                "ts":     {"$gte": month_start},
                "success": True,
            })
            if monthly_use >= doc["monthly_limit"]:
                return None

        # Update last_used_at and increment counter
        self._keys.update_one(
            {"key_hash": key_hash},
            {"$set": {"last_used_at": now}, "$inc": {"usage_count": 1}},
        )

        return APIKey(
            key_id        = doc["key_id"],
            key           = raw_key,
            key_prefix    = doc["key_prefix"],
            key_hash      = doc["key_hash"],
            role          = doc["role"],
            label         = doc["label"],
            owner_id      = doc.get("owner_id"),
            client_id     = doc.get("client_id"),
            is_active     = doc["is_active"],
            created_at    = doc["created_at"],
            expires_at    = doc.get("expires_at"),
            last_used_at  = now,
            usage_count   = doc["usage_count"] + 1,
            monthly_limit = doc.get("monthly_limit"),
            metadata      = doc.get("metadata", {}),
        )

    # ── revoke / update ───────────────────────────────────────────

    def revoke_key(self, key_id: str) -> bool:
        if not self._ok:
            return False
        res = self._keys.update_one(
            {"key_id": key_id},
            {"$set": {"is_active": False, "revoked_at": datetime.now(UTC)}},
        )
        return res.modified_count > 0

    def update_key(self, key_id: str, updates: dict) -> bool:
        """
        Allowed updatable fields: label, expires_at, monthly_limit,
        is_active, metadata.
        """
        allowed = {"label", "expires_at", "monthly_limit", "is_active", "metadata"}
        safe    = {k: v for k, v in updates.items() if k in allowed}
        if not safe or not self._ok:
            return False
        safe["updated_at"] = datetime.now(UTC)
        res = self._keys.update_one({"key_id": key_id}, {"$set": safe})
        return res.modified_count > 0

    def rotate_key(self, key_id: str) -> Optional[dict]:
        """
        Invalidate the current key and issue a new one with the same settings.
        Returns new key dict (full key shown once) or None on failure.
        """
        if not self._ok:
            return None
        doc = self._keys.find_one({"key_id": key_id})
        if not doc:
            return None

        # Revoke old
        self.revoke_key(key_id)

        # Create replacement
        return self.create_key(
            role          = doc["role"],
            label         = doc["label"] + " (rotated)",
            owner_id      = doc.get("owner_id"),
            client_id     = doc.get("client_id"),
            monthly_limit = doc.get("monthly_limit"),
            metadata      = doc.get("metadata", {}),
        )

    # ── list / get ────────────────────────────────────────────────

    def get_key_by_id(self, key_id: str) -> Optional[dict]:
        if not self._ok:
            return None
        doc = self._keys.find_one({"key_id": key_id}, {"key_hash": 0})
        return doc

    def list_keys(
        self,
        role:      Optional[str] = None,
        owner_id:  Optional[str] = None,
        client_id: Optional[str] = None,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        if not self._ok:
            return []
        query: dict = {}
        if role:      query["role"]      = role
        if owner_id:  query["owner_id"]  = owner_id
        if client_id: query["client_id"] = client_id
        if active_only: query["is_active"] = True

        try:
            collection = self._keys_read if self._keys_read is not None else self._keys
            docs = (
                collection
                .find(query, {"key_hash": 0})  # never return hash
                .sort("created_at", DESCENDING)
                .skip(skip)
                .limit(limit)
            )
            return [_clean(d) for d in docs]
        except PyMongoError as e:
            print(f"⚠️  KeyManager read error in list_keys — {e}")
            return []

    # ── usage logging ─────────────────────────────────────────────

    def log_usage(self, key_id: str, key_prefix: str, role: str, endpoint: str,
                  user_id: str, response_ms: int, intent: str = "",
                  rag_band: str = "", success: bool = True, error: str = "") -> None:
        if not self._ok:
            return
        self._usage.insert_one({
            "key_id":       key_id,
            "key_prefix":   key_prefix,
            "role":         role,
            "endpoint":     endpoint,
            "user_id":      user_id,
            "ts":           datetime.now(UTC),
            "response_ms":  response_ms,
            "intent":       intent,
            "rag_band":     rag_band,
            "success":      success,
            "error":        error or None,
        })

    def get_usage(
        self,
        key_id:    Optional[str] = None,
        owner_id:  Optional[str] = None,
        days: int  = 30,
        limit: int = 200,
    ) -> list[dict]:
        if not self._ok:
            return []
        since = datetime.now(UTC) - timedelta(days=days)
        query: dict = {"ts": {"$gte": since}}
        if key_id:   query["key_id"]  = key_id
        try:
            collection = self._usage_read if self._usage_read is not None else self._usage
            docs = (
                collection
                .find(query, {"_id": 0})
                .sort("ts", DESCENDING)
                .limit(limit)
            )
            return [_clean(d) for d in docs]
        except PyMongoError as e:
            print(f"⚠️  KeyManager read error in get_usage — {e}")
            return []

    def get_usage_summary(self, key_id: str, days: int = 30) -> dict:
        """Aggregated usage stats for a single key."""
        if not self._ok:
            return {}
        since = datetime.now(UTC) - timedelta(days=days)
        pipeline = [
            {"$match": {"key_id": key_id, "ts": {"$gte": since}}},
            {"$group": {
                "_id":          None,
                "total":        {"$sum": 1},
                "successes":    {"$sum": {"$cond": ["$success", 1, 0]}},
                "errors":       {"$sum": {"$cond": ["$success", 0, 1]}},
                "avg_ms":       {"$avg": "$response_ms"},
                "intents":      {"$push": "$intent"},
            }},
        ]
        result = list(self._usage.aggregate(pipeline))
        if not result:
            return {"total": 0, "successes": 0, "errors": 0, "avg_ms": 0}
        r = result[0]
        from collections import Counter
        return {
            "total":     r["total"],
            "successes": r["successes"],
            "errors":    r["errors"],
            "avg_ms":    round(r.get("avg_ms") or 0, 1),
            "top_intents": dict(Counter(r["intents"]).most_common(5)),
        }

    # ── bootstrap root admin ──────────────────────────────────────

    def bootstrap_root_admin(self) -> Optional[dict]:
        """
        Create the very first admin key if no admin keys exist.
        Called once at server startup. Returns key dict or None.
        """
        if not self._ok:
            return None
        count = self._keys.count_documents({"role": "admin"})
        if count > 0:
            print("✅ Admin keys already exist — skipping bootstrap")
            return None
        result = self.create_key(
            role     = "admin",
            label    = "Root Admin (auto-generated)",
            owner_id = None,
        )
        print(f"🔑 ROOT ADMIN KEY CREATED — save this, it won't be shown again:")
        print(f"   {result['key']}")
        return result


# ── helpers ───────────────────────────────────────────────────────

def _clean(doc: dict) -> dict:
    """Convert ObjectId + datetime to JSON-safe types."""
    out = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out