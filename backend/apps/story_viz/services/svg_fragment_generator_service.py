from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from apps.core.llm.structured_output import json_schema_instructions, parse_model_content
from apps.story_viz.schemas import AnimationScript

logger = logging.getLogger("apps.story_viz")

# 危险标签/协议黑名单（小写匹配）
_UNSAFE_SVG_TOKENS: tuple[str, ...] = ("<script", "<iframe", "<foreignobject", "<embed", "<object", "javascript:")
# 任意 on* 事件属性（如 onload= / onanimationend=）
_EVENT_ATTR_RE = re.compile(r"\son[a-z]+\s*=")


def _is_unsafe_fragment(svg_lowered: str) -> bool:
    """黑名单命中即拒绝该片段（安全审计 XSS）。"""
    return any(token in svg_lowered for token in _UNSAFE_SVG_TOKENS) or bool(_EVENT_ATTR_RE.search(svg_lowered))


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

        system_prompt = "你是 SVG 片段生成助手。仅输出可嵌入 <g> 内的安全 SVG 片段字符串，不要包含 script。"
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
                if _is_unsafe_fragment(svg.lower()):
                    continue
                clean_fragments.append({"name": item.name, "svg": svg})
            if not clean_fragments:
                return self._fallback_fragments()
            return {"fragments": clean_fragments}
        except Exception:
            logger.exception("story_viz_svg_fragment_generation_failed")
            return self._fallback_fragments()

    async def agenerate(self, *, script: AnimationScript) -> dict[str, object]:
        """异步版本，使用 achat 替代 chat。"""
        prompts = script.fragment_prompts[:3]
        if not prompts:
            return self._fallback_fragments()

        system_prompt = "你是 SVG 片段生成助手。仅输出可嵌入 <g> 内的安全 SVG 片段字符串，不要包含 script。"
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
            llm_resp = await self._llm_service.achat(messages=messages, model=self._model, temperature=0.0)
            parsed = parse_model_content(llm_resp.content, SvgFragmentBundle)
            clean_fragments: list[dict[str, str]] = []
            for item in parsed.fragments:
                svg = item.svg.strip()
                if _is_unsafe_fragment(svg.lower()):
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
