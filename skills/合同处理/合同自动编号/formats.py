"""
格式定义模块

定义支持的编号格式和相关常量。
"""

from typing import Any

# 签字盖章部分的关键词
SIGNATURE_KEYWORDS: list[str] = [
    '以下无正文',
    '签约页',
    '（盖章）',
    '(盖章)',
    '授权代表签字',
    '签订日期',
    '甲方（盖章）',
    '乙方（盖章）',
    '丙方（盖章）',
    '丁方（盖章）',
]

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
