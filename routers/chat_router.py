"""
routers/chat_router.py
The core /chat endpoint — authenticated, usage-logged, multi-tenant.

Any valid API key (admin / client / user) can use POST /chat.
The api_key_id is threaded into the RAG retriever so the correct
private knowledge base (if any) is searched alongside the default KB.
"""

import time
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from auth.models import APIKey
from auth.dependencies import require_auth, get_key_manager
from auth.key_manager import KeyManager
from memory.mongo_memory import MongoMemory
from memory.customer_config import get_customer_website
from memory.conversation_timing import ConversationPauseBuffer
from main import run_query

router = APIRouter(tags=["Chat"])

_memory = MongoMemory()
_pause_buffer = ConversationPauseBuffer()


# ── Request / Response ────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id:     str
    message:     str
    website_url: Optional[str] = None
    wait_for_pause: bool = False
    pause_window_seconds: float = 2.0
    max_wait_seconds: float = 90.0

class ChatResponse(BaseModel):
    answer:     str
    intent:     str
    rag_band:   str
    session_id: str
    key_prefix: str           # for caller to confirm which key was used
    status: str = "answered"
    combined_message_count: int = 1
    language_profile: dict = Field(default_factory=dict)


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
    result = {}
    success = False
    error = ""

    # Determine which RAG namespace to use
    # - admin/client keys → use their own key_id as the RAG namespace
    # - user keys         → use their parent client_id as the RAG namespace
    rag_api_key = (
        caller.client_id   # user-role: inherit client's RAG
        if caller.role == "user" and caller.client_id
        else caller.key_id  # client/admin: own namespace
    )

    try:
        message = req.message
        combined_message_count = 1
        if req.wait_for_pause:
            pause_window = min(max(req.pause_window_seconds, 0.25), 90.0)
            max_wait = min(max(req.max_wait_seconds, pause_window), 90.0)
            buffer_key = f"{caller.key_id}:{req.user_id}"
            version = await _pause_buffer.add_message(buffer_key, req.message)
            message, combined_message_count, owns_turn = await _pause_buffer.wait_for_pause(
                buffer_key,
                version,
                pause_seconds=pause_window,
                max_wait_seconds=max_wait,
            )
            if not owns_turn:
                success = True
                return ChatResponse(
                    answer="",
                    intent="pending_context",
                    rag_band="pending",
                    session_id=_memory.get_or_create_session(req.user_id),
                    key_prefix=caller.key_prefix,
                    status="listening",
                    combined_message_count=0,
                    language_profile={},
                )

        website_url = req.website_url or get_customer_website(rag_api_key)
        result = await asyncio.to_thread(
            run_query,
            query   = message,
            user_id = req.user_id,
            api_key = rag_api_key,
            website_url = website_url,
        )
        success = True
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
        status     = "answered",
        combined_message_count = combined_message_count,
        language_profile = result.get("language_profile", {}),
    )
