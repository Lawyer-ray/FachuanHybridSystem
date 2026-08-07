"""文档解析后端共享：页眉页码清理工具

TextinBackend 和 MineruBackend 都需要从解析结果中清理页眉、页码等非正文痕迹。
本模块统一这些逻辑，避免两个后端字节级复制相同代码。

公共能力：
- clean_page_artifacts: 清理 markdown 中的 HTML 注释、独立数字行、已知页眉文本行
- collect_header_texts: 从 block 列表收集 Header 类型的文本（核心循环，后端各自适配数据来源后调用）
- normalize_text: 归一化文本（去标点），用于页眉模糊匹配
- strip_markdown_emphasis: 去除 markdown 强调标记（**bold** 等），保留内部文字
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# HTML 注释正则：TextinParse 在 <!-- --> 中存放页码等元信息，MinerU 偶尔也用
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# 独立成行的纯数字（页码）：仅匹配行首到行尾只有数字的行
_STANDALONE_PAGE_NUMBER_RE = re.compile(r"(?m)^\s*\d+\s*$")
# 归一化正则：去除标点和空白，只保留字母数字汉字（用于页眉模糊匹配）
_NORMALIZE_RE = re.compile(r"[^\w\u4e00-\u9fff]")
# markdown 强调标记：**bold** / *italic* / __bold__ / _italic_
# 注意：要先匹配双符号再匹配单符号，避免误吃
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
_MD_ITALIC_RE = re.compile(r"\*(.+?)\*|_(.+?)_", re.DOTALL)


def clean_page_artifacts(markdown: str, exclude_lines: list[str] | None = None) -> str:
    """清理 markdown 中的页眉页码痕迹

    1. 删除 HTML 注释块（可能存放页码等元信息）
    2. 删除独立成行的纯数字行（页码）
    3. 删除已知页眉文本（从 block 列表 Header 类型收集，解决 markdown 残留）
    4. 压缩因删除行产生的多余空行

    Args:
        markdown: 原始 markdown 文本
        exclude_lines: 已知页眉文本列表，从 markdown 中删除匹配的行

    Returns:
        清理后的 markdown
    """
    if not markdown:
        return markdown
    cleaned = _HTML_COMMENT_RE.sub("", markdown)
    cleaned = _STANDALONE_PAGE_NUMBER_RE.sub("", cleaned)
    if exclude_lines:
        for line in exclude_lines:
            escaped = re.escape(line)
            cleaned = re.sub(rf"(?m)^\s*{escaped}\s*$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def collect_header_texts(blocks: Iterable[dict[str, Any]], header_type: str = "header") -> list[str]:
    """从 block 列表收集页眉类型的文本（去重）

    两个后端的 block 数据来源不同：
    - TextinParse: ParseResponse.elements（内存列表，type="Header"）
    - MinerU: content_list.json（type="header"）

    本函数只负责核心循环，调用方负责取 blocks 和传入正确的 header_type。

    Args:
        blocks: block 字典的可迭代对象
        header_type: 页眉类型的字符串标识（TextinParse 为 "Header"，MinerU 为 "header"）

    Returns:
        页眉文本列表（去重，保留首次出现顺序）
    """
    header_texts: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != header_type:
            continue
        text = (block.get("text") or "").strip()
        if text and text not in seen:
            seen.add(text)
            header_texts.append(text)
    return header_texts


def normalize_text(text: str) -> str:
    """归一化文本：去除标点和空白，只保留字母数字汉字

    用于页眉模糊匹配（如"大笨蛋，蠢猪" vs "大笨蛋、蠢猪"归一化后相同）。
    """
    return _NORMALIZE_RE.sub("", text)


def strip_markdown_emphasis(text: str) -> str:
    """去除 markdown 强调标记，保留内部文本

    TextinParse 的 element.text 有时会带 **bold** / *italic* 标记，
    纯文本用途时应去除这些符号（保留文字内容）。

    Args:
        text: 可能含 markdown 强调标记的文本

    Returns:
        去除强调标记后的纯文本
    """
    if not text:
        return text
    text = _MD_BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    text = _MD_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    return text
