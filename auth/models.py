"""
auth/models.py
Data models for the API key system.

MongoDB collection: api_keys
Document schema:
{
    "_id":           ObjectId,
    "key":           str,          # the actual key string  ywk_live_...
    "key_prefix":    str,          # first 12 chars for display  ywk_live_xxxx
    "key_hash":      str,          # SHA-256 hash — we never store the plaintext again
    "role":          str,          # "admin" | "client" | "user"
    "label":         str,          # human-readable name  e.g. "Acme Corp Production"
    "owner_id":      str,          # admin key_id that created this  (null for root admin)
    "client_id":     str | None,   # for user-role keys: which client they belong to
    "is_active":     bool,
    "created_at":    datetime,
    "expires_at":    datetime | None,
    "last_used_at":  datetime | None,
    "usage_count":   int,
    "monthly_limit": int | None,   # None = unlimited
    "metadata":      dict,         # free-form  e.g. {"whatsapp_number": "+91..."}
}

MongoDB collection: usage_logs
Document schema:
{
    "key_id":        str,
    "key_prefix":    str,
    "role":          str,
    "endpoint":      str,          # "/chat" | "/ingest" | etc.
    "user_id":       str,
    "ts":            datetime,
    "response_ms":   int,
    "intent":        str,
    "rag_band":      str,
    "success":       bool,
    "error":         str | None,
}
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class APIKey:
    key_id:        str
    key:           str                  # full key — returned ONCE at creation only
    key_prefix:    str                  # display prefix  ywk_live_xxxx****
    key_hash:      str                  # SHA-256
    role:          str                  # "admin" | "client" | "user"
    label:         str
    owner_id:      Optional[str]        # which admin created this
    client_id:     Optional[str]        # for user keys: parent client key_id
    is_active:     bool
    created_at:    datetime
    expires_at:    Optional[datetime]
    last_used_at:  Optional[datetime]
    usage_count:   int
    monthly_limit: Optional[int]
    metadata:      dict = field(default_factory=dict)

    def to_safe_dict(self) -> dict:
        """Return a dict safe to send back to API callers — no hash, no full key."""
        return {
            "key_id":        self.key_id,
            "key_prefix":    self.key_prefix,
            "role":          self.role,
            "label":         self.label,
            "owner_id":      self.owner_id,
            "client_id":     self.client_id,
            "is_active":     self.is_active,
            "created_at":    self.created_at.isoformat(),
            "expires_at":    self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at":  self.last_used_at.isoformat() if self.last_used_at else None,
            "usage_count":   self.usage_count,
            "monthly_limit": self.monthly_limit,
            "metadata":      self.metadata,
        }


# Role hierarchy — higher index = more permissions
ROLE_HIERARCHY = ["user", "client", "admin"]

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        # key management
        "key:create_any",
        "key:list_all",
        "key:revoke_any",
        "key:update_any",
        # chat & rag
        "chat:use",
        "rag:ingest",
        "rag:ingest_any",
        # history & monitoring
        "history:read_any",
        "usage:read_any",
        # agentic flows
        "agent:email",
        "agent:calendar",
        "agent:automation",
    },
    "client": {
        # key management (own users only)
        "key:create_user",
        "key:list_own_users",
        "key:revoke_own_user",
        # chat & rag
        "chat:use",
        "rag:ingest",
        # history (own users only)
        "history:read_own",
        "usage:read_own",
    },
    "user": {
        "chat:use",
        "history:read_own",
    },
}


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())