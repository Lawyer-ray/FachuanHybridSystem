"""Business logic services."""

from __future__ import annotations

from typing import Any, Protocol


class ICaseNumberExtractionProvider(Protocol):
    def extract(self, *, content: str) -> str: ...


class OllamaCaseNumberExtractionProvider:
    def extract(self, *, content: str) -> str:
        from apps.core.interfaces import ServiceLocator
        from apps.core.llm.config import LLMConfig

        prompt = f"""
请从以下法律文书内容中提取所有案号.

案号格式规则:
1. 标准格式:(年份)法院代码案件类型序号,如:(2024)粤0604民初12345号
2. 简化格式:法院代码案件类型序号,如:粤0604民初12345号
3. 可能包含全角字符,需要识别
4. 案号通常出现在文书开头或标题中

返回 JSON 格式:{{"case_numbers": ["案号1", "案号2"]}}
如果没有找到案号,返回:{{"case_numbers": []}}

文书内容:
{content}
"""

        model = LLMConfig.get_ollama_model()
        messages: list[Any] = []
        llm_service = ServiceLocator.get_llm_service()
        llm_resp = llm_service.chat(messages=messages, backend="ollama", model=model, fallback=False)
        return llm_resp.content or ""
