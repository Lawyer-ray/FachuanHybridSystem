"""Smart fill service - natural language template filling."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

from apps.core.llm.structured_output import parse_json_content
from apps.documents.services.code_placeholders.catalog_service import CodePlaceholderCatalogService
from apps.documents.services.document_template.placeholder_extractor import extract_placeholders
from apps.documents.services.generation.pipeline.renderer import DocxRenderer
from apps.documents.services.placeholders.fallback import PLACEHOLDER_FALLBACK_VALUE

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个法律文书模板填充助手。用户会给你一份文书模板中的占位符列表，以及自然语言描述，你需要将用户描述中的信息映射到对应的占位符。

规则：
1. 仔细匹配用户描述中的信息与占位符的语义
2. 如果用户没有提到某个占位符的信息，该占位符的值设为空字符串
3. 日期类占位符请使用"YYYY年MM月DD日"格式
4. 金额类占位符请使用中文大写或阿拉伯数字，根据上下文判断
5. 只输出 JSON，不要输出其他文字"""

USER_PROMPT_TEMPLATE = """## 模板占位符列表
{catalog}

## 用户描述
{user_input}

## 今天日期
{today_date}

请根据用户描述，为每个占位符生成对应的值。返回 JSON 对象，键为占位符名，值为填充内容。"""

# 自动填充的占位符
AUTO_FILL_KEYS = {"今天日期", "当前日期", "今年年份"}


@dataclass
class PlaceholderResult:
    """单个占位符的填充结果"""

    key: str
    value: str
    source: str  # "llm", "auto", "fallback"


@dataclass
class SmartFillResult:
    """智能填充结果"""

    placeholders: list[PlaceholderResult] = field(default_factory=list)
    rendered_bytes: bytes | None = None
    error: str | None = None


class SmartFillService:
    """自然语言模板填充服务"""

    def __init__(self, llm_service: Any) -> None:
        self._llm_service = llm_service
        self._catalog_service = CodePlaceholderCatalogService()

    def preview(self, template_path: str, user_input: str, model: str | None = None) -> SmartFillResult:
        """预览：提取占位符 -> LLM 映射 -> 返回预览"""
        try:
            # Step 1: 提取占位符
            keys = extract_placeholders(template_path)
            if not keys:
                return SmartFillResult(error="模板中未发现占位符")

            # Step 2: 构建 catalog
            catalog_text = self._build_catalog(keys)

            # Step 3: 调用 LLM
            llm_values = self._call_llm(catalog_text, user_input, model=model)

            # Step 4: 后处理
            items = self._build_result_items(keys, llm_values)

            return SmartFillResult(placeholders=items)
        except Exception as e:
            logger.exception("智能填充预览失败")
            return SmartFillResult(error=f"预览失败: {e}")

    def render(self, template_path: str, placeholders: list[PlaceholderResult]) -> bytes:
        """渲染 docx（不再调用 LLM）"""
        context = {item.key: item.value for item in placeholders}
        renderer = DocxRenderer()
        return renderer.render(template_path, context)

    def fill(self, template_path: str, user_input: str) -> SmartFillResult:
        """填充：预览 + 渲染 docx"""
        result = self.preview(template_path, user_input)
        if result.error:
            return result

        # Step 5: 渲染
        try:
            result.rendered_bytes = self.render(template_path, result.placeholders)
        except Exception as e:
            logger.exception("智能填充渲染失败")
            result.error = f"渲染失败: {e}"

        return result

    def _build_catalog(self, keys: list[str]) -> str:
        """构建占位符目录，注入系统元数据"""
        definitions = {d.key: d for d in self._catalog_service.list_definitions()}
        lines = []

        for key in keys:
            if key in AUTO_FILL_KEYS:
                lines.append(f"- {{{{ {key} }}}}: [自动填充，无需生成]")
            elif key in definitions:
                d = definitions[key]
                desc = d.description or d.display_name or key
                example = f"（示例：{d.example_value}）" if d.example_value else ""
                lines.append(f"- {{{{ {key} }}}}: {desc}{example}")
            else:
                lines.append(f"- {{{{ {key} }}}}: [模板自定义占位符]")

        return "\n".join(lines)

    def _call_llm(self, catalog: str, user_input: str, model: str | None = None) -> dict[str, str]:
        """调用 LLM，返回映射结果"""
        today = timezone.localdate()
        today_str = f"{today.year}年{today.month:02d}月{today.day:02d}日"

        user_message = USER_PROMPT_TEMPLATE.format(
            catalog=catalog,
            user_input=user_input,
            today_date=today_str,
        )

        # 重试最多 3 次
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self._llm_service.complete(
                    prompt=user_message,
                    system_prompt=SYSTEM_PROMPT,
                    temperature=0.1,
                    model=model or None,
                )

                parsed = parse_json_content(response.content)
                if isinstance(parsed, dict):
                    # 确保所有值都是字符串
                    return {str(k): str(v) if v is not None else "" for k, v in parsed.items()}

                logger.warning("LLM 返回非 dict 格式: %s", type(parsed).__name__)
            except Exception as e:
                logger.warning("LLM 调用失败 (attempt %d): %s", attempt + 1, e)
                last_error = e

        if last_error:
            raise last_error
        return {}

    def _build_result_items(
        self,
        keys: list[str],
        llm_values: dict[str, str],
    ) -> list[PlaceholderResult]:
        """构建结果列表，区分来源"""
        today = timezone.localdate()
        today_str = f"{today.year}年{today.month:02d}月{today.day:02d}日"
        auto_fill = {
            "今天日期": today_str,
            "当前日期": today_str,
            "今年年份": str(today.year),
        }

        items: list[PlaceholderResult] = []
        for key in keys:
            if key in auto_fill:
                items.append(PlaceholderResult(key=key, value=auto_fill[key], source="auto"))
            elif llm_values.get(key):
                items.append(PlaceholderResult(key=key, value=llm_values[key], source="llm"))
            else:
                items.append(PlaceholderResult(key=key, value=PLACEHOLDER_FALLBACK_VALUE, source="fallback"))

        return items
