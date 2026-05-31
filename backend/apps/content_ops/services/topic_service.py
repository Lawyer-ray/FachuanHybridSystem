"""选题建议服务 — 使用 LLM 搜索热点法律事件，给出选题建议。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from apps.core.interfaces import ServiceLocator
from apps.core.llm.config import LLMConfig
from apps.core.llm.service import LLMService
from apps.core.llm.structured_output import clean_text, parse_json_content

if TYPE_CHECKING:
    from apps.content_ops.services.hot_topic_service import HotTopicItem

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

_TRENDS_SYSTEM_PROMPT = """\
你是一位资深的法律内容编辑，专门为普通读者寻找有故事性的法律选题。

以下是中国各大平台的今日热搜/热榜话题：

{topics_text}

请从中筛选出与法律相关的话题，并为每个话题生成选题建议。
对于每个选题：
1. 从热搜话题中选取，标题要吸引人
2. 描述为什么这个话题适合写成法律故事（法律角度切入）
3. 给出建议的检索关键词（用于在裁判文书库中搜索）

如果没有直接与法律相关的话题，请尝试找到可以从法律角度切入的话题（如消费维权、劳动纠纷、合同争议、交通事故等）。
推荐 5 个选题，请严格按照 JSON 格式输出。
"""

@dataclass
class TopicResult:
    topics: list[dict[str, str]]
    model: str
    token_usage: dict[str, int]

class TopicService:
    """使用 LLM 生成选题建议。"""

    def suggest(self, model: str | None = None) -> TopicResult:
        llm_service = ServiceLocator.get_llm_service()

        from apps.content_ops.constants import CONTENT_LLM_MODEL

        model_name = model or CONTENT_LLM_MODEL
        backend = LLMConfig.resolve_backend_for_model(model_name)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "请推荐 5 个适合写成法律故事的选题。"},
        ]

        response = llm_service.chat(
            messages=messages,
            model=model_name,
            backend=backend,
            temperature=0.8,
        )

        content = clean_text(response.content)
        parsed = parse_json_content(content)

        # Normalize: LLM may return a list directly or {"topics": [...]}
        raw_topics: list[dict[str, Any]]
        if isinstance(parsed, list):
            raw_topics = parsed
        elif isinstance(parsed, dict):
            raw_topics = parsed.get("topics", parsed.get("选题", [])) or []
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
            title = next(
                (v for k, v in t.items() if any(p in k.lower() for p in _title_patterns) and isinstance(v, str) and v),
                "",
            )
            description = next(
                (v for k, v in t.items() if any(p in k.lower() for p in _desc_patterns) and isinstance(v, str) and v),
                "",
            )
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
            topics.append(
                {
                    "title": title,
                    "description": description,
                    "suggested_keyword": kw,
                }
            )

        return TopicResult(
            topics=topics,
            model=response.model,
            token_usage={
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
            },
        )

    def suggest_from_trends(
        self,
        hot_topics: list[HotTopicItem],
        model: str | None = None,
    ) -> TopicResult:
        """基于热点话题数据，用 LLM 筛选法律相关选题。"""
        from apps.content_ops.constants import CONTENT_LLM_MODEL

        # 构造热点话题文本
        topics_text = "\n".join(
            f"{i + 1}. [{t.source}] {t.title}" + (f" (热度:{t.heat})" if t.heat else "")
            for i, t in enumerate(hot_topics[:50])  # 限制最多 50 条
        )

        llm_service = ServiceLocator.get_llm_service()
        model_name = model or CONTENT_LLM_MODEL
        backend = LLMConfig.resolve_backend_for_model(model_name)

        messages = [
            {"role": "system", "content": _TRENDS_SYSTEM_PROMPT.format(topics_text=topics_text)},
            {"role": "user", "content": "请从以上热搜话题中筛选法律相关选题，推荐 5 个。"},
        ]

        response = llm_service.chat(
            messages=messages,
            model=model_name,
            backend=backend,
            temperature=0.7,
        )

        content = clean_text(response.content)
        parsed = parse_json_content(content)

        # 复用 suggest() 中的标准化逻辑
        raw_topics: list[dict[str, Any]]
        if isinstance(parsed, list):
            raw_topics = parsed
        elif isinstance(parsed, dict):
            raw_topics = parsed.get("topics", parsed.get("选题", [])) or []
        else:
            raw_topics = []

        _title_patterns = ("title", "topic", "选题", "主题")
        _desc_patterns = ("description", "描述", "简介", "summary")
        _kw_patterns = ("keyword", "关键词")

        topics = []
        for t in raw_topics:
            values = list(t.values())
            title = next(
                (v for k, v in t.items() if any(p in k.lower() for p in _title_patterns) and isinstance(v, str) and v),
                "",
            )
            description = next(
                (v for k, v in t.items() if any(p in k.lower() for p in _desc_patterns) and isinstance(v, str) and v),
                "",
            )
            kw = next((v for k, v in t.items() if any(p in k.lower() for p in _kw_patterns) and v), "")
            str_values = [v for v in values if isinstance(v, str) and v]
            if not title and len(str_values) >= 1:
                title = str_values[0]
            if not description and len(str_values) >= 2:
                description = str_values[1]
            if not kw and len(str_values) >= 3:
                kw = str_values[2]
            if not kw:
                list_values = [v for v in values if isinstance(v, list)]
                if list_values:
                    kw = list_values[0]
            if isinstance(kw, list):
                kw = "、".join(str(k) for k in kw)
            topics.append(
                {
                    "title": title,
                    "description": description,
                    "suggested_keyword": kw,
                }
            )

        return TopicResult(
            topics=topics,
            model=response.model,
            token_usage={
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
            },
        )
