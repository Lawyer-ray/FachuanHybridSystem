from __future__ import annotations

import logging
from typing import Any

import bleach
from pydantic import BaseModel, Field

from apps.core.llm.structured_output import json_schema_instructions, parse_model_content
from apps.story_viz.schemas import AnimationScript

logger = logging.getLogger("apps.story_viz")

# SVG 片段白名单（安全审计：LLM 输出最终经 D3 .html() 注入页面，黑名单可被
# data: URI / use href / SMIL animate / style 注入等绕过，改为 bleach 白名单消毒）
_SVG_ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "g",
        "path",
        "circle",
        "rect",
        "line",
        "text",
        "polyline",
        "polygon",
        "ellipse",
        "title",
    }
)
# 仅放行几何/样式属性；不含 href/src/xlink:href/style 等可承载 data: URI 或 CSS 注入的属性
_SVG_ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "*": [
        "class",
        "transform",
        "opacity",
        "fill",
        "fill-opacity",
        "fill-rule",
        "stroke",
        "stroke-width",
        "stroke-opacity",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-dasharray",
        "stroke-miterlimit",
    ],
    "circle": ["cx", "cy", "r"],
    "ellipse": ["cx", "cy", "rx", "ry"],
    "rect": ["x", "y", "width", "height", "rx", "ry"],
    "line": ["x1", "y1", "x2", "y2"],
    "polyline": ["points"],
    "polygon": ["points"],
    "path": ["d"],
    "text": [
        "x",
        "y",
        "dx",
        "dy",
        "text-anchor",
        "font-size",
        "font-family",
        "font-weight",
        "dominant-baseline",
    ],
}


def sanitize_svg_fragment(fragment: str) -> str:
    """bleach 白名单消毒 SVG 片段：仅保留白名单标签与几何/样式属性（安全审计 XSS）。

    非白名单标签（script/iframe/foreignObject/animate/use/a 等）连同事件属性、
    URL 型属性（href/src/xlink:href，可携带 data:/javascript: 协议）、style 属性一并剥除。
    """
    return str(
        bleach.clean(
            fragment,
            tags=_SVG_ALLOWED_TAGS,
            attributes=_SVG_ALLOWED_ATTRIBUTES,
            strip=True,
            strip_comments=True,
        )
    )


def _has_allowed_tag(cleaned: str) -> bool:
    return any(f"<{tag}" in cleaned for tag in _SVG_ALLOWED_TAGS)


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
                svg = sanitize_svg_fragment(item.svg).strip()
                if not _has_allowed_tag(svg):
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
                svg = sanitize_svg_fragment(item.svg).strip()
                if not _has_allowed_tag(svg):
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
