"""内容生成链 — 将裁判文书事实改写为街坊邻居风格的叙事文章。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from apps.core.interfaces import ServiceLocator
from apps.core.llm.service import LLMService
from apps.core.llm.structured_output import clean_text, parse_model_content

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位擅长讲故事的法律故事写手。你的读者是街坊邻居、普通老百姓，他们不懂法律术语，但爱听故事。

你的任务是把裁判文书中的案件事实改写成一篇引人入胜的叙事文章。

写作要求：
1. 用街坊邻居聊天的口吻，通俗易懂，生动有趣
2. 避免法律术语，用大白话解释（比如"原告"说"告状的那个人"，"被告"说"被告的那个人"）
3. 有清晰的叙事线：谁？怎么了？为什么闹上法庭？法院怎么判的？
4. 标题要抓人眼球，像故事会的标题
5. 正文 800-1500 字，节奏紧凑，不要废话
6. 结尾可以加一句点评或感悟，引起共鸣
7. 不要编造事实，所有内容必须基于提供的案件事实

请严格按照 JSON 格式输出。
"""


class NarrativeResult(BaseModel):
    title: str = Field(description="文章标题，吸引眼球，适合街坊邻居阅读")
    content: str = Field(description="叙事风格的案件故事正文，800-1500字")
    summary: str = Field(description="一句话摘要，50字以内")


@dataclass
class ContentResult:
    title: str
    content: str
    summary: str
    model: str
    token_usage: dict[str, int]


class ContentGenerationChain:
    """将裁判文书事实改写为叙事风格的故事文章。"""

    def __init__(self, model: str | None = None) -> None:
        self._model = model or "mimo-v2.5-pro"

    def run(self, *, facts: str, case_summary: str = "") -> ContentResult:
        llm_service = ServiceLocator.get_llm_service()

        user_msg = f"## 案件事实\n\n{facts}"
        if case_summary:
            user_msg += f"\n\n## 案情简述\n\n{case_summary}"

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        response = llm_service.chat(
            messages=messages,
            model=self._model,
            backend=LLMService.BACKEND_OPENAI_COMPATIBLE,
            temperature=0.8,
        )

        content = clean_text(response.content)
        parsed = parse_model_content(content, NarrativeResult)

        return ContentResult(
            title=parsed.title,
            content=parsed.content,
            summary=parsed.summary,
            model=response.model,
            token_usage={
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
            },
        )
