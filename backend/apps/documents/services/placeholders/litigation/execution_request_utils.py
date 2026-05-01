"""强制执行申请书 - 共享工具函数."""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from .execution_request_models import FeeItem

AMOUNT_PATTERN = r"([0-9][0-9,]*(?:\.[0-9]+)?)"
AMOUNT_WITH_UNIT_PATTERN = rf"{AMOUNT_PATTERN}\s*(万)?\s*元?"

VALID_DATE_INCLUSION = {"both", "start_only", "end_only", "neither"}
VALID_YEAR_DAYS = {0, 360, 365}

FULLWIDTH_TRANSLATION = str.maketrans(
    {
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "．": ".",
        "，": ",",
        "％": "%",
        "：": ":",
        "（": "(",
        "）": ")",
        "　": " ",
    }
)


def parse_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    clean = raw.replace(",", "").strip()
    if not clean:
        return None
    try:
        return Decimal(clean)
    except (InvalidOperation, ValueError):
        return None


def safe_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def format_amount(amount: Decimal | None) -> str:
    if amount is None:
        return "0"
    quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return str(int(quantized))
    return format(quantized.normalize(), "f")


def build_date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def parse_amount_value(raw_amount: str | None, unit_marker: str | None = None) -> Decimal | None:
    amount = parse_decimal(raw_amount)
    if amount is None:
        return None
    if unit_marker and "万" in unit_marker:
        return amount * Decimal("10000")
    return amount


def parse_multiplier_value(raw: str | None) -> Decimal | None:
    value = parse_decimal(raw)
    if value is not None:
        return value
    if raw is None:
        return None

    clean = raw.strip()
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if clean == "十":
        return Decimal("10")
    if clean in digits:
        return Decimal(str(digits[clean]))

    if "十" in clean:
        left, right = clean.split("十", 1)
        if left:
            if left not in digits:
                return None
            tens = digits[left]
        else:
            tens = 1
        ones = 0
        if right:
            if right not in digits:
                return None
            ones = digits[right]
        return Decimal(str(tens * 10 + ones))
    return None


def extract_sentence(text: str, start: int, end: int) -> str:
    delimiters = ("。", "；", "\n")
    left = 0
    right = len(text)

    for delim in delimiters:
        pos = text.rfind(delim, 0, start)
        if pos >= 0:
            left = max(left, pos + 1)

    right_candidates: list[int] = []
    for delim in delimiters:
        pos = text.find(delim, end)
        if pos >= 0:
            right_candidates.append(pos)
    if right_candidates:
        right = min(right_candidates)

    return text[left:right].strip()


def normalize_text(text: str) -> str:
    normalized = text.translate(FULLWIDTH_TRANSLATION)
    normalized = re.sub(r" ", " ", normalized)
    normalized = re.sub(r"[ \t\r\f\v]+", " ", normalized)
    normalized = re.sub(r"\n+", "\n", normalized)
    return normalized


def normalize_year_days(value: int | None) -> int:
    if value in VALID_YEAR_DAYS:
        return int(value)
    return 360


def normalize_date_inclusion(value: str | None) -> str:
    if value in VALID_DATE_INCLUSION:
        return str(value)
    return "both"


def to_docx_hard_breaks(text: str) -> str:
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", "\a")
