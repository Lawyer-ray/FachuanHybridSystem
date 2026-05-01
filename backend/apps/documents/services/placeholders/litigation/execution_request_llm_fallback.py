"""强制执行申请书 - LLM/Ollama 兜底解析."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any

from .execution_request_models import ParsedAmounts, ParsedInterestParams
from .execution_request_utils import format_amount, parse_decimal, safe_decimal

logger = logging.getLogger(__name__)

OLLAMA_FALLBACK_MODEL = "qwen3.5:0.8b"
OLLAMA_MAX_TEXT_CHARS = 12000


def should_try_llm_fallback(
    *,
    text: str,
    amounts: ParsedAmounts,
    params: ParsedInterestParams,
    principal_fallback_to_target: bool,
) -> bool:
    if principal_fallback_to_target:
        return True

    principal = amounts.principal or Decimal("0")
    if re.search(r"[0-9]+\s*万\s*元", text) and principal < Decimal("10000"):
        return True

    if amounts.litigation_fee <= 0 and _has_fee_prepaid_context(text, fee_keywords=("受理费",)):
        return True
    if amounts.preservation_fee <= 0 and _has_fee_prepaid_context(
        text,
        fee_keywords=("保全费", "财产保全费", "财产保全申请费"),
    ):
        return True

    if params.start_date and params.multiplier is None and params.custom_rate_value is None:
        return True
    return False


def _has_fee_prepaid_context(text: str, *, fee_keywords: tuple[str, ...]) -> bool:
    prepaid_markers = ("预交", "已缴", "已交", "先行垫付")
    for sentence in re.split(r"[。；\n]", text):
        compact = sentence.replace(" ", "").strip()
        if not compact:
            continue
        if not any(keyword in compact for keyword in fee_keywords):
            continue
        if "负担" not in compact:
            continue
        if any(marker in compact for marker in prepaid_markers):
            return True
    return False


def merge_llm_fallback(
    *,
    amounts: ParsedAmounts,
    params: ParsedInterestParams,
    llm_data: dict[str, Any],
    principal_fallback_to_target: bool,
) -> bool:
    changed = False

    llm_principal = llm_data.get("principal_amount")
    if isinstance(llm_principal, Decimal) and llm_principal > 0:
        current_principal = amounts.principal or Decimal("0")
        if (
            principal_fallback_to_target
            or current_principal <= 0
            or (current_principal < Decimal("10000") and llm_principal >= Decimal("10000"))
        ):
            amounts.principal = llm_principal
            principal_desc = str(llm_data.get("principal_label") or "").strip()
            if "货" in principal_desc:
                amounts.principal_label = "货款本金"
            elif principal_desc:
                amounts.principal_label = "借款本金"
            changed = True

    for field_name, key in (
        ("litigation_fee", "litigation_fee"),
        ("preservation_fee", "preservation_fee"),
        ("announcement_fee", "announcement_fee"),
        ("attorney_fee", "attorney_fee"),
        ("guarantee_fee", "guarantee_fee"),
    ):
        current = getattr(amounts, field_name)
        llm_value = llm_data.get(key)
        if current <= 0 and isinstance(llm_value, Decimal) and llm_value > 0:
            setattr(amounts, field_name, llm_value)
            changed = True

    llm_start_date = llm_data.get("interest_start_date")
    if params.start_date is None and isinstance(llm_start_date, date):
        params.start_date = llm_start_date
        changed = True

    llm_lpr_multiplier = llm_data.get("lpr_multiplier")
    if (
        params.multiplier is None
        and params.custom_rate_value is None
        and isinstance(llm_lpr_multiplier, Decimal)
        and llm_lpr_multiplier > 0
    ):
        params.multiplier = llm_lpr_multiplier
        params.rate_type = "1y"
        params.rate_description = (
            f"全国银行间同业拆借中心公布的一年期贷款市场报价利率的{format_amount(llm_lpr_multiplier)}倍"
        )
        changed = True

    llm_fixed_rate = llm_data.get("fixed_rate_percent")
    if (
        params.multiplier is None
        and params.custom_rate_value is None
        and isinstance(llm_fixed_rate, Decimal)
        and llm_fixed_rate > 0
    ):
        params.custom_rate_unit = "percent"
        params.custom_rate_value = llm_fixed_rate
        params.rate_description = f"年利率{format_amount(llm_fixed_rate)}%"
        changed = True

    llm_interest_base = llm_data.get("interest_base_amount")
    if isinstance(llm_interest_base, Decimal) and llm_interest_base > 0:
        if params.base_amount is None or (
            params.base_amount < Decimal("10000") and llm_interest_base >= Decimal("10000")
        ):
            params.base_mode = "fixed_amount"
            params.base_amount = llm_interest_base
            changed = True

    return changed


def extract_with_ollama_fallback(main_text: str) -> dict[str, Any] | None:
    prompt = (
        "你是法律文书金额与利率解析助手。仅输出 JSON，不要输出其他文字。\n"
        "要求：所有金额统一换算为“元”（例如“52万元”=520000）；利率倍数用数字表示。\n"
        "只返回以下 JSON 字段：\n"
        "{\n"
        '  "principal_amount_yuan": number|null,\n'
        '  "principal_label": "借款本金|货款本金|本金|",\n'
        '  "interest_start_date": "YYYY-MM-DD"|null,\n'
        '  "interest_base_amount_yuan": number|null,\n'
        '  "lpr_multiplier": number|null,\n'
        '  "fixed_rate_percent": number|null,\n'
        '  "litigation_fee": number|null,\n'
        '  "preservation_fee": number|null,\n'
        '  "announcement_fee": number|null,\n'
        '  "attorney_fee": number|null,\n'
        '  "guarantee_fee": number|null,\n'
        '  "has_double_interest_clause": true|false\n'
        "}\n"
        "文书如下：\n"
        f"{main_text[: OLLAMA_MAX_TEXT_CHARS]}"
    )

    try:
        from apps.core.services.wiring import get_llm_service

        response = get_llm_service().complete(
            prompt=prompt,
            backend="ollama",
            model=OLLAMA_FALLBACK_MODEL,
            temperature=0.1,
            max_tokens=500,
            fallback=False,
            timeout=8.0,
            num_predict=500,
        )
        content = str(getattr(response, "content", "") or "")
    except Exception:
        logger.exception("execution_request_ollama_fallback_failed")
        return None

    payload = _extract_json_object(content)
    if not isinstance(payload, dict):
        return None

    parsed: dict[str, Any] = {
        "principal_amount": safe_decimal(payload.get("principal_amount_yuan")),
        "principal_label": str(payload.get("principal_label") or "").strip(),
        "interest_base_amount": safe_decimal(payload.get("interest_base_amount_yuan")),
        "lpr_multiplier": safe_decimal(payload.get("lpr_multiplier")),
        "fixed_rate_percent": safe_decimal(payload.get("fixed_rate_percent")),
        "litigation_fee": safe_decimal(payload.get("litigation_fee")),
        "preservation_fee": safe_decimal(payload.get("preservation_fee")),
        "announcement_fee": safe_decimal(payload.get("announcement_fee")),
        "attorney_fee": safe_decimal(payload.get("attorney_fee")),
        "guarantee_fee": safe_decimal(payload.get("guarantee_fee")),
        "has_double_interest_clause": _parse_bool(payload.get("has_double_interest_clause")),
    }

    start_date_value = payload.get("interest_start_date")
    parsed["interest_start_date"] = _parse_iso_date(start_date_value)
    return parsed


def _extract_json_object(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text:
        return None

    candidates = [text]
    candidates.extend(re.findall(r"\{[\s\S]*\}", text))
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    candidates.extend(fenced)

    for candidate in candidates:
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            continue
    return None


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        year, month, day = text.split("-")
        return date(int(year), int(month), int(day))
    except Exception:
        return None


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "是"}:
        return True
    if text in {"false", "0", "no", "n", "否"}:
        return False
    return False
