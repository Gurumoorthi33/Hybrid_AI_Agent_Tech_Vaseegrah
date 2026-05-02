"""
routers/client_router.py
Client-role endpoints — clients manage their own user keys and view own usage.

All routes require role="client" (or "admin") via X-API-Key header.

Endpoints:
  POST  /client/keys              — create a user key under this client
  GET   /client/keys              — list own user keys
  POST  /client/keys/{key_id}/revoke  — revoke own user key
  GET   /client/usage             — own usage summary
  POST  /client/ingest            — upload RAG file for this client's namespace
"""

import os, shutil, tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from pydantic import BaseModel, Field
from typing import Optional

from auth.models import APIKey
from auth.dependencies import require_role, get_key_manager
from auth.key_manager import KeyManager
from memory.ingestor import ingest_customer_file

router = APIRouter(prefix="/client", tags=["Client — Key & RAG Management"])

_CLIENT_OR_ADMIN = Depends(require_role("client", "admin"))


# ── Request models ────────────────────────────────────────────────

class CreateUserKeyRequest(BaseModel):
    label:          str            = Field(..., description="e.g. 'WhatsApp user +91...'")
    expires_in_days: Optional[int] = Field(None)
    monthly_limit:  Optional[int]  = Field(None)
    metadata:       Optional[dict] = Field(None)


# ── POST /client/keys ─────────────────────────────────────────────

@router.post("/keys", status_code=status.HTTP_201_CREATED)
async def create_user_key(
    body:   CreateUserKeyRequest,
    caller: APIKey    = _CLIENT_OR_ADMIN,
    km:     KeyManager = Depends(get_key_manager),
):
    """Create a user-level API key scoped to this client."""
    client_id = caller.key_id if caller.role == "client" else body.metadata.get("client_id") if body.metadata else None
    if not client_id:
        raise HTTPException(400, "client_id could not be determined")

    result = km.create_key(
        role            = "user",
        label           = body.label,
        owner_id        = caller.key_id,
        client_id       = client_id,
        expires_in_days = body.expires_in_days,
        monthly_limit   = body.monthly_limit,
        metadata        = body.metadata,
    )
    return {
        "status":  "created",
        "message": "⚠️  Store the key now — it will not be shown again.",
        "data":    result,
    }


# ── GET /client/keys ──────────────────────────────────────────────

@router.get("/keys")
async def list_user_keys(
    active_only: bool = Query(False),
    skip:  int = Query(0),
    limit: int = Query(50),
    caller: APIKey    = _CLIENT_OR_ADMIN,
    km:     KeyManager = Depends(get_key_manager),
):
    """List all user keys owned by this client."""
    client_id = caller.key_id if caller.role == "client" else None
    keys = km.list_keys(
        role        = "user",
        client_id   = client_id,
        active_only = active_only,
        skip        = skip,
        limit       = limit,
    )
    return {"count": len(keys), "keys": keys}


# ── POST /client/keys/{key_id}/revoke ────────────────────────────

@router.post("/keys/{key_id}/revoke")
async def revoke_user_key(
    key_id: str,
    caller: APIKey    = _CLIENT_OR_ADMIN,
    km:     KeyManager = Depends(get_key_manager),
):
    """Revoke a user key — only if it belongs to this client."""
    doc = km.get_key_by_id(key_id)
    if not doc:
        raise HTTPException(404, "Key not found")

    if caller.role == "client" and doc.get("client_id") != caller.key_id:
        raise HTTPException(403, "You can only revoke user keys that belong to your account")

    ok = km.revoke_key(key_id)
    return {"status": "revoked", "key_id": key_id} if ok else HTTPException(500, "Revoke failed")


# ── GET /client/usage ─────────────────────────────────────────────

@router.get("/usage")
async def client_usage(
    days:  int = Query(30),
    limit: int = Query(100),
    caller: APIKey    = _CLIENT_OR_ADMIN,
    km:     KeyManager = Depends(get_key_manager),
):
    """Usage summary for this client's own key."""
    summary = km.get_usage_summary(key_id=caller.key_id, days=days)
    logs    = km.get_usage(key_id=caller.key_id, days=days, limit=limit)
    return {"summary": summary, "logs": logs}


# ── POST /client/ingest ───────────────────────────────────────────

@router.post("/ingest")
async def ingest_rag_file(
    file:   UploadFile = File(...),
    caller: APIKey    = _CLIENT_OR_ADMIN,
):
    """
    Upload a custom RAG knowledge file for this client.
    The file is ingested into data/customers/<key_id>/ — isolated per client.
    """
    allowed_exts = {".txt", ".pdf", ".md", ".csv"}
    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {allowed_exts}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        doc_count = ingest_customer_file(caller.key_id, tmp_path)
    finally:
        os.unlink(tmp_path)

    return {
        "status":  "ok",
        "message": f"File '{file.filename}' ingested into your private knowledge base.",
        "key_id":  caller.key_id,
        "chunks":  doc_count,
    }
