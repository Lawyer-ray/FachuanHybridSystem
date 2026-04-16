from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from apps.core.llm.structured_output import json_schema_instructions, parse_model_content
from apps.story_viz.schemas import AnimationScript

logger = logging.getLogger("apps.story_viz")


class SvgFragmentItem(BaseModel):
    name: str = Field(default="")
    svg: str = Field(default="")


class SvgFragmentBundle(BaseModel):
    fragments: list[SvgFragmentItem] = Field(default_factory=list)


class SvgFragmentGeneratorService:
    def __init__(self, *, llm_service: Any, model: str | None = None) -> None:
        self._llm_service = llm_service
        self._model = model

    def generate(self, *, script: AnimationScript) -> dict[str, object]:
        prompts = script.fragment_prompts[:3]
        if not prompts:
            return self._fallback_fragments()

        system_prompt = (
            "你是 SVG 片段生成助手。仅输出可嵌入 <g> 内的安全 SVG 片段字符串，不要包含 script。"
        )
        messages = [
            {
                "role": "system",
                "content": "\n\n".join([system_prompt, json_schema_instructions(SvgFragmentBundle)]),
            },
            {
                "role": "user",
                "content": "\n".join(f"- {item}" for item in prompts),
            },
        ]

        try:
            llm_resp = self._llm_service.chat(messages=messages, model=self._model, temperature=0.0)
            parsed = parse_model_content(llm_resp.content, SvgFragmentBundle)
            clean_fragments: list[dict[str, str]] = []
            for item in parsed.fragments:
                svg = item.svg.strip()
                lowered = svg.lower()
                if "<script" in lowered or "onload=" in lowered or "onclick=" in lowered:
                    continue
                clean_fragments.append({"name": item.name, "svg": svg})
            if not clean_fragments:
                return self._fallback_fragments()
            return {"fragments": clean_fragments}
        except Exception:
            logger.exception("story_viz_svg_fragment_generation_failed")
            return self._fallback_fragments()

    def _fallback_fragments(self) -> dict[str, object]:
        return {
            "fragments": [
                {"name": "pulse", "svg": "<circle cx='0' cy='0' r='8' fill='rgba(56,189,248,0.35)' />"},
                {"name": "halo", "svg": "<circle cx='0' cy='0' r='14' fill='none' stroke='rgba(59,130,246,0.45)' />"},
            ]
        }
