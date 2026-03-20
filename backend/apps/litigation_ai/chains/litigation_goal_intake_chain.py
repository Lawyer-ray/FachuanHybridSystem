"""Module for litigation goal intake chain."""

from __future__ import annotations

import logging
from typing import Any

from apps.core.llm.config import LLMConfig
from apps.core.llm.structured_output import json_schema_instructions, parse_model_content

from .goal_schemas import GoalIntakeResult

logger = logging.getLogger("apps.litigation_ai")


class LitigationGoalIntakeChain:
    def __init__(self, model: str | None = None) -> None:
        self._model = model

    async def arun(self, *, case_info: dict[str, Any], document_type: str, user_input: str) -> GoalIntakeResult:
        if not (await LLMConfig.get_api_key_async() or "").strip():
            return self._fallback_intake(
                document_type=document_type, user_input=user_input, notes="llm_api_key_missing"
            )

        system_prompt = await self._get_system_prompt()
        try:
            from asgiref.sync import sync_to_async

            from apps.litigation_ai.services.wiring import get_llm_service

            llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()
            messages = [
                {
                    "role": "system",
                    "content": "\n\n".join([system_prompt, json_schema_instructions(GoalIntakeResult)]),
                },
                {
                    "role": "user",
                    "content": "\n".join(
                        [
                            "# 文书类型",
                            document_type,
                            "",
                            "# 案件信息",
                            f"案件名称:{case_info.get('case_name', '')}",
                            f"案由:{case_info.get('cause_of_action', '')}",
                            f"涉案金额(如有):{case_info.get('target_amount') or ''}",
                            "",
                            "# 用户输入(诉讼目标/诉讼请求)",
                            user_input or "",
                        ]
                    ),
                },
            ]
            llm_resp = await llm_service.achat(messages=messages, model=self._model, temperature=0.2)
            return parse_model_content(llm_resp.content, GoalIntakeResult)
        except Exception:
            logger.exception("操作失败")

            return self._fallback_intake(document_type=document_type, user_input=user_input, notes="llm_call_failed")

    async def _get_system_prompt(self) -> str:
        from asgiref.sync import sync_to_async

        from apps.litigation_ai.services.prompt_template_service import PromptTemplateService

        service = PromptTemplateService()
        template = await sync_to_async(service.get_system_template)("litigation_ai.flow.intake_goal")
        return template or self._default_prompt()

    def _default_prompt(self) -> str:
        return "\n".join(
            [
                "你是专业诉讼律师助理,负责把用户描述的“诉讼目标/诉讼请求”整理成结构化信息,并判断是否需要追问.",
                "输出必须严格符合给定结构化字段.",
                "goal_text:用一句到三句话概括用户本次诉讼目标(中文,专业).",
                "requests:诉讼请求要点列表,每条尽量包含金额/对象/期间等信息(缺失可为空).",
                "need_clarification:当关键请求要素缺失导致无法起草(如金额、对象、主张类型不清)时为 true.",
                "clarifying_question:当 need_clarification 为 true 时,提出一个最关键、最短的追问;否则留空.",
                "不要编造事实;只基于用户输入与案件信息整理.",
            ]
        )

    def _fallback_intake(self, *, document_type: str, user_input: str, notes: str) -> GoalIntakeResult:
        text = (user_input or "").strip()
        if not text:
            return GoalIntakeResult(
                goal_text="",
                requests=[],
                need_clarification=True,
                clarifying_question="请补充本次诉讼的目标/诉讼请求(如金额、对象、期间等).",
            )

        need_more = len(text) < 6
        question = ""
        if need_more:
            question = "为了准确起草,请补充金额、对象和时间范围等关键要素."

        return GoalIntakeResult(
            goal_text=text,
            requests=[],
            need_clarification=need_more,
            clarifying_question=question,
        )
