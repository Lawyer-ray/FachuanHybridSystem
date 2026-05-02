from __future__ import annotations

import logging
from typing import Any

from apps.core.llm.structured_output import json_schema_instructions, parse_model_content
from apps.story_viz.schemas import AnimationScript, ComparisonItem, ExtractedFacts, GraphEdge, GraphNode, MotionPlan

logger = logging.getLogger("apps.story_viz")


class AnimationScriptService:
    def __init__(self, *, llm_service: Any, model: str | None = None) -> None:
        self._llm_service = llm_service
        self._model = model

    def generate_script(self, *, facts: ExtractedFacts, viz_type: str) -> AnimationScript:
        system_prompt = "你是故事可视化导演助手。请将输入事实编排为可视化脚本。脚本需与 viz_type 对应并保持结构化。"
        messages = [
            {
                "role": "system",
                "content": "\n\n".join([system_prompt, json_schema_instructions(AnimationScript)]),
            },
            {
                "role": "user",
                "content": (f"viz_type={viz_type}\nfacts_json={facts.model_dump_json(ensure_ascii=False)}"),
            },
        ]

        try:
            llm_resp = self._llm_service.chat(messages=messages, model=self._model, temperature=0.0)
            parsed = parse_model_content(llm_resp.content, AnimationScript)
            parsed.viz_type = viz_type
            return parsed
        except Exception:
            logger.warning("story_viz_script_first_attempt_failed, retrying")
            try:
                llm_resp = self._llm_service.chat(messages=messages, model=self._model, temperature=0.3)
                parsed = parse_model_content(llm_resp.content, AnimationScript)
                parsed.viz_type = viz_type
                return parsed
            except Exception:
                logger.exception("story_viz_animation_script_failed")
                return self._build_fallback_script(facts=facts, viz_type=viz_type)

    @staticmethod
    def _build_fallback_script(*, facts: ExtractedFacts, viz_type: str) -> AnimationScript:
        if viz_type == "claim_judgment":
            comparison = [
                ComparisonItem(
                    claim=e.summary,
                    judgment="",
                    amount_claim=e.amounts[0] if e.amounts else "",
                    amount_judgment="",
                    supported=False,
                )
                for e in facts.events[:12]
                if e.summary
            ]
            if not comparison and facts.judgment_result:
                comparison = [ComparisonItem(claim="诉讼请求", judgment=facts.judgment_result)]
            return AnimationScript(
                title=facts.case_title,
                viz_type=viz_type,
                annotations=[facts.judgment_result] if facts.judgment_result else [],
                comparison_nodes=comparison,
                motion_plan=MotionPlan(duration_ms=1000, easing="ease-in-out"),
            )

        nodes = [{"id": p.name, "label": p.name, "category": p.role or "party"} for p in facts.parties[:16] if p.name]
        edges = [
            {"source": r.source, "target": r.target, "relation": r.relation_type}
            for r in facts.relationships[:24]
            if r.source and r.target
        ]
        return AnimationScript(
            title=facts.case_title,
            viz_type=viz_type,
            annotations=[x.summary for x in facts.events[:5] if x.summary],
            timeline_nodes=[{"time": x.time_label, "label": x.summary} for x in facts.events[:12] if x.summary],
            relationship_nodes=[GraphNode(id=n["id"], label=n["label"], category=n["category"]) for n in nodes],
            edges=[GraphEdge(source=e["source"], target=e["target"], relation=e["relation"]) for e in edges],
            scene_order=[f"scene_{i}" for i in range(min(5, len(facts.events)))],
            motion_plan=MotionPlan(duration_ms=1000, easing="ease-in-out"),
            fragment_prompts=["indicator pulse", "connection halo"],
        )
