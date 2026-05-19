"""
OpenAI client adapter.

The agents in this project use a small messages API shape. This adapter keeps
those call sites stable while routing requests to OpenAI chat completions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass
class _TextBlock:
    text: str


@dataclass
class _MessageResponse:
    content: list[_TextBlock]


class _MessagesAdapter:
    def __init__(self, client: OpenAI) -> None:
        self._client = client

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict[str, Any]],
        system: str | None = None,
        **kwargs: Any,
    ) -> _MessageResponse:
        openai_messages: list[dict[str, Any]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(messages)

        response = self._client.chat.completions.create(
            model=model,
            messages=openai_messages,
            max_tokens=max_tokens,
            **kwargs,
        )
        text = response.choices[0].message.content or ""
        return _MessageResponse(content=[_TextBlock(text=text)])


class OpenAIMessageClient:
    def __init__(self, api_key: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self.messages = _MessagesAdapter(self._client)
