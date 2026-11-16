"""叙述式文本（判决书/起诉状）当事人信息提取（纯函数）。"""

from __future__ import annotations

import re
from typing import Any

_NARRATIVE_NAME_RE = re.compile(
    r"(?:原告|被告|上诉人|被上诉人|申请人|被申请人|异议人|第三人)[一二三四五六七八九十]*[:：]\s*([一-龥·]{2,4})(?=[，,。；;])"
)
_NARRATIVE_GENDER_RE = re.compile(r"[，,]\s*(男|女)\s*[，,]")
_NARRATIVE_ETHNICITY_RE = re.compile(r"[，,]\s*([一-龥]{1,4}族)\s*[，,]")
_NARRATIVE_ADDRESS_RE = re.compile(
    r"(?:住|居住于|住所地|住址)[:：]?\s*([一-龥0-9]{2,60}?(?:省|市|县)?[一-龥0-9]*?(?:区|镇|乡)?[一-龥0-9]*(?:路|街|道|巷|村)[一-龥0-9]*(?:号|号院)[一-龥0-9]*(?:房|室|楼|座|栋|单元)?)"
)
_NARRATIVE_PHONE_RE = re.compile(r"(?:联系电话|电话|手机|联系方式)\s*[:：]?\s*(1[3-9]\d{9}|\d{3,4}-\d{7,8})")

# 叙述式地址边界截取：起点标签 → 下一个字段标签或句读为止
_NARRATIVE_ADDRESS_START_RE = re.compile(r"(?:住|居住于|住所地|住址|约定送达地址|送达地址)[:：]?")
_ADDRESS_BOUNDARY_RE = re.compile(r"公民身份|身份证号|联系电话|电话|手机|联系方式|出生|民族|有效期|邮编")


def _extract_narrative_address_by_boundary(flat: str) -> str | None:
    """叙述式地址边界截取：从「住/送达地址」起截取到下一个字段标签，不限地址形态。"""
    start = _NARRATIVE_ADDRESS_START_RE.search(flat)
    if not start:
        return None
    tail = flat[start.end() :]
    boundary = _ADDRESS_BOUNDARY_RE.search(tail)
    addr = tail[: boundary.start()] if boundary else tail
    addr = addr.strip("。，,;；、")
    return addr or None


def _extract_narrative_fields(text: str) -> dict[str, Any]:
    """从判决书/起诉状等叙述式文本中提取当事人信息（非证件卡片版式）。"""
    flat = text.replace("\n", "")
    fields: dict[str, Any] = {
        "name": None,
        "gender": None,
        "ethnicity": None,
        "address": None,
        "phone": None,
    }

    name_match = _NARRATIVE_NAME_RE.search(flat)
    if name_match:
        fields["name"] = name_match.group(1)

    gender_match = _NARRATIVE_GENDER_RE.search(flat)
    if gender_match:
        fields["gender"] = gender_match.group(1)

    ethnicity_match = _NARRATIVE_ETHNICITY_RE.search(flat)
    if ethnicity_match:
        fields["ethnicity"] = ethnicity_match.group(1)

    # 优先边界截取（覆盖任意地址形态），正则模式仅作兜底
    fields["address"] = _extract_narrative_address_by_boundary(flat)
    if not fields["address"]:
        address_match = _NARRATIVE_ADDRESS_RE.search(flat)
        if address_match:
            fields["address"] = address_match.group(1)

    phone_match = _NARRATIVE_PHONE_RE.search(flat)
    if phone_match:
        fields["phone"] = phone_match.group(1)

    return fields
