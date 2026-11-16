"""字段级置信度计算（纯函数）。"""

from __future__ import annotations

from typing import Any

from ..validators import _validate_credit_code, _validate_id_number

# 字段级置信度：标签命中（卡片版式）> 叙述式命中 > 未命中；身份证号以校验位验证为准
_FIELD_CONF_LABEL = 0.95
_FIELD_CONF_NARRATIVE = 0.75
_FIELD_CONF_UNVERIFIED_ID = 0.6
_FIELD_CONF_ID_VERIFIED = 0.98
_FIELD_CONF_MISSING = 0.0


def _compute_id_card_field_confidence(extracted: dict[str, Any], narrative_used: bool) -> dict[str, float]:
    """身份证路径字段级置信度。"""
    if extracted.get("id_number"):
        id_conf = (
            _FIELD_CONF_ID_VERIFIED if _validate_id_number(extracted.get("id_number")) else _FIELD_CONF_UNVERIFIED_ID
        )
    else:
        id_conf = _FIELD_CONF_MISSING

    source_conf = _FIELD_CONF_NARRATIVE if narrative_used else _FIELD_CONF_LABEL
    confidence: dict[str, float] = {"id_number": id_conf}
    for key in ("name", "address", "gender", "ethnicity", "birth_date", "expiry_date", "phone"):
        confidence[key] = source_conf if extracted.get(key) else _FIELD_CONF_MISSING
    return confidence


def _compute_business_license_field_confidence(extracted: dict[str, Any]) -> dict[str, float]:
    """营业执照路径字段级置信度。"""
    if extracted.get("credit_code"):
        credit_conf = (
            _FIELD_CONF_ID_VERIFIED
            if _validate_credit_code(extracted.get("credit_code"))
            else _FIELD_CONF_UNVERIFIED_ID
        )
    else:
        credit_conf = _FIELD_CONF_MISSING

    confidence: dict[str, float] = {"credit_code": credit_conf}
    for key in ("company_name", "legal_representative", "address", "business_scope", "registration_date", "phone"):
        confidence[key] = _FIELD_CONF_LABEL if extracted.get(key) else _FIELD_CONF_MISSING
    return confidence


def _overall_confidence(extracted_data: dict[str, Any]) -> float:
    """整包置信度 = 命中字段的字段级置信度均值（无字段级置信度时回退 0.95）。"""
    field_conf: dict[str, float] | None = extracted_data.get("field_confidence")
    if not field_conf:
        return _FIELD_CONF_LABEL
    values = [v for v in field_conf.values() if v > _FIELD_CONF_MISSING]
    if not values:
        return _FIELD_CONF_MISSING
    return round(sum(values) / len(values), 2)
