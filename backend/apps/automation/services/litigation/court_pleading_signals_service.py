"""Business logic services."""

import logging
from typing import Any

from apps.core.llm.structured_output import json_schema_instructions, parse_model_content

from .dtos import CourtPleadingSignals

logger = logging.getLogger("apps.automation")


class CourtPleadingSignalsService:
    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def get_signals(self, case_id: int) -> Any:
        doc_names = self._get_case_court_document_names(case_id)
        if not doc_names:
            return CourtPleadingSignals()

        prompt = self._get_prompt_template() or self._default_prompt()
        try:
            return self._classify_with_llm(prompt, doc_names)
        except Exception:
            logger.warning(
                "法院文书态势识别失败,回退到关键词规则",
                extra={},
                exc_info=True,
            )
            return self._fallback_by_keywords(doc_names)

    def _get_case_court_document_names(self, case_id: int) -> list[str]:
        from apps.automation.models import CourtDocument

        qs = CourtDocument.objects.filter(case_id=case_id).exclude(c_wsmc__isnull=True).exclude(c_wsmc="")
        return list(qs.values_list("c_wsmc", flat=True)[:200])

    def _get_prompt_template(self) -> Any:
        # PromptVersionService 已移除，始终使用默认 prompt
        return None

    def _classify_with_llm(self, system_prompt: str, doc_names: list[str]) -> Any:
        from apps.automation.services.wiring import get_llm_service

        llm_service = get_llm_service()
        messages = [
            {
                "role": "system",
                "content": "\n\n".join([system_prompt, json_schema_instructions(CourtPleadingSignals)]),
            },
            {
                "role": "user",
                "content": "法院文书名称列表:\n" + "\n".join([f"- {x}" for x in doc_names]),
            },
        ]
        llm_resp = llm_service.chat(messages=messages, model=self._model, temperature=0.0)
        return parse_model_content(llm_resp.content, CourtPleadingSignals)

    def _fallback_by_keywords(self, doc_names: list[str]) -> CourtPleadingSignals:
        text = "\n".join(doc_names)
        return CourtPleadingSignals(
            has_complaint=("起诉状" in text) and ("反诉" not in text or "反诉起诉状" not in text),
            has_defense=("答辩状" in text) and ("反诉答辩" not in text),
            has_counterclaim=("反诉状" in text) or ("反诉起诉状" in text),
            has_counterclaim_defense=("反诉答辩状" in text),
            notes="fallback_keywords",
        )

    def _default_prompt(self) -> str:
        return "\n".join(
            [
                "你是法律助理,负责从“法院文书名称列表”中识别案件当前是否出现以下诉讼文书:起诉状、答辩状、反诉状、反诉答辩状.",
                "你必须输出结构化结果,字段:has_complaint, has_defense, "
                "has_counterclaim, has_counterclaim_defense, notes.",
                "只根据名称判断即可;不确定时选择更保守的 false,并在 notes 中说明原因.",
            ]
        )
