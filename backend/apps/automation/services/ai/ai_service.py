"""Business logic services."""

from __future__ import annotations

from typing import Any


class AIService:
    def __init__(self, *, llm_service: Any) -> None:
        self._llm_service = llm_service

    def chat_with_ollama(self, *, model: str, prompt: str, text: str) -> dict[str, Any]:
        messages: list[Any] = []
        resp = self._llm_service.chat(messages=messages, backend="ollama", model=model, fallback=False)
        return {
            "backend": "ollama",
            "model": model,
            "content": resp.content,
            "raw": getattr(resp, "raw", None),
        }

    def chat_with_moonshot(self, *, model: str, prompt: str, text: str) -> dict[str, Any]:
        messages: list[Any] = []
        resp = self._llm_service.chat(messages=messages, backend="moonshot", model=model, fallback=False)
        return {
            "backend": "moonshot",
            "model": model,
            "content": resp.content,
            "raw": getattr(resp, "raw", None),
        }
