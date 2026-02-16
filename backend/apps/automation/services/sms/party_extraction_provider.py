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
        from apps.core.interfaces import ServiceLocator
        from apps.core.llm.config import LLMConfig

        prompt = (
            "请从以下法院短信中提取所有当事人名称.\n\n"
            "规则:\n"
            "1. 当事人可以是自然人或法人\n"
            "2. 必须排除法院名称、法官/书记员、系统/平台名、非当事人地名机构名\n"
            '3. 返回 JSON 格式:{"parties": ["当事人1", "当事人2"]}\n'
            '4. 如果没有找到明确的当事人,返回:{"parties": []}\n\n'
            f"短信内容:\n{content}\n"
        )

        model = self._model or LLMConfig.get_ollama_model()
        messages: list[Any] = []
        llm_service = ServiceLocator.get_llm_service()
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
