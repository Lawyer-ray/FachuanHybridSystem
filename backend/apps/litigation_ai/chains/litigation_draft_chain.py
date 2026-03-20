"""Module for litigation draft chain."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apps.core.llm.structured_output import clean_text, parse_json_content

logger = logging.getLogger("apps.litigation_ai")


@dataclass
class DraftResult:
    display_text: str
    draft: dict[str, str]
    model: str
    token_usage: dict[str, int]


class LitigationDraftChain:
    def __init__(self, model: str | None = None) -> None:
        self._model = model

    async def _build_messages(
        self, document_type: str, case_info: dict[str, Any], litigation_goal: str, evidence_text: str
    ) -> list[dict[str, str]]:
        from apps.litigation_ai.services.prompt_template_service import PromptTemplateService

        template_service = PromptTemplateService()
        from asgiref.sync import sync_to_async

        system_template = await sync_to_async(template_service.get_system_template)(document_type) or (
            "你是一位专业的诉讼律师,擅长撰写诉讼文书.\n"
            "你只能生成文书的可变内容,不要编造或改写当事人身份信息、审理机构、签名盖章等.\n"
            "输出必须是中文、专业、逻辑清晰.\n"
        )
        system = template_service.replace_variables(system_template, case_info)
        import json

        from .schemas import ComplaintDraft, DefenseDraft

        schema = (
            ComplaintDraft.model_json_schema()
            if document_type in ["complaint", "counterclaim"]
            else DefenseDraft.model_json_schema()
        )
        schema_text = json.dumps(schema, ensure_ascii=False)

        output_contract = (
            "你必须只输出一个 JSON 对象,不要输出 Markdown,不要输出多余文字.\n"
            f"该 JSON 必须严格符合以下 JSON Schema:{schema_text}\n"
            "注意:不要输出任何当事人信息、审理机构、签名盖章等固定块内容.\n"
            "如果给出了证据摘要,请在 evidence_citations 中列出你实际引用到的证据,\n"
            "并尽量填写 evidence_item_id(来自 [证据#ID])、pages(来自页码)、used_in(用于说明引用位置).\n"
        )

        user = "\n".join(
            [
                "# 案件信息",
                f"案件名称:{case_info.get('case_name', '')}",
                f"案由:{case_info.get('cause_of_action', '')}",
                "",
                "# 系统生成的基础信息(以此为准,不要改写)",
                str(case_info.get("system_generated_court_block", "")),
                str(case_info.get("system_generated_party_block", "")),
                str(case_info.get("system_generated_signature_block", "")),
                "",
                "# 诉讼目标",
                litigation_goal,
                "",
                "# 证据摘要",
                evidence_text or "无",
            ]
        )

        return [
            {"role": "system", "content": f"{system}\n{output_contract}"},
            {"role": "user", "content": user},
        ]

    def _clean_llm_output(self, text: str) -> str:
        return clean_text(text)

    def _format_display_text(self, document_type: str, draft: dict[str, Any]) -> str:
        if document_type in ["complaint", "counterclaim"]:
            return "\n\n".join(
                [
                    "诉讼请求:",
                    (draft.get("litigation_request") or "").strip(),
                    "",
                    "事实与理由:",
                    (draft.get("facts_and_reasons") or "").strip(),
                ]
            ).strip()

        parts = []
        if (draft.get("defense_opinion") or "").strip():
            parts.extend(["答辩意见:", (draft.get("defense_opinion") or "").strip(), ""])
        parts.extend(["答辩理由:", (draft.get("defense_reason") or "").strip()])

        rebuttal = draft.get("rebuttal_to_opponent_evidence") or []
        if rebuttal:
            parts.extend(["", "质证/反驳要点:", "\n".join([f"- {x}" for x in rebuttal if str(x).strip()]).strip()])

        return "\n\n".join([p for p in parts if p is not None]).strip()

    async def arun(
        self,
        *,
        case_info: dict[str, Any],
        document_type: str,
        litigation_goal: str,
        evidence_text: str,
        stream_callback: Callable[[str], Any] | None = None,
    ) -> DraftResult:
        from asgiref.sync import sync_to_async

        from apps.litigation_ai.services.wiring import get_llm_service

        llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()

        messages = await self._build_messages(document_type, case_info, litigation_goal, evidence_text)

        response = await llm_service.achat(messages=messages, model=self._model, temperature=0.2)
        model_name = response.model or self._model or ""
        content = self._clean_llm_output(response.content or "")
        token_usage = {
            "prompt_tokens": int(getattr(response, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(response, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(response, "total_tokens", 0) or 0),
        }

        from .schemas import ComplaintDraft, DefenseDraft

        parsed = parse_json_content(content) if content else {}
        if document_type in ["complaint", "counterclaim"]:
            draft_obj: ComplaintDraft | DefenseDraft = ComplaintDraft.model_validate(parsed)
        else:
            draft_obj = DefenseDraft.model_validate(parsed)

        draft = draft_obj.model_dump()
        display_text = self._format_display_text(document_type, draft)
        if stream_callback and display_text:
            await stream_callback(display_text)

        return DraftResult(
            display_text=display_text,
            draft=draft,
            model=model_name,
            token_usage=token_usage,
        )
