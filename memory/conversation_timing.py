"""
Pause-aware message buffering for human-like chat timing.

For webhook-style clients, each incoming message can opt into a short debounce
window. If another message arrives for the same user/key before the pause
window ends, the older request returns "listening" and the newest request owns
the combined message.
"""

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class PendingConversation:
    messages: list[str] = field(default_factory=list)
    version: int = 0
    updated_at: float = field(default_factory=time.monotonic)


class ConversationPauseBuffer:
    def __init__(self):
        self._items: dict[str, PendingConversation] = {}
        self._lock = asyncio.Lock()

    async def add_message(self, key: str, message: str) -> int:
        async with self._lock:
            item = self._items.setdefault(key, PendingConversation())
            item.messages.append(message.strip())
            item.version += 1
            item.updated_at = time.monotonic()
            return item.version

    async def wait_for_pause(
        self,
        key: str,
        version: int,
        *,
        pause_seconds: float,
        max_wait_seconds: float,
    ) -> tuple[str, int, bool]:
        started = time.monotonic()
        pause_seconds = max(0.0, min(float(pause_seconds), 90.0))
        max_wait_seconds = max(pause_seconds, min(float(max_wait_seconds), 90.0))

        while True:
            await asyncio.sleep(min(pause_seconds or 0.1, 1.0))
            async with self._lock:
                item = self._items.get(key)
                if item is None:
                    return "", 0, False
                if item.version != version:
                    return "", 0, False

                idle_for = time.monotonic() - item.updated_at
                waited = time.monotonic() - started
                if idle_for >= pause_seconds or waited >= max_wait_seconds:
                    combined = "\n".join(item.messages).strip()
                    count = len(item.messages)
                    self._items.pop(key, None)
                    return combined, count, True
