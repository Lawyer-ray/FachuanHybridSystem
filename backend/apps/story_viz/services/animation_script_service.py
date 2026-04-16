from __future__ import annotations

import logging
from typing import Any

from apps.core.llm.structured_output import json_schema_instructions, parse_model_content
from apps.story_viz.schemas import AnimationScript, ExtractedFacts

logger = logging.getLogger("apps.story_viz")


class AnimationScriptService:
    def __init__(self, *, llm_service: Any, model: str | None = None) -> None:
        self._llm_service = llm_service
        self._model = model

    def generate_script(self, *, facts: ExtractedFacts, viz_type: str) -> AnimationScript:
        system_prompt = (
            "你是故事可视化导演助手。请将输入事实编排为可视化脚本。"
            "脚本需与 viz_type 对应并保持结构化。"
        )
        messages = [
            {
                "role": "system",
                "content": "\n\n".join([system_prompt, json_schema_instructions(AnimationScript)]),
            },
            {
                "role": "user",
                "content": (
                    f"viz_type={viz_type}\n"
                    f"facts_json={facts.model_dump_json(ensure_ascii=False)}"
                ),
            },
        ]

        try:
            llm_resp = self._llm_service.chat(messages=messages, model=self._model, temperature=0.0)
            parsed = parse_model_content(llm_resp.content, AnimationScript)
            parsed.viz_type = viz_type
            return parsed
        except Exception:
            logger.exception("story_viz_animation_script_failed")
            return AnimationScript(
                title=facts.case_title,
                viz_type=viz_type,
                annotations=[x.summary for x in facts.events[:5]],
                timeline_nodes=[
                    {
                        "time": x.time_label,
                        "label": x.summary,
                    }
                    for x in facts.events[:8]
                ],
                relationship_nodes=[
                    {
                        "id": p.name,
                        "label": p.name,
                        "category": p.role or "party",
                    }
                    for p in facts.parties[:12]
                    if p.name
                ],
                edges=[
                    {
                        "source": r.source,
                        "target": r.target,
                        "relation": r.relation_type,
                    }
                    for r in facts.relationships[:20]
                ],
            )
