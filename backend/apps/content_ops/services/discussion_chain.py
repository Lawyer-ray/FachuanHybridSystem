"""讨论稿生成链 — 将案件事实改写为多人播客讨论脚本。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from apps.content_ops.constants import CONTENT_LLM_MODEL
from apps.core.interfaces import ServiceLocator
from apps.core.llm.structured_output import clean_text, parse_json_content

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位专业的播客脚本编剧。你的任务是把真实的法律案件改写成一期生动有趣的播客讨论节目。

输出要求：
1. 生成 15-25 轮对话，节奏紧凑，不要拖沓
2. 每个角色要有人设感，说话风格要和角色定位一致
3. 对话要自然真实，有互动感：提问、回答、追问、感叹、总结
4. 用通俗易懂的大白话，避免法律术语
5. 开头要抓人，结尾要有感悟或金句
6. 不要编造事实，所有内容必须基于提供的案件事实

请严格按照 JSON 格式输出，使用英文 key：
{
  "title": "播客标题（抓人眼球）",
  "topic": "讨论主题概述（一句话）",
  "turns": [
    {"speaker": "角色名", "text": "对话内容"},
    ...
  ]
}
"""

class DiscussionTurnResult(BaseModel):
    speaker: str = Field(description="说话人名称，必须与输入的角色名完全一致")
    text: str = Field(description="该轮对话内容，50-200字")

class DiscussionResult(BaseModel):
    title: str = Field(description="播客标题，吸引眼球")
    topic: str = Field(description="讨论主题概述，50字以内")
    turns: list[DiscussionTurnResult] = Field(description="对话轮次列表，15-25轮")

@dataclass
class DiscussionOutput:
    title: str
    topic: str
    turns: list[dict[str, str]]
    model: str
    token_usage: dict[str, int]

class DiscussionGenerationChain:
    """将案件事实改写为多人播客讨论脚本。"""

    def __init__(self, model: str | None = None) -> None:
        self._model = model or CONTENT_LLM_MODEL

    def run(
        self,
        *,
        facts: str,
        speakers: list[dict[str, str]],
        case_summary: str = "",
    ) -> DiscussionOutput:
        """生成多人讨论脚本。

        Args:
            facts: 案件事实文本
            speakers: 角色列表，每个 dict 包含 name, role, style_prompt
            case_summary: 案情简述（可选）

        Returns:
            DiscussionOutput 包含标题、主题和对话轮次
        """
        llm_service = ServiceLocator.get_llm_service()

        speakers_text = "\n".join(
            f"- {s['name']}：{s.get('role', '')}（音色：{s.get('style_prompt', '默认')}）" for s in speakers
        )

        user_msg = f"## 参与角色\n\n{speakers_text}\n\n## 案件事实\n\n{facts}"
        if case_summary:
            user_msg = f"## 案情简述\n\n{case_summary}\n\n{user_msg}"

        from apps.core.llm.config import LLMConfig

        backend = LLMConfig.resolve_backend_for_model(self._model)

        response = llm_service.chat(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            model=self._model,
            backend=backend,
            temperature=0.8,
        )

        content = clean_text(response.content)
        parsed = parse_json_content(content)

        # 兼容中文 key
        _key_map = {
            "标题": "title",
            "title": "title",
            "主题": "topic",
            "讨论主题": "topic",
            "topic": "topic",
            "对话": "turns",
            "轮次": "turns",
            "turns": "turns",
        }
        mapped: dict[str, Any] = {}
        for k, v in parsed.items():
            mapped[_key_map.get(k, k)] = v
        parsed = mapped

        # 兼容 turns 内的中文 key
        if "turns" in parsed and isinstance(parsed["turns"], list):
            _turn_key_map = {"说话人": "speaker", "speaker": "speaker", "内容": "text", "文本": "text", "text": "text"}
            fixed_turns = []
            for turn in parsed["turns"]:
                if isinstance(turn, dict):
                    fixed_turns.append({_turn_key_map.get(k, k): v for k, v in turn.items()})
            parsed["turns"] = fixed_turns

        result = DiscussionResult.model_validate(parsed)

        # 确保 speaker 名称与输入一致
        speaker_names = {s["name"] for s in speakers}
        turns: list[dict[str, str]] = []
        for turn in result.turns:
            # 尝试匹配最相似的角色名
            matched_name = turn.speaker
            for name in speaker_names:
                if name in turn.speaker or turn.speaker in name:
                    matched_name = name
                    break
            turns.append({"speaker": matched_name, "text": turn.text})

        token_usage = {}
        if hasattr(response, "usage") and response.usage:
            token_usage = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                "total_tokens": getattr(response.usage, "total_tokens", 0),
            }

        return DiscussionOutput(
            title=result.title,
            topic=result.topic,
            turns=turns,
            model=self._model,
            token_usage=token_usage,
        )
