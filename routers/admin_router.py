"""
routers/admin_router.py
Admin-only endpoints for API key lifecycle management.

All routes require role="admin" via the X-API-Key header.

Endpoints:
  POST   /admin/keys                  — create any key (admin/client/user)
  GET    /admin/keys                  — list all keys (with filters)
  GET    /admin/keys/{key_id}         — get single key details
  PATCH  /admin/keys/{key_id}         — update label/expiry/limit/status
  POST   /admin/keys/{key_id}/revoke  — hard-revoke a key
  POST   /admin/keys/{key_id}/rotate  — rotate (revoke + reissue)
  GET    /admin/usage                 — platform-wide usage log
  GET    /admin/usage/{key_id}        — usage summary for one key
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

from auth.models import APIKey, ROLE_HIERARCHY
from auth.dependencies import require_role, get_key_manager
from auth.key_manager import KeyManager

router = APIRouter(prefix="/admin", tags=["Admin — Key Management"])

_ADMIN = Depends(require_role("admin"))


# ── Request / Response models ─────────────────────────────────────

class CreateKeyRequest(BaseModel):
    role:             str             = Field(...,  description="admin | client | user")
    label:            str             = Field(...,  description="Human-readable name")
    client_id:        Optional[str]   = Field(None, description="Required when role=user")
    expires_in_days:  Optional[int]   = Field(None, description="Days until expiry (None=never)")
    monthly_limit:    Optional[int]   = Field(None, description="Max requests/month (None=unlimited)")
    metadata:         Optional[dict]  = Field(None, description="Free-form extra info")


class UpdateKeyRequest(BaseModel):
    label:         Optional[str]      = None
    expires_at:    Optional[datetime] = None
    monthly_limit: Optional[int]      = None
    is_active:     Optional[bool]     = None
    metadata:      Optional[dict]     = None


# ── POST /admin/keys ──────────────────────────────────────────────

@router.post("/keys", status_code=status.HTTP_201_CREATED)
async def create_key(
    body: CreateKeyRequest,
    caller: APIKey    = _ADMIN,
    km:    KeyManager = Depends(get_key_manager),
):
    """
    Create a new API key (any role).
    The full key value is returned ONCE — store it securely.
    """
    if body.role not in ROLE_HIERARCHY:
        raise HTTPException(400, f"Invalid role. Choose from: {ROLE_HIERARCHY}")

    if body.role == "user" and not body.client_id:
        raise HTTPException(400, "client_id is required when creating a user key")

    result = km.create_key(
        role            = body.role,
        label           = body.label,
        owner_id        = caller.key_id,
        client_id       = body.client_id,
        expires_in_days = body.expires_in_days,
        monthly_limit   = body.monthly_limit,
        metadata        = body.metadata,
    )
    return {
        "status":  "created",
        "message": "⚠️  Store the key now — it will not be shown again.",
        "data":    result,
    }


# ── GET /admin/keys ───────────────────────────────────────────────

@router.get("/keys")
async def list_keys(
    role:        Optional[str]  = Query(None),
    client_id:   Optional[str]  = Query(None),
    active_only: bool           = Query(False),
    skip:        int            = Query(0),
    limit:       int            = Query(50),
    _:    APIKey    = _ADMIN,
    km:   KeyManager = Depends(get_key_manager),
):
    keys = km.list_keys(
        role        = role,
        active_only = active_only,
        client_id   = client_id,
        skip        = skip,
        limit       = limit,
    )
    return {"count": len(keys), "keys": keys}


# ── GET /admin/keys/{key_id} ──────────────────────────────────────

@router.get("/keys/{key_id}")
async def get_key(
    key_id: str,
    _:  APIKey    = _ADMIN,
    km: KeyManager = Depends(get_key_manager),
):
    doc = km.get_key_by_id(key_id)
    if not doc:
        raise HTTPException(404, f"Key '{key_id}' not found")
    return doc


# ── PATCH /admin/keys/{key_id} ────────────────────────────────────

@router.patch("/keys/{key_id}")
async def update_key(
    key_id: str,
    body: UpdateKeyRequest,
    _:  APIKey    = _ADMIN,
    km: KeyManager = Depends(get_key_manager),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update provided")
    ok = km.update_key(key_id, updates)
    if not ok:
        raise HTTPException(404, f"Key '{key_id}' not found or no changes made")
    return {"status": "updated", "key_id": key_id, "updated_fields": list(updates.keys())}


# ── POST /admin/keys/{key_id}/revoke ─────────────────────────────

@router.post("/keys/{key_id}/revoke")
async def revoke_key(
    key_id: str,
    _:  APIKey    = _ADMIN,
    km: KeyManager = Depends(get_key_manager),
):
    ok = km.revoke_key(key_id)
    if not ok:
        raise HTTPException(404, f"Key '{key_id}' not found")
    return {"status": "revoked", "key_id": key_id}


# ── POST /admin/keys/{key_id}/rotate ─────────────────────────────

@router.post("/keys/{key_id}/rotate")
async def rotate_key(
    key_id: str,
    _:  APIKey    = _ADMIN,
    km: KeyManager = Depends(get_key_manager),
):
    """
    Revokes the current key and issues a replacement with the same settings.
    Returns the new key (shown once).
    """
    result = km.rotate_key(key_id)
    if not result:
        raise HTTPException(404, f"Key '{key_id}' not found")
    return {
        "status":  "rotated",
        "message": "⚠️  Old key is revoked. Store the new key now — it will not be shown again.",
        "data":    result,
    }


# ── GET /admin/usage ──────────────────────────────────────────────

@router.get("/usage")
async def platform_usage(
    key_id: Optional[str] = Query(None, description="Filter by a specific key"),
    days:   int           = Query(30),
    limit:  int           = Query(200),
    _:  APIKey    = _ADMIN,
    km: KeyManager = Depends(get_key_manager),
):
    logs = km.get_usage(key_id=key_id, days=days, limit=limit)
    return {"count": len(logs), "days": days, "logs": logs}


# ── GET /admin/usage/{key_id} — summary ──────────────────────────

@router.get("/usage/{key_id}/summary")
async def usage_summary(
    key_id: str,
    days:   int = Query(30),
    _:  APIKey    = _ADMIN,
    km: KeyManager = Depends(get_key_manager),
):
    return km.get_usage_summary(key_id=key_id, days=days)