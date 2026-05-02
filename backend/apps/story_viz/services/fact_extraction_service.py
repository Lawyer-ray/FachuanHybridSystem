from __future__ import annotations

import logging
from typing import Any

from apps.core.llm.structured_output import json_schema_instructions, parse_model_content
from apps.story_viz.schemas import ExtractedFacts, FactEvent

logger = logging.getLogger("apps.story_viz")


class FactExtractionService:
    def __init__(self, *, llm_service: Any, model: str | None = None) -> None:
        self._llm_service = llm_service
        self._model = model

    def extract(self, *, source_title: str, source_text: str) -> ExtractedFacts:
        system_prompt = "你是法律事实提取助手。请根据给定判决书文本提取人物、事件、关系与裁判结果。只输出 JSON。"
        messages = [
            {
                "role": "system",
                "content": "\n\n".join([system_prompt, json_schema_instructions(ExtractedFacts)]),
            },
            {
                "role": "user",
                "content": f"标题：{source_title}\n\n正文：\n{source_text}",
            },
        ]

        try:
            llm_resp = self._llm_service.chat(messages=messages, model=self._model, temperature=0.0)
            return parse_model_content(llm_resp.content, ExtractedFacts)
        except Exception:
            logger.warning("story_viz_fact_extraction_first_attempt_failed, retrying")
            try:
                llm_resp = self._llm_service.chat(messages=messages, model=self._model, temperature=0.3)
                return parse_model_content(llm_resp.content, ExtractedFacts)
            except Exception:
                logger.exception("story_viz_fact_extraction_failed")
                fallback_summary = source_text[:120] if source_text else ""
                return ExtractedFacts(
                    case_title=source_title,
                    events=[
                        FactEvent(
                            sequence=1,
                            time_label="",
                            summary=fallback_summary,
                        )
                    ],
                    confidence_notes="fallback",
                )
