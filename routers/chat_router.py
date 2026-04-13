"""
routers/chat_router.py
The core /chat endpoint — authenticated, usage-logged, multi-tenant.

Any valid API key (admin / client / user) can use POST /chat.
The api_key_id is threaded into the RAG retriever so the correct
private knowledge base (if any) is searched alongside the default KB.
"""

import time
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from auth.models import APIKey
from auth.dependencies import require_auth, get_key_manager
from auth.key_manager import KeyManager
from memory.mongo_memory import MongoMemory
from main import run_query

router = APIRouter(tags=["Chat"])

_memory = MongoMemory()


# ── Request / Response ────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id:  str             # end-user identifier (e.g. WhatsApp number)
    message:  str


class ChatResponse(BaseModel):
    answer:     str
    intent:     str
    rag_band:   str
    session_id: str
    key_prefix: str           # for caller to confirm which key was used


# ── POST /chat ────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req:    ChatRequest,
    caller: APIKey    = Depends(require_auth),
    km:     KeyManager = Depends(get_key_manager),
):
    if not req.message.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty message")

    t0 = time.time()

    # Determine which RAG namespace to use
    # - admin/client keys → use their own key_id as the RAG namespace
    # - user keys         → use their parent client_id as the RAG namespace
    rag_api_key = (
        caller.client_id   # user-role: inherit client's RAG
        if caller.role == "user" and caller.client_id
        else caller.key_id  # client/admin: own namespace
    )

    try:
        result = run_query(
            query   = req.message,
            user_id = req.user_id,
            api_key = rag_api_key,
        )
        success = True
        error   = ""
    except Exception as e:
        success = False
        error   = str(e)
        raise HTTPException(500, f"Agent error: {e}") from e
    finally:
        elapsed_ms = int((time.time() - t0) * 1000)
        km.log_usage(
            key_id      = caller.key_id,
            key_prefix  = caller.key_prefix,
            role        = caller.role,
            endpoint    = "/chat",
            user_id     = req.user_id,
            response_ms = elapsed_ms,
            intent      = result.get("intent", "")   if success else "",
            rag_band    = result.get("rag_band", "") if success else "",
            success     = success,
            error       = error,
        )

    session_id = _memory.get_or_create_session(req.user_id)

    return ChatResponse(
        answer     = result["answer"],
        intent     = result.get("intent",   "general_ecommerce"),
        rag_band   = result.get("rag_band", "low"),
        session_id = session_id,
        key_prefix = caller.key_prefix,
    )