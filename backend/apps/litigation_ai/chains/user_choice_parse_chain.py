"""Module for user choice parse chain."""

from __future__ import annotations

import logging

from apps.core.llm.config import LLMConfig
from apps.core.llm.structured_output import json_schema_instructions, parse_model_content

from .goal_schemas import UserChoiceResult

logger = logging.getLogger("apps.litigation_ai")


class UserChoiceParseChain:
    def __init__(self, model: str | None = None) -> None:
        self._model = model

    async def arun(
        self,
        *,
        user_input: str,
        primary_document_type: str,
        optional_document_types: list[str],
    ) -> UserChoiceResult:
        if not (await LLMConfig.get_api_key_async() or "").strip():
            return self._fallback_parse(
                user_input=user_input,
                primary_document_type=primary_document_type,
                optional_document_types=optional_document_types,
                notes="llm_api_key_missing",
            )

        system_prompt = await self._get_system_prompt()
        try:
            from asgiref.sync import sync_to_async

            from apps.litigation_ai.services.wiring import get_llm_service

            llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()
            messages = [
                {
                    "role": "system",
                    "content": "\n\n".join([system_prompt, json_schema_instructions(UserChoiceResult)]),
                },
                {
                    "role": "user",
                    "content": "\n".join(
                        [
                            "# 默认要生成的文书",
                            primary_document_type,
                            "",
                            "# 可选的额外文书",
                            ", ".join(optional_document_types),
                            "",
                            "# 用户输入",
                            user_input or "",
                        ]
                    ),
                },
            ]
            llm_resp = await llm_service.achat(messages=messages, model=self._model, temperature=0.0)
            return parse_model_content(llm_resp.content, UserChoiceResult)
        except Exception:
            logger.exception("操作失败")

            return self._fallback_parse(
                user_input=user_input,
                primary_document_type=primary_document_type,
                optional_document_types=optional_document_types,
                notes="llm_call_failed",
            )

    async def _get_system_prompt(self) -> str:
        from asgiref.sync import sync_to_async

        from apps.litigation_ai.services.prompt_template_service import PromptTemplateService

        service = PromptTemplateService()
        template = await sync_to_async(service.get_system_template)("litigation_ai.flow.parse_user_choice")
        return template or self._default_prompt()

    def _default_prompt(self) -> str:
        return "\n".join(
            [
                "你是法律助理,负责解析用户对“是否需要额外生成文书/是否都要/先生成哪个”的自然语言选择.",
                "primary_document_type:用户当前要生成的文书类型(若用户未明确改变,则使用默认).",
                "pending_document_types:用户确认需要额外生成的文书类型列表(不包含 primary_document_type).",
                "用户表达“都要/一起/两个都生成”时,应把可选文书加入 pending_document_types.",
                "用户表达“不需要/不要/先不做”时,pending_document_types 为空.",
                "notes 用于说明解析依据,简短即可.",
                "输出必须严格符合结构化字段.",
            ]
        )

    def _fallback_parse(
        self,
        *,
        user_input: str,
        primary_document_type: str,
        optional_document_types: list[str],
        notes: str,
    ) -> UserChoiceResult:
        text = (user_input or "").strip()
        normalized = text.replace(" ", "")

        def _contains_any(keys: list[str]) -> bool:
            return any(k in normalized for k in keys)

        pending: list[str] = []
        chosen_primary = primary_document_type or ""

        if _contains_any(["都要", "一起", "全部", "全都", "两个都", "都生成"]):
            pending = list(optional_document_types or [])
            return UserChoiceResult(
                primary_document_type=chosen_primary, pending_document_types=pending, notes=f"{notes}:all"
            )

        if _contains_any(["不要", "不需要", "先不", "不用", "不生成", "不要了"]):
            return UserChoiceResult(
                primary_document_type=chosen_primary, pending_document_types=[], notes=f"{notes}:none"
            )

        type_map = [
            ("反诉答辩状", "counterclaim_defense"),
            ("反诉答辩", "counterclaim_defense"),
            ("反诉状", "counterclaim"),
            ("答辩状", "defense"),
            ("答辩", "defense"),
            ("起诉状", "complaint"),
            ("起诉", "complaint"),
        ]
        for key, code in type_map:
            if key in normalized:
                chosen_primary = code
                break

        if "反诉答辩" in normalized and "counterclaim_defense" in (optional_document_types or []):
            pending = ["counterclaim_defense"]

        pending = [x for x in pending if x and x != chosen_primary]
        return UserChoiceResult(
            primary_document_type=chosen_primary, pending_document_types=pending, notes=f"{notes}:heuristic"
        )
