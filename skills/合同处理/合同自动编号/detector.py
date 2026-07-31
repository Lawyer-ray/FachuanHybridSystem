"""
编号检测模块

检测文档中的编号结构，识别编号层级。
"""

import logging
import re

from docx import Document

from .formats import SIGNATURE_KEYWORDS

logger = logging.getLogger(__name__)


def is_signature_section(text: str) -> bool:
    """检测是否是签字盖章部分

    Args:
        text: 待检测的文本

    Returns:
        是否是签字盖章部分
    """
    for keyword in SIGNATURE_KEYWORDS:
        if keyword in text:
            return True
    return False


def detect_chinese_level0(text: str) -> tuple[str, str] | tuple[None, None]:
    """检测中文格式的一级标题（一、二、三...）

    Args:
        text: 待检测的文本

    Returns:
        (matched_text, original_text) 或 (None, None)
    """
    m = re.match(r'^([一二三四五六七八九十]+)、\s*', text)
    if m:
        return m.group(0), text
    return None, None


def detect_decimal_level0(text: str) -> tuple[str, str] | tuple[None, None]:
    """检测纯数字格式的一级标题（1. 2. 3...）

    Args:
        text: 待检测的文本

    Returns:
        (matched_text, original_text) 或 (None, None)
    """
    m = re.match(r'^(\d+)\.\s+', text)
    if m and '.' not in text[len(m.group(0)):len(m.group(0))+5]:
        return m.group(0), text
    return None, None


def detect_chinese_sublevel(text: str, has_level1_heading: bool) -> tuple[int, str] | tuple[None, None]:
    """检测中文格式的子级编号

    Args:
        text: 待检测的文本
        has_level1_heading: 是否已经出现过 （一）子标题

    Returns:
        (level, matched_text) 或 (None, None)
    """
    # Level 1: （一）（二）... 或 （1）（2）...
    m = re.match(r'^[（(]([一二三四五六七八九十\d]+)[）)]\s*', text)
    if m:
        return 1, m.group(0)

    # 数字编号：1. 2. 3... 或 1.1 1.2...
    m = re.match(r'^(\d+\.\d+|\d+[.、])\s*', text)
    if m:
        if has_level1_heading:
            return 2, m.group(0)
        else:
            return 1, m.group(0)

    return None, None


def detect_decimal_sublevel(text: str) -> tuple[int, str] | tuple[None, None]:
    """检测纯数字格式的子级编号

    Args:
        text: 待检测的文本

    Returns:
        (level, matched_text) 或 (None, None)
    """
    # 检测数字层级：1.1.1.1.1 > 1.1.1.1 > 1.1.1 > 1.1 > 1.
    m = re.match(r'^(\d+(?:\.\d+){0,4})\.\s+', text)
    if m:
        num_str = m.group(1)
        level = num_str.count('.')  # 点号数量决定层级
        if level > 4:
            level = 4  # 最多5级
        return level, m.group(0)

    return None, None


def detect_numbering_structure(doc: Document, format_type: str) -> list[tuple[int, int, str, str]]:
    """
    分析文档结构，识别编号层级

    Args:
        doc: Word 文档
        format_type: 编号格式类型 ('chinese' 或 'decimal')

    Returns:
        list of (para_idx, level, matched_text, original_text)
    """
    # 识别 Level 0 标题
    level0_paras = []
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue

        if format_type == 'chinese':
            matched, _ = detect_chinese_level0(text)
        else:
            matched, _ = detect_decimal_level0(text)

        if matched:
            level0_paras.append((i, matched, text))

    # 识别所有编号段落
    numbered_paras = []
    paras = doc.paragraphs

    for level0_idx, (para_idx, matched, text) in enumerate(level0_paras):
        # Level 0 标题
        numbered_paras.append((para_idx, 0, matched, text))

        # 找出下一个 Level 0 的位置
        next_level0_idx = level0_paras[level0_idx + 1][0] if level0_idx + 1 < len(level0_paras) else len(paras)

        # 扫描 Level 0 下的所有段落
        has_level1_heading = False
        prev_level = 0

        for i in range(para_idx + 1, next_level0_idx):
            para = paras[i]
            text = para.text.strip()
            if not text:
                continue

            # 检测签字盖章部分，停止编号
            if is_signature_section(text):
                break

            # 检测子级编号
            if format_type == 'chinese':
                level, sub_matched = detect_chinese_sublevel(text, has_level1_heading)
                if level is not None:
                    if level == 1:
                        has_level1_heading = True
                    numbered_paras.append((i, level, sub_matched, text))
                    prev_level = level
                    continue
            else:
                level, sub_matched = detect_decimal_sublevel(text)
                if level is not None:
                    numbered_paras.append((i, level, sub_matched, text))
                    prev_level = level
                    continue

            # 其他段落：继承上一个段落的级别
            if prev_level >= 1:
                numbered_paras.append((i, prev_level, '', text))
            else:
                numbered_paras.append((i, 1, '', text))

    return numbered_paras
