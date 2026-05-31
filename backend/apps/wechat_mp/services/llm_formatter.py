"""LLM 驱动的公众号排版服务。

使用大模型将 Markdown 内容转换为花里胡哨的公众号 HTML。
支持多种排版风格：专业、创意、简约等。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 排版系统提示词
_FORMATTING_SYSTEM_PROMPT = """你是一位顶级的微信公众号排版设计师。你的任务是将用户提供的 Markdown 内容转换为精美的、带有内联样式的 HTML，可以直接粘贴到微信公众号的 ProseMirror 编辑器中。

## 重要规则

1. **只输出 HTML**，不要输出任何解释文字
2. **所有样式必须内联**（style=""），不能用 <style> 标签
3. **不要使用 <script> 标签**
4. 只使用以下 HTML 标签：section, p, span, strong, em, h1-h6, blockquote, ul, ol, li, table, thead, tbody, tr, th, td, code, pre, img, a, hr, svg, br
5. SVG 必须内联，不能用 <img src="...svg">
6. 使用 display:flex 实现多列布局
7. 确保在手机端（375px 宽度）显示效果良好

## 可用的排版元素

### 标题样式
- h1：居中 + 渐变色文字（用 SVG linearGradient）或底部彩色边框
- h2：左侧彩色边框 + 浅色背景 + 圆角
- h3：全宽彩色背景 + 白色文字 + 圆角

### 卡片布局
用 section + border-radius + box-shadow + padding 实现卡片效果

### 多列布局
用 display:flex + gap 实现两列或三列布局

### 步骤/流程
用带编号的圆形 + 连接线实现步骤展示

### 时间线
用左侧竖线 + 圆点节点实现时间线效果

### 高亮文字
用 background:linear-gradient(180deg,transparent 60%,颜色 60%) 实现荧光笔效果

### 分隔线
用 SVG path 实现波浪线、菱形、渐变等创意分隔线

### Callout 盒子
用左侧彩色边框 + 浅色背景 + emoji 图标实现提示框

### 表格
用圆角 + 阴影 + 深色表头 + 交替行背景实现精美表格

### 作者卡片
用渐变背景 + 头像 + 姓名实现作者介绍卡片

### 结尾卡片
用居中文字 + 装饰元素实现文章结尾

## 配色方案

根据内容类型选择合适的配色：
- 法律/专业：深蓝 #0F4C81 为主色
- 科技/创新：紫色 #6C5CE7 为主色
- 生活/分享：绿色 #07c160 为主色
- 教育/知识：橙色 #e17055 为主色

## 输出格式

直接输出 <section> 包裹的 HTML，不要有其他内容。"""

def _build_user_prompt(md_content: str, style: str = "auto") -> str:
    """构建用户提示词。"""
    style_desc = {
        "auto": "根据内容自动选择最合适的排版风格",
        "professional": "专业严肃风格，适合法律文书、商业报告",
        "creative": "创意活泼风格，适合科技、生活类文章",
        "minimal": "极简优雅风格，适合深度阅读",
        "colorful": "色彩丰富风格，适合教育、科普文章",
    }

    return f"""请将以下 Markdown 内容转换为精美的公众号 HTML 排版。

排版风格要求：{style_desc.get(style, style_desc["auto"])}

## Markdown 内容

{md_content}

## 要求

1. 保留原文的所有内容和结构
2. 根据内容类型选择最合适的排版元素（卡片、步骤、时间线、表格等）
3. 为标题、重点内容、引用等添加精美的视觉样式
4. 如果内容包含列表，考虑使用带编号的圆形或 emoji 作为标记
5. 如果内容包含表格，使用圆角、阴影、深色表头
6. 如果内容包含代码块，使用带语法高亮的样式
7. 在文章末尾添加一个精美的结尾卡片

请直接输出 HTML，不要有其他解释。"""

async def llm_format_article(
    md_content: str,
    style: str = "auto",
    model: str | None = None,
    max_retries: int = 2,
) -> str | None:
    """使用 LLM 将 Markdown 转换为精美公众号 HTML。

    Args:
        md_content: Markdown 格式的内容
        style: 排版风格 (auto/professional/creative/minimal/colorful)
        model: LLM 模型名称，None 使用默认模型
        max_retries: 最大重试次数

    Returns:
        精美的 HTML 字符串，失败返回 None
    """
    try:
        from apps.core.llm import get_llm_service

        service = get_llm_service()

        messages = [
            {"role": "system", "content": _FORMATTING_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(md_content, style)},
        ]

        for attempt in range(max_retries + 1):
            try:
                response = await service.achat(
                    messages=messages,
                    model=model,
                    temperature=0.7,
                    max_tokens=8000,
                )

                html = response.content.strip()

                # 清理 LLM 输出：移除 markdown 代码块包裹
                if html.startswith("```html"):
                    html = html[7:]
                elif html.startswith("```"):
                    html = html[3:]
                if html.endswith("```"):
                    html = html[:-3]
                html = html.strip()

                # 验证输出是有效 HTML
                if "<section" in html or "<p" in html:
                    logger.info(
                        "LLM formatting completed (attempt %d, model=%s)",
                        attempt + 1,
                        response.model,
                    )
                    return html

                logger.warning(
                    "LLM output is not valid HTML (attempt %d), retrying...",
                    attempt + 1,
                )

            except Exception as e:
                logger.warning(
                    "LLM formatting failed (attempt %d): %s",
                    attempt + 1,
                    e,
                )
                if attempt < max_retries:
                    continue
                raise

    except Exception as e:
        logger.error("LLM formatting service error: %s", e, exc_info=True)
        return None

    return None
