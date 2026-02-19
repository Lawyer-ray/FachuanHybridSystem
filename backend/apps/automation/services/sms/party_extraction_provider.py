"""Business logic services."""

from __future__ import annotations

import json
from typing import Any, Protocol


class IPartyExtractionProvider(Protocol):
    def extract(self, *, content: str) -> list[str]: ...


class OllamaPartyExtractionProvider:
    def __init__(self, *, model: str | None = None, base_url: str | None = None) -> None:
        self._model = model
        self._base_url = base_url

    def extract(self, *, content: str) -> list[str]:
        from apps.core.llm.config import LLMConfig
        from apps.core.llm.service import get_llm_service

        model = self._model or LLMConfig.get_ollama_model()
        messages: list[Any] = []
        llm_service = get_llm_service()
        llm_resp = llm_service.chat(messages=messages, backend="ollama", model=model, fallback=False)
        content_text = llm_resp.content or ""
        try:
            result = json.loads(content_text)
        except json.JSONDecodeError:
            return []
        parties = result.get("parties", [])
        if not isinstance(parties, list):
            return []
        out: list[str] = []
        for p in parties:
            if isinstance(p, str) and p.strip():
                out.append(p.strip())
        return out
