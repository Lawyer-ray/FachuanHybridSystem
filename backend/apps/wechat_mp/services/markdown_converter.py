"""Markdown → 公众号 HTML 转换服务"""

from __future__ import annotations

import logging

import markdown  # type: ignore[import-untyped]
from django.utils.html import escape

logger = logging.getLogger(__name__)

# 公众号编辑器支持的 CSS 样式（内联样式）
_WECHAT_CSS = """
<style>
    section { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.8; color: #333; }
    h2 { font-size: 20px; font-weight: bold; color: #1a1a1a; margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 2px solid #07c160; }
    h3 { font-size: 17px; font-weight: bold; color: #333; margin: 20px 0 10px; }
    p { font-size: 15px; margin: 10px 0; text-align: justify; }
    strong { color: #07c160; }
    blockquote { border-left: 4px solid #07c160; padding: 10px 15px; margin: 15px 0; background: #f8f8f8; color: #666; font-size: 14px; }
    ul, ol { padding-left: 20px; margin: 10px 0; }
    li { font-size: 15px; margin: 5px 0; }
    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 14px; color: #c7254e; }
    pre { background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; margin: 15px 0; }
    pre code { background: none; padding: 0; color: #333; }
    hr { border: none; border-top: 1px solid #eee; margin: 20px 0; }
    img { max-width: 100%; height: auto; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; }
    th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; font-size: 14px; }
    th { background: #f4f4f4; font-weight: bold; }
</style>
"""


def convert_markdown_to_wechat_html(md_content: str) -> str:
    """将 Markdown 转换为公众号支持的 HTML。

    Args:
        md_content: Markdown 格式的文本

    Returns:
        带样式的 HTML 字符串，可直接粘贴到公众号编辑器
    """
    # 移除第一行标题（公众号标题单独设置）
    lines = md_content.strip().split("\n")
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    md_content = "\n".join(lines).strip()

    # 转换 Markdown → HTML
    html = markdown.markdown(
        md_content,
        extensions=[
            "markdown.extensions.tables",
            "markdown.extensions.fenced_code",
            "markdown.extensions.codehilite",
            "markdown.extensions.nl2br",
        ],
        extension_configs={
            "markdown.extensions.codehilite": {
                "css_class": "highlight",
                "noclasses": True,
            },
        },
    )

    # 包裹在 section 标签中，添加内联样式
    return f"{_WECHAT_CSS}\n<section>{html}</section>"


def extract_summary(md_content: str, max_length: int = 120) -> str:
    """从 Markdown 内容中提取摘要（用于公众号文章摘要）。

    Args:
        md_content: Markdown 格式的文本
        max_length: 摘要最大长度

    Returns:
        纯文本摘要
    """
    import re

    # 移除标题行
    lines = md_content.strip().split("\n")
    text_lines = [line for line in lines if not line.startswith("#")]

    # 移除 Markdown 标记
    text = " ".join(text_lines)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # 粗体
    text = re.sub(r"\*(.*?)\*", r"\1", text)  # 斜体
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)  # 链接
    text = re.sub(r"#{1,6}\s+", "", text)  # 标题
    text = re.sub(r"\s+", " ", text).strip()  # 多余空白

    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text
