"""中文格式化工具 — 集中化中文数字和日期格式，消除跨文件重复。"""

from __future__ import annotations

from datetime import date, datetime

# 中文数字 1-20
CHINESE_NUMBERS: list[str] = [
    "",  # 0 占位
    "一", "二", "三", "四", "五",
    "六", "七", "八", "九", "十",
    "十一", "十二", "十三", "十四", "十五",
    "十六", "十七", "十八", "十九", "二十",
]

# 中文数字 → 阿拉伯数字映射
CHINESE_TO_INT: dict[str, int] = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
}

# 阿拉伯数字 → 中文数字映射（2 → "两" 用于法律文书语境）
INT_TO_CHINESE_LEGAL: dict[int, str] = {
    1: "一", 2: "两", 3: "三", 4: "四", 5: "五",
    6: "六", 7: "七", 8: "八", 9: "九", 10: "十",
}

# 中文日期格式
DATE_FORMAT_CHINESE = "%Y年%m月%d日"


def int_to_chinese(n: int) -> str:
    """将阿拉伯数字转为中文数字（1-20）。"""
    if 0 <= n < len(CHINESE_NUMBERS):
        return CHINESE_NUMBERS[n]
    return str(n)


def int_to_chinese_legal(n: int) -> str:
    """将阿拉伯数字转为中文数字（法律文书语境，2→"两"）。"""
    return INT_TO_CHINESE_LEGAL.get(n, str(n))


def chinese_to_int(s: str) -> int | None:
    """将中文数字转为阿拉伯数字。返回 None 表示无法识别。"""
    return CHINESE_TO_INT.get(s.strip())


def format_date_chinese(d: date | datetime | None) -> str:
    """格式化日期为中文格式（2026年06月21日）。"""
    if d is None:
        return ""
    return d.strftime(DATE_FORMAT_CHINESE)
