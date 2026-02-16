"""Module for document type parse chain."""

from __future__ import annotations

import logging
from typing import cast

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from apps.core.llm.config import LLMConfig

logger = logging.getLogger(__name__)


class DocumentTypeParseResult(BaseModel):
    document_type: str = Field(default="")
    confidence: float = Field(default=0.0)
    notes: str = Field(default="")


class DocumentTypeParseChain:
    def __init__(self, model: str | None = None) -> None:
        self._model = model

    async def arun(self, *, user_input: str, allowed_types: list[str]) -> DocumentTypeParseResult:
        if not (await LLMConfig.get_api_key_async() or "").strip():
            return self._fallback_parse(user_input=user_input, allowed_types=allowed_types, notes="llm_api_key_missing")

        system_prompt = await self._get_system_prompt()
        try:
            from asgiref.sync import sync_to_async

            from apps.litigation_ai.services.wiring import get_llm_service

            llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()
            llm = await sync_to_async(llm_service.get_langchain_llm, thread_sensitive=True)(model=self._model)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    (
                        "human",
                        "\n".join(
                            [
                                "# 允许的文书类型(英文 code)",
                                "{allowed_types}",
                                "",
                                "# 用户输入",
                                "{user_input}",
                            ]
                        ),
                    ),
                ]
            )
            chain = prompt | llm.with_structured_output(DocumentTypeParseResult)
            result = await chain.ainvoke(
                {"allowed_types": ", ".join(allowed_types or []), "user_input": user_input or ""}
            )
            return cast(DocumentTypeParseResult, result)
        except Exception:
            logger.exception("操作失败")

            return self._fallback_parse(user_input=user_input, allowed_types=allowed_types, notes="llm_call_failed")

    async def _get_system_prompt(self) -> str:
        from asgiref.sync import sync_to_async

        from apps.litigation_ai.services.prompt_template_service import PromptTemplateService

        service = PromptTemplateService()
        template = await sync_to_async(service.get_system_template)("litigation_ai.flow.parse_document_type")
        return template or self._default_prompt()

    def _default_prompt(self) -> str:
        return "\n".join(
            [
                "你是法律助手,负责把用户输入解析为文书类型 code.",
                "文书类型 code 只允许在 allowed_types 内选择:complaint, defense, counterclaim, counterclaim_defense.",
                "用户可能输入中文名称(起诉状/答辩状/反诉状/反诉答辩状)、数字序号(1/2/3/4)、或描述性文字.",
                "如果无法确定,document_type 置空,confidence 置 0,并在 notes 说明原因.",
                "输出必须严格符合结构化字段.",
            ]
        )

    def _fallback_parse(self, *, user_input: str, allowed_types: list[str], notes: str) -> DocumentTypeParseResult:
        text = (user_input or "").strip()
        if not text:
            return DocumentTypeParseResult(document_type="", confidence=0.0, notes=f"{notes}:empty")

        normalized = text.lower().replace(" ", "")
        type_map = [
            ("反诉答辩状", "counterclaim_defense"),
            ("反诉答辩", "counterclaim_defense"),
            ("反诉状", "counterclaim"),
            ("反诉起诉状", "counterclaim"),
            ("答辩状", "defense"),
            ("答辩", "defense"),
            ("起诉状", "complaint"),
            ("起诉书", "complaint"),
            ("起诉", "complaint"),
        ]
        for key, code in type_map:
            if key in text and (not allowed_types or code in allowed_types):
                return DocumentTypeParseResult(document_type=code, confidence=0.9, notes=f"{notes}:keyword:{key}")

        if normalized in {"complaint", "defense", "counterclaim", "counterclaim_defense"} and (
            not allowed_types or normalized in allowed_types
        ):
            return DocumentTypeParseResult(document_type=normalized, confidence=0.95, notes=f"{notes}:code")

        if normalized.isdigit():
            idx = int(normalized) - 1
            if 0 <= idx < len(allowed_types or []):
                return DocumentTypeParseResult(
                    document_type=allowed_types[idx],
                    confidence=0.75,
                    notes=f"{notes}:index:{normalized}",
                )

        return DocumentTypeParseResult(document_type="", confidence=0.0, notes=f"{notes}:unmatched")
