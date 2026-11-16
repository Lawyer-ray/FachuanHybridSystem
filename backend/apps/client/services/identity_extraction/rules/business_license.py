"""营业执照规则提取（纯函数）。"""

from __future__ import annotations

import re
from typing import Any

from ..text_cleaning import _normalize_ocr_text, _prepare_text_for_llm
from ..validators import _validate_credit_code
from .confidence import _compute_business_license_field_confidence


def _extract_business_license(raw_text: str) -> dict[str, Any] | None:
    """营业执照正则提取：企业名称、统一社会信用代码、法定代表人、地址、电话。"""
    text = _prepare_text_for_llm(_normalize_ocr_text(raw_text))
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # 统一社会信用代码（18位字母数字），多候选时优先选校验通过者
    credit_code = None
    for code_match in re.finditer(r"(?<![0-9A-Z])([0-9A-Z]{18})(?![0-9A-Z])", text.upper()):
        candidate = code_match.group(1)
        if not any(ch.isalpha() for ch in candidate):
            continue  # 纯数字串大概率是日期/号码，不是信用代码
        if _validate_credit_code(candidate):
            credit_code = candidate
            break
        if credit_code is None:
            credit_code = candidate

    # 企业名称（原告/被告/名称/公司 后面的内容）
    company_name = None
    for line in lines:
        m = re.search(r"(?:原告|被告|名称|公司名称|企业名称)[:：]\s*(.+)", line)
        if m:
            company_name = m.group(1).strip()
            break
    # 如果没匹配到前缀，尝试匹配"有限公司/股份公司"等模式
    if not company_name:
        m = re.search(r"([一-龥]+(?:有限公司|股份有限公司|集团|合伙企业))", text)
        if m:
            company_name = m.group(1)

    # 法定代表人
    legal_rep = None
    for line in lines:
        m = re.search(r"(?:法定代表人|负责人|经营者)[:：]\s*([一-龥·]{2,20})", line)
        if m:
            legal_rep = m.group(1).strip()
            break

    # 地址
    address = None
    for line in lines:
        m = re.search(r"(?:地址|住所|经营场所|住址)[:：]\s*(.+)", line)
        if m:
            address = m.group(1).strip()
            break

    # 联系电话
    phone = None
    phone_match = re.search(r"(?:联系电话|电话|手机|联系方式)[:：]\s*([0-9\-\+\s]{7,20})", text)
    if phone_match:
        phone = phone_match.group(1).replace(" ", "").strip()

    # 成立日期
    registration_date = None
    date_match = re.search(r"(?:成立日期|注册日期|营业期限)[:：]?\s*(\d{4})\D(\d{1,2})\D(\d{1,2})", text)
    if date_match:
        y_s, m_s, d_s = date_match.group(1), date_match.group(2), date_match.group(3)
        registration_date = f"{y_s}-{int(m_s):02d}-{int(d_s):02d}"

    # 经营范围
    business_scope = None
    for line in lines:
        m = re.search(r"(?:经营范围)[:：]\s*(.+)", line)
        if m:
            business_scope = m.group(1).strip()
            break

    extracted: dict[str, Any] = {
        "company_name": company_name,
        "credit_code": credit_code,
        "legal_representative": legal_rep,
        "address": address or "",
        "business_scope": business_scope,
        "registration_date": registration_date,
        "phone": phone or "",
    }

    # 如果一个字段都没提取到，返回 None 让后续流程处理
    if not any(extracted.values()):
        return None

    extracted["field_confidence"] = _compute_business_license_field_confidence(extracted)
    return extracted
