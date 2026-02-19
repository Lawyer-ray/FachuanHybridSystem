"""Business logic services."""

from __future__ import annotations

from typing import Any, Protocol


class ICaseNumberExtractionProvider(Protocol):
    def extract(self, *, content: str) -> str: ...


class OllamaCaseNumberExtractionProvider:
    def extract(self, *, content: str) -> str:
        from apps.core.llm.config import LLMConfig
        from apps.core.llm.service import get_llm_service

        model = LLMConfig.get_ollama_model()
        messages: list[Any] = []
        llm_service = get_llm_service()
        llm_resp = llm_service.chat(messages=messages, backend="ollama", model=model, fallback=False)
        return llm_resp.content or ""
