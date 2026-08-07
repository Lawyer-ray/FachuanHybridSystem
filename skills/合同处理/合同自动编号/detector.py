"""
编号检测模块

检测文档中的编号结构，识别编号层级。
"""

import logging
import re

from docx import Document

from .formats import SIGNATURE_KEYWORDS, SIGNATURE_PATTERNS

logger = logging.getLogger(__name__)


def is_signature_section(text: str) -> bool:
    """检测是否是签字盖章部分

    Args:
        text: 待检测的文本

    Returns:
        是否是签字盖章部分
    """
    # 检查关键词
    for keyword in SIGNATURE_KEYWORDS:
        if keyword in text:
            return True

    # 检查模式
    for pattern in SIGNATURE_PATTERNS:
        if re.match(pattern, text.strip()):
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

    层级映射（中文格式 一、1.（1）①）：
      Level 1 → 1.    （来源：（一）（二）... 中文数字带括号）
      Level 2 → （1）  （来源：（1）（2）... 阿拉伯数字带括号，或 1. 2. 当存在（一）子标题时）
      Level 3 → ①     （来源：1）2）... 无左括号）

    Args:
        text: 待检测的文本
        has_level1_heading: 是否已经出现过 （一）子标题

    Returns:
        (level, matched_text) 或 (None, None)
    """
    # Level 1: （一）（二）... （中文数字带括号 → 映射为 "1."）
    m = re.match(r'^[（(]([一二三四五六七八九十]+)[）)]\s*', text)
    if m:
        return 1, m.group(0)

    # Level 2: （1）（2）... （阿拉伯数字带括号 → 映射为 "（1）"）
    m = re.match(r'^[（(](\d+)[）)]\s*', text)
    if m:
        return 2, m.group(0)

    # Level 3: 1）2）... （无左括号）
    m = re.match(r'^(\d+)[）)]\s*', text)
    if m:
        return 3, m.group(0)

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

            # 先检测子级编号 — 必须优先于签名检测！
            # 有编号前缀的段落绝不可能是签名页（即使文本包含"签字"等词）
            if format_type == 'chinese':
                level, sub_matched = detect_chinese_sublevel(text, has_level1_heading)
                if level is not None:
                    # 只有（一）型子标题才设置 has_level1_heading
                    is_subheading = level == 1 and sub_matched and sub_matched[0] in '（('
                    if is_subheading:
                        has_level1_heading = True
                    numbered_paras.append((i, level, sub_matched, text))
                    # （一）型子标题后的无编号段落应为下一级（level + 1）
                    if is_subheading:
                        prev_level = level + 1
                    else:
                        prev_level = level
                    continue  # ← 成功匹配编号，跳过后续所有检查
            else:
                level, sub_matched = detect_decimal_sublevel(text)
                if level is not None:
                    numbered_paras.append((i, level, sub_matched, text))
                    prev_level = level
                    continue  # ← 成功匹配编号，跳过后续所有检查

            # 启发式：检测是否是以特殊关键词开头的新段落
            # 如果段落以"甲方/乙方有以下/下列行为"开头，应该是新的 Level 1
            # 空matched表示继承上一级别
            if re.match(r'^[甲乙丙丁]方有[以下下列]', text):
                numbered_paras.append((i, 1, '', text))
                prev_level = 1
                continue

            # 签名盖章检测放在最后 — 只有前面都匹配不上的才是签名区
            if is_signature_section(text):
                break

            # 其他段落：继承上一个段落的级别
            if prev_level >= 1:
                numbered_paras.append((i, prev_level, '', text))
            else:
                numbered_paras.append((i, 1, '', text))

    return numbered_paras
