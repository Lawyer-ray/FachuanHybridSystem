"""选题建议服务 — 使用 LLM 搜索热点法律事件，给出选题建议。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from apps.core.interfaces import ServiceLocator
from apps.core.llm.service import LLMService
from apps.core.llm.structured_output import clean_text, parse_json_content

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位资深的法律内容编辑，专门为普通读者寻找有故事性的法律选题。

请根据当前社会热点和近期常见纠纷类型，推荐 5 个适合写成"街坊邻居聊案件"风格故事的选题。

要求：
1. 选题应贴近普通人的日常生活（邻里纠纷、家庭矛盾、消费维权、劳动争议等）
2. 每个选题要有趣味性，能引起读者好奇心
3. 提供一个简短的描述说明为什么这个选题有意思
4. 给出建议的检索关键词（用于在裁判文书库中搜索）

请严格按照 JSON 格式输出。
"""


@dataclass
class TopicResult:
    topics: list[dict[str, str]]
    model: str
    token_usage: dict[str, int]


class TopicService:
    """使用 LLM 生成选题建议。"""

    def suggest(self) -> TopicResult:
        llm_service = ServiceLocator.get_llm_service()

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "请推荐 5 个适合写成法律故事的选题。"},
        ]

        response = llm_service.chat(
            messages=messages,
            model="mimo-v2.5-pro",
            backend=LLMService.BACKEND_OPENAI_COMPATIBLE,
            temperature=0.8,
        )

        content = clean_text(response.content)
        parsed = parse_json_content(content)

        # Normalize: LLM may return a list directly or {"topics": [...]}
        if isinstance(parsed, list):
            raw_topics = parsed
        elif isinstance(parsed, dict):
            raw_topics = parsed.get("topics", parsed.get("选题", []))
        else:
            raw_topics = []

        # LLM returns inconsistent keys across calls; use key-pattern + positional fallback
        _title_patterns = ("title", "topic", "选题", "主题")
        _desc_patterns = ("description", "描述", "简介", "summary")
        _kw_patterns = ("keyword", "关键词")

        topics = []
        for t in raw_topics:
            values = list(t.values())
            # Try key-pattern matching first
            title = next((v for k, v in t.items() if any(p in k.lower() for p in _title_patterns) and isinstance(v, str) and v), "")
            description = next((v for k, v in t.items() if any(p in k.lower() for p in _desc_patterns) and isinstance(v, str) and v), "")
            kw = next((v for k, v in t.items() if any(p in k.lower() for p in _kw_patterns) and v), "")
            # Positional fallback: first str→title, second str→description, third→keyword
            str_values = [v for v in values if isinstance(v, str) and v]
            if not title and len(str_values) >= 1:
                title = str_values[0]
            if not description and len(str_values) >= 2:
                description = str_values[1]
            if not kw and len(str_values) >= 3:
                kw = str_values[2]
            if not kw:
                # Also check list values for keyword
                list_values = [v for v in values if isinstance(v, list)]
                if list_values:
                    kw = list_values[0]
            if isinstance(kw, list):
                kw = "、".join(str(k) for k in kw)
            topics.append({
                "title": title,
                "description": description,
                "suggested_keyword": kw,
            })

        return TopicResult(
            topics=topics,
            model=response.model,
            token_usage={
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
            },
        )
