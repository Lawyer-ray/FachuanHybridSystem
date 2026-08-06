"""
格式定义模块

定义支持的编号格式和相关常量。
"""

import re
from typing import Any

# 签字盖章部分的关键词
# 必须是仅出现在正式签名区域的内容，正文条款中可能出现的不放这里
SIGNATURE_KEYWORDS: list[str] = [
    # 明确的签名/盖章标识（几乎不可能出现在正文条款中）
    '以下无正文',
    '签约页',
    '（盖章）',
    '(盖章)',
    '甲方（盖章）',
    '乙方（盖章）',
    '丙方（盖章）',
    '丁方（盖章）',
    # 签名区域常见内容（行首模式更精确，暂用关键词过滤+位置判断）
    '签约地点',
    '签订地点',
    # 日期占位符
    '年   月   日',
    '年  月  日',
    '年 月 日',
]

# 签名区域的精确模式（匹配行首的签名格式）
# 这些模式要求以签名单词开头，避免正文条款被误检
SIGNATURE_PATTERNS: list[str] = [
    r'^甲方[：:]',
    r'^乙方[：:]',
    r'^丙方[：:]',
    r'^丁方[：:]',
    r'^[一二三四五六七八九十]+方[：:]',
    r'^甲方（盖章）',
    r'^乙方（盖章）',
    r'^授权代表(签字|签署)[:：]',
    r'^签订日期[:：]',
    r'^签署日期[:：]',
]

# 空格分隔的敏感关键词（正文条款可能包含，需要额外校验上下文）
_SIGNATURE_CONTEXT_SENSITIVE: list[str] = [
    '授权代表',
    '签订日期',
]


def _has_number_prefix(text: str) -> bool:
    """检查文本是否以编号前缀开头

    用于区分"正文条款中引用签名行为"和"签名区域标题"。
    例如：
      - 有编号: （四）本协议自授权代表签字并加盖公章之日起生效 → NOT 签名页
      - 无编号: 授权代表签字：________ → IS 签名页
    """
    stripped = text.strip()
    # 行首是这些之一 → 视为有编号，不应被误判为签名页
    patterns = [
        r'^[（(][一二三四五六七八九十\d]+[）)]',  # （一）(1) 等
        r'^[\d一二三四五六七八九十]+[\.、]',  # 1. 一、
        r'^[\d一二三四五六七八九十]+[、\.][\s]*',  # 更宽松的编号前缀
    ]
    for p in patterns:
        if re.match(p, stripped):
            return True
    return False


def is_signature_section(text: str) -> bool:
    """检测是否是签字盖章部分（增强版，正文条款不会被误判）

    Args:
        text: 待检测的文本

    Returns:
        是否是签字盖章部分
    """
    stripped = text.strip()

    # 如果行首有编号前缀（如"（四）"），即使文本中有"授权代表"字样
    # 也应该被视为正文条款而非签名区域
    if _has_number_prefix(text):
        return False

    # 检查关键词（不含需上下文敏感判断的）
    for keyword in SIGNATURE_KEYWORDS:
        if keyword in text:
            return True

    # 检查精确模式
    for pattern in SIGNATURE_PATTERNS:
        if re.match(pattern, stripped):
            return True

    return False

# 编号格式定义
NUMBERING_FORMATS: dict[str, dict[str, Any]] = {
    'chinese': {
        'name': '一、1.（1）①',
        'description': '中文格式（一、二、三...）',
        'levels': [
            {'ilvl': '0', 'numFmt': 'chineseCounting', 'lvlText': '%1、', 'start': '1'},
            {'ilvl': '1', 'numFmt': 'decimal', 'lvlText': '%2.', 'start': '1'},
            {'ilvl': '2', 'numFmt': 'decimal', 'lvlText': '（%3）', 'start': '1'},
            {'ilvl': '3', 'numFmt': 'decimalEnclosedCircle', 'lvlText': '%4', 'start': '1'},
        ]
    },
    'decimal': {
        'name': '1. 1.1 1.1.1 1.1.1.1',
        'description': '纯数字格式（1. 2. 3...）',
        'levels': [
            {'ilvl': '0', 'numFmt': 'decimal', 'lvlText': '%1.', 'start': '1'},
            {'ilvl': '1', 'numFmt': 'decimal', 'lvlText': '%1.%2.', 'start': '1'},
            {'ilvl': '2', 'numFmt': 'decimal', 'lvlText': '%1.%2.%3.', 'start': '1'},
            {'ilvl': '3', 'numFmt': 'decimal', 'lvlText': '%1.%2.%3.%4.', 'start': '1'},
            {'ilvl': '4', 'numFmt': 'decimal', 'lvlText': '%1.%2.%3.%4.%5.', 'start': '1'},
        ]
    }
}


def get_format(format_type: str) -> dict[str, Any]:
    """获取格式定义

    Args:
        format_type: 格式类型 ('chinese' 或 'decimal')

    Returns:
        格式定义字典

    Raises:
        ValueError: 不支持的格式类型
    """
    if format_type not in NUMBERING_FORMATS:
        raise ValueError(f"不支持的格式类型: {format_type}，可选: {list(NUMBERING_FORMATS.keys())}")
    return NUMBERING_FORMATS[format_type]


def get_max_level(format_type: str) -> int:
    """获取格式的最大层级

    Args:
        format_type: 格式类型

    Returns:
        最大层级索引
    """
    format_def = get_format(format_type)
    return len(format_def['levels']) - 1
