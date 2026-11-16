"""当事人字段提取（证件号/地址/电话/法定代表人）与主体类型判定。"""

from __future__ import annotations

import re
from typing import Any

from .names import _clean_name_candidate
from .patterns import (
    _ADDRESS_LINE_FALLBACK_PATTERN,
    _ADDRESS_PATTERN,
    _CREDIT_CODE_FALLBACK_PATTERN,
    _CREDIT_CODE_PATTERN,
    _ID_NUMBER_FALLBACK_PATTERN,
    _ID_NUMBER_PATTERN,
    _LEGAL_KEYWORDS,
    _LEGAL_REP_PATTERN,
    _PHONE_FALLBACK_PATTERN,
    _PHONE_PATTERN,
    _WHITESPACE_PATTERN,
)


def _extract_credit_code(text: str) -> str | None:
    """提取统一社会信用代码"""
    match = _CREDIT_CODE_PATTERN.search(text)
    if match:
        return match.group(1).strip().upper()

    # 无标签兜底：仅接受含字母的18位编码，避免误判身份证号
    # 但需要排除明显是身份证号的情况（文本中有"身份证"关键词）
    for fallback_match in _CREDIT_CODE_FALLBACK_PATTERN.finditer(text):
        code = fallback_match.group(1).strip().upper()
        if not any(ch.isalpha() for ch in code):
            continue
        # 排除身份证号：如果编码附近有"身份证"关键词，跳过
        # 计算编码在文本中的位置
        start_pos = fallback_match.start()
        end_pos = fallback_match.end()
        # 检查前面 20 个字符内是否有"身份证"
        context_before = text[max(0, start_pos - 20) : start_pos].lower()
        if "身份证" in context_before:
            continue
        return code

    return None


def _extract_id_number(text: str) -> str | None:
    """提取身份证号码"""
    match = _ID_NUMBER_PATTERN.search(text)
    if match:
        return match.group(1).strip().upper()

    fallback = _ID_NUMBER_FALLBACK_PATTERN.search(text)
    return fallback.group(1).strip().upper() if fallback else None


def _extract_address(text: str) -> str | None:
    """提取地址"""
    match = _ADDRESS_PATTERN.search(text)
    if match:
        address = match.group(1).strip()
        if address:
            return address

    # 无标签兜底：从明显的省市开头行提取
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and _ADDRESS_LINE_FALLBACK_PATTERN.fullmatch(line):
            return line
    return None


def _extract_phone(text: str) -> str | None:
    """提取电话号码"""
    match = _PHONE_PATTERN.search(text)
    if match:
        phone = _WHITESPACE_PATTERN.sub("", match.group(1).strip())
        if phone:
            return phone

    # 无标签兜底：优先手机号，其次座机
    fallback_phone: str | None = None
    for fallback in _PHONE_FALLBACK_PATTERN.finditer(text):
        candidate = _WHITESPACE_PATTERN.sub("", fallback.group(1).strip())
        digits_only = re.sub(r"\D", "", candidate)
        if len(digits_only) == 11 and digits_only.startswith("1"):
            return candidate
        if fallback_phone is None:
            fallback_phone = candidate
    return fallback_phone


def _extract_legal_representative(text: str) -> str | None:
    """提取法定代表人"""
    match = _LEGAL_REP_PATTERN.search(text)
    if not match:
        return None
    legal_rep = _clean_name_candidate(match.group(1))
    return legal_rep or None


def _determine_client_type(name: str, text: str) -> str:
    """根据名称和文本内容判断客户类型"""
    if _extract_credit_code(text):
        return "legal"
    if _extract_legal_representative(text):
        return "legal"
    if any(kw in name for kw in _LEGAL_KEYWORDS):
        return "legal"
    if _extract_id_number(text):
        return "natural"
    return "natural"


def _empty_result() -> dict[str, Any]:
    """返回空的解析结果"""
    return {
        "name": "",
        "phone": "",
        "address": "",
        "client_type": "natural",
        "id_number": "",
        "legal_representative": "",
    }
