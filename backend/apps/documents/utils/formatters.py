"""Utility functions."""

from __future__ import annotations

"""
通用格式化工具

提供日期、货币、百分比等通用格式化方法.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# 默认日期格式
DEFAULT_DATE_FORMAT = "%Y年%m月%d日"


def format_date(d: date | None, fmt: str = DEFAULT_DATE_FORMAT) -> str:
    """
    格式化日期

    Args:
        d: 日期对象
        fmt: 日期格式字符串,默认为 "%Y年%m月%d日"

    Returns:
        格式化的日期字符串,如果日期为 None 则返回空字符串
    """
    if d is None:
        return ""
    try:
        return d.strftime(fmt)
    except Exception as e:
        logger.warning(f"格式化日期失败: {e}")
        return ""


def format_date_chinese(d: date | None, default_today: bool = False) -> str:
    """
    格式化日期为中文格式(月和日补零)

    Args:
        d: 日期对象
        default_today: 如果日期为 None,是否使用今天的日期

    Returns:
        格式化的日期字符串,如 "2024年01月15日"
    """
    if d is None:
        if default_today:
            d = date.today()
        else:
            return ""

    try:
        return f"{d.year}年{d.month:02d}月{d.day:02d}日"
    except Exception as e:
        logger.warning(f"格式化日期失败: {e}")
        return "____年____月____日"


def format_currency(amount: Decimal | None, include_symbol: bool = False) -> str:
    """
    格式化货币金额

    Args:
        amount: 金额
        include_symbol: 是否包含货币符号

    Returns:
        格式化的金额字符串,如 "1,234.56" 或 "¥1,234.56"
    """
    if amount is None:
        return ""

    try:
        formatted = f"{amount:,.2f}"
        if include_symbol:
            return f"¥{formatted}"
        return formatted
    except Exception as e:
        logger.warning(f"格式化货币失败: {e}")
        return ""


def format_percentage(rate: Decimal | None, decimal_places: int = 2) -> str:
    """
    格式化百分比

    Args:
        rate: 百分比数值(如 10 表示 10%)
        decimal_places: 小数位数

    Returns:
        格式化的百分比字符串,如 "10.00%"
    """
    if rate is None:
        return ""

    try:
        if decimal_places > 0:
            return f"{rate:.{decimal_places}f}%"
        return f"{rate}%"
    except Exception as e:
        logger.warning(f"格式化百分比失败: {e}")
        return ""


def get_choice_display(value: str, choices_class: type[Any]) -> str:
    """
    获取选项的显示文本

    Args:
        value: 选项值
        choices_class: Django TextChoices 类

    Returns:
        选项的显示文本,如果找不到则返回原值
    """
    if not value:
        return ""

    try:
        result = dict(choices_class.choices).get(value, value)
        return str(result) if result is not None else value
    except Exception as e:
        logger.warning(f"获取选项显示文本失败: {e}")
        return value
