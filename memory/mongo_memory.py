"""
memory/mongo_memory.py
Persistent memory layer: conversation history, sessions, agent checkpoints.
Direct MongoDB connection (no MCP needed — MCP is better suited for external
integrations; direct pymongo is simpler and faster for in-process state).
"""

import uuid
from datetime import datetime, UTC
from typing import Optional
from pymongo import MongoClient, DESCENDING
from pymongo.errors import ConnectionFailure
from config.settings import (
    MONGO_URI, MONGO_DB_NAME,
    MONGO_CONV_COLLECTION, MONGO_SESSION_COLLECTION, MONGO_CHECKPOINT_COLLECTION
)


class MongoMemory:
    """
    Handles all persistent state for the YoWhats agent:
      - Session tracking
      - Full conversation history per user
      - Agent reasoning checkpoints (for ReAct replay / audit)
    """

    def __init__(self):
        try:
            self._client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            self._client.admin.command("ping")
            self._db = self._client[MONGO_DB_NAME]
            self._conv = self._db[MONGO_CONV_COLLECTION]
            self._sessions = self._db[MONGO_SESSION_COLLECTION]
            self._checkpoints = self._db[MONGO_CHECKPOINT_COLLECTION]
            print("✅ MongoDB connected")
        except ConnectionFailure as e:
            print(f"⚠️  MongoDB unavailable → memory disabled: {e}")
            self._db = None

    # ─────────────────────── Session ───────────────────────

    def get_or_create_session(self, user_id: str) -> str:
        """Return active session_id for user, or create a new one."""
        if self._db is None:
            return str(uuid.uuid4())

        doc = self._sessions.find_one({"user_id": user_id, "active": True})
        if doc:
            return doc["session_id"]

        session_id = str(uuid.uuid4())
        self._sessions.insert_one({
            "user_id": user_id,
            "session_id": session_id,
            "active": True,
            "created_at": datetime.now(UTC),
        })
        return session_id

    def close_session(self, user_id: str):
        if self._db is None:
            return
        self._sessions.update_many(
            {"user_id": user_id, "active": True},
            {"$set": {"active": False, "closed_at": datetime.now(UTC)}}
        )

    # ─────────────────────── Messages ───────────────────────

    def add_message(self, user_id: str, session_id: str, role: str, content: str):
        """Persist a single message turn."""
        if self._db is None:
            return
        self._conv.insert_one({
            "user_id": user_id,
            "session_id": session_id,
            "role": role,           # "user" | "assistant"
            "content": content,
            "ts": datetime.now(UTC),
        })

    def get_history(self, user_id: str, session_id: str, limit: int = 10) -> list[dict]:
        """Retrieve last N turns for context injection."""
        if self._db is None:
            return []
        cursor = (
            self._conv
            .find({"user_id": user_id, "session_id": session_id})
            .sort("ts", DESCENDING)
            .limit(limit)
        )
        msgs = list(cursor)
        msgs.reverse()   # chronological order
        return [{"role": m["role"], "content": m["content"]} for m in msgs]

    # ─────────────────────── Checkpoints ────────────────────

    def save_checkpoint(self, user_id: str, session_id: str, step: dict):
        """
        Save an agent reasoning step (ReAct style):
          step = {
            "action": "retrieve_rag" | "web_search" | "generate" | ...,
            "input": ...,
            "output": ...,
            "confidence": float,
            "sources": [...],
          }
        """
        if self._db is None:
            return
        self._checkpoints.insert_one({
            "user_id": user_id,
            "session_id": session_id,
            "ts": datetime.now(UTC),
            **step,
        })

    def get_checkpoints(self, session_id: str) -> list[dict]:
        if not self._db:
            return []
        return list(self._checkpoints.find({"session_id": session_id}).sort("ts", 1))