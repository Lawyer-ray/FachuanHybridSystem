"""法院一张网申请担保 API — 辅助函数。"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.utils import timezone

from .court_guarantee_schemas import (
    _BROWSER_HOLD_SECONDS,
    _BROWSER_HOLD_SECONDS_ON_FAILURE,
    _BROWSER_SLOW_MO_MS,
    _DEFAULT_INSURANCE_COMPANY,
    _DEFAULT_LEGAL_ID_NUMBER,
    _DEFAULT_NATURAL_ID_NUMBER,
    _GUARANTEE_INSURANCE_COMPANY_OPTIONS,
    _PROPERTY_CLUE_TYPE_DISPLAY,
    _QUOTE_RETRY_ALLOWED_STATUSES,
    _RESPONDENT_SIDE_STATUSES,
    _SUNSHINE_DEFAULT_CONSULTANT_CODE,
    _SUNSHINE_INSURANCE_COMPANY,
)

logger = logging.getLogger("apps.automation")

_SESSION_UPDATE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="court-guarantee-session")


def _get_organization_service() -> Any:
    from apps.core.dependencies import build_organization_service

    return build_organization_service()


def _get_client_service() -> Any:
    from apps.core.dependencies import build_client_service

    return build_client_service()


def _get_case_number(case: Any) -> str:
    case_number_from_table = (
        case.case_numbers.exclude(number__isnull=True).exclude(number="").values_list("number", flat=True).first()
    )
    if case_number_from_table:
        return str(case_number_from_table)

    filing_number = str(getattr(case, "filing_number", "") or "").strip()
    return filing_number


def _has_case_number(case: Any) -> bool:
    return bool(_get_case_number(case))


def _get_case_court_name(case: Any) -> str | None:
    from apps.core.models.enums import AuthorityType

    authorities = case.supervising_authorities.all().order_by("id")
    trial_authority = authorities.filter(authority_type=AuthorityType.TRIAL).first()
    if trial_authority and str(getattr(trial_authority, "name", "") or "").strip():
        return _resolve_court_name(trial_authority.name)

    any_named_authority = authorities.exclude(name__isnull=True).exclude(name="").first()
    if any_named_authority and any_named_authority.name:
        return _resolve_court_name(any_named_authority.name)

    return None


def _resolve_court_name(authority_name: str | None) -> str | None:
    normalized_authority_name = str(authority_name or "").strip()
    if not normalized_authority_name:
        return None
    if "人民法院" in normalized_authority_name:
        return normalized_authority_name

    from apps.core.models import Court

    court = Court.objects.filter(name__contains=normalized_authority_name).first()
    if court and court.name:
        return str(court.name)
    return f"{normalized_authority_name}人民法院"


def _normalize_insurance_company(name: str, *, allowed_options: list[str] | None = None) -> str:
    normalized_name = name.strip()
    if not normalized_name:
        if allowed_options:
            return allowed_options[0]
        return _DEFAULT_INSURANCE_COMPANY

    if allowed_options:
        if normalized_name in allowed_options:
            return normalized_name
        return allowed_options[0]

    if normalized_name in _GUARANTEE_INSURANCE_COMPANY_OPTIONS:
        return normalized_name
    return _DEFAULT_INSURANCE_COMPANY


def _parse_preserve_amount(raw_value: Any) -> Decimal | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, Decimal):
        return raw_value
    try:
        return Decimal(str(raw_value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _normalize_consultant_code(*, insurance_company_name: str, consultant_code: str | None) -> str:
    normalized_code = str(consultant_code or "").strip()
    normalized_company = str(insurance_company_name or "").strip()
    if _SUNSHINE_INSURANCE_COMPANY in normalized_company and not normalized_code:
        return _SUNSHINE_DEFAULT_CONSULTANT_CODE
    return normalized_code


def _normalize_property_clue_content(raw_content: str) -> str:
    content = str(raw_content or "").strip()
    if not content:
        return ""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return ""
    return "；".join(lines)


def _normalize_property_value(raw_value: Any | None) -> str:
    if raw_value is None:
        return ""
    normalized_property_value = str(raw_value).strip().replace(",", "")
    if "." in normalized_property_value:
        normalized_property_value = normalized_property_value.rstrip("0").rstrip(".")
    return normalized_property_value


def _build_property_clue_info(*, clue_type: str, raw_content: str) -> str:
    normalized_type = str(clue_type or "").strip()
    type_display = _PROPERTY_CLUE_TYPE_DISPLAY.get(normalized_type, normalized_type or "财产线索")
    normalized_content = _normalize_property_clue_content(raw_content)
    if normalized_content:
        return f"{type_display}：{normalized_content}"
    return type_display


def _build_selected_respondent_property_clues(
    *,
    case_parties: list[Any],
    selected_respondents: list[dict[str, Any]],
    preserve_amount: Any | None = None,
) -> list[dict[str, str]]:
    party_id_set = {
        int(item.get("party_id") or 0) for item in selected_respondents if int(item.get("party_id") or 0) > 0
    }
    selected_case_parties = [party for party in case_parties if int(getattr(party, "id", 0) or 0) in party_id_set]
    if not selected_case_parties:
        selected_case_parties = _list_opponent_case_parties(case_parties=case_parties)

    normalized_property_value = _normalize_property_value(preserve_amount)
    client_service = _get_client_service()
    property_clues: list[dict[str, str]] = []

    for party in selected_case_parties:
        client = getattr(party, "client", None)
        owner_name = (
            str(getattr(client, "name", "") or "").strip() or str(getattr(party, "name", "") or "被申请人").strip()
        )
        property_location = str(getattr(client, "address", "") or "").strip() if client is not None else ""

        clue_dtos = (
            client_service.get_property_clues_by_client_internal(int(getattr(client, "id", 0) or 0))
            if client is not None and int(getattr(client, "id", 0) or 0) > 0
            else []
        )
        for clue in clue_dtos:
            property_info = _build_property_clue_info(
                clue_type=str(getattr(clue, "clue_type", "") or ""),
                raw_content=str(getattr(clue, "content", "") or ""),
            )
            property_clues.append(
                {
                    "owner_name": owner_name,
                    "property_type": "其他",
                    "property_info": property_info or f"{owner_name}名下财产线索",
                    "property_location": property_location,
                    "property_province": "",
                    "property_cert_no": "",
                    "property_value": normalized_property_value,
                }
            )

        if clue_dtos:
            continue

        property_clues.append(
            {
                "owner_name": owner_name,
                "property_type": "其他",
                "property_info": f"{owner_name}名下财产线索",
                "property_location": property_location,
                "property_province": "",
                "property_cert_no": "",
                "property_value": normalized_property_value,
            }
        )

    return property_clues


def _build_primary_respondent_property_clue(
    *,
    case_parties: list[Any],
    selected_respondents: list[dict[str, Any]],
    preserve_amount: Any | None = None,
) -> dict[str, str]:
    property_clues = _build_selected_respondent_property_clues(
        case_parties=case_parties,
        selected_respondents=selected_respondents,
        preserve_amount=preserve_amount,
    )
    if property_clues:
        return property_clues[0]
    return {
        "owner_name": "被申请人",
        "property_type": "其他",
        "property_info": "被申请人名下财产线索",
        "property_location": "",
        "property_province": "",
        "property_cert_no": "",
        "property_value": _normalize_property_value(preserve_amount),
    }


def _find_reusable_binding(*, case_id: int, preserve_amount: Decimal) -> Any | None:
    from apps.automation.models import CasePreservationQuoteBinding

    return (
        CasePreservationQuoteBinding.objects.select_related("preservation_quote")
        .filter(case_id=case_id, preserve_amount_snapshot=preserve_amount)
        .order_by("-created_at")
        .first()
    )


def _build_case_quote_context(*, case: Any) -> dict[str, Any] | None:
    from apps.automation.models import CasePreservationQuoteBinding, QuoteItemStatus

    preserve_amount = _parse_preserve_amount(getattr(case, "preservation_amount", None))
    if preserve_amount is None:
        return None

    binding = _find_reusable_binding(case_id=int(case.id), preserve_amount=preserve_amount)
    if binding is None:
        binding = (
            CasePreservationQuoteBinding.objects.select_related("preservation_quote")
            .filter(case_id=case.id)
            .order_by("-created_at")
            .first()
        )
    if binding is None:
        return None

    quote = binding.preservation_quote
    quote_items: list[dict[str, Any]] = []

    successful_items = list(
        quote.quotes.filter(status=QuoteItemStatus.SUCCESS).order_by("min_amount", "max_amount", "id")
    )
    recommended_company: str | None = None
    if successful_items:
        recommended_company = str(successful_items[0].company_name)

    for item in successful_items:
        premium = str(item.premium) if item.premium is not None else ""
        min_amount = str(item.min_amount) if item.min_amount is not None else ""
        max_amount = str(item.max_amount) if item.max_amount is not None else ""
        max_apply_amount = str(item.max_apply_amount) if item.max_apply_amount is not None else ""

        quote_items.append(
            {
                "id": int(item.id),
                "company_name": str(item.company_name),
                "premium": premium,
                "min_amount": min_amount,
                "max_amount": max_amount,
                "max_apply_amount": max_apply_amount,
                "status": str(item.status),
                "error_message": str(item.error_message or ""),
                "is_recommended": recommended_company == str(item.company_name),
            }
        )

    return {
        "binding_id": int(binding.id),
        "quote_id": int(quote.id),
        "status": str(quote.status),
        "error_message": str(quote.error_message or ""),
        "preserve_amount_snapshot": str(binding.preserve_amount_snapshot),
        "recommended_company": recommended_company,
        "can_retry": quote.status in _QUOTE_RETRY_ALLOWED_STATUSES,
        "created_at": quote.created_at.isoformat() if quote.created_at else None,
        "finished_at": quote.finished_at.isoformat() if quote.finished_at else None,
        "success_count": int(quote.success_count),
        "failed_count": int(quote.failed_count),
        "total_companies": int(quote.total_companies),
        "items": quote_items,
    }


def _build_reusable_quote_options(*, case: Any) -> list[dict[str, Any]]:
    from apps.automation.models import CasePreservationQuoteBinding, PreservationQuote, QuoteStatus

    preserve_amount = _parse_preserve_amount(getattr(case, "preservation_amount", None))
    if preserve_amount is None or preserve_amount <= 0:
        return []

    bound_quote_ids = set(
        CasePreservationQuoteBinding.objects.filter(case_id=int(case.id)).values_list(
            "preservation_quote_id", flat=True
        )
    )

    reusable_quotes = (
        PreservationQuote.objects.filter(preserve_amount=preserve_amount)
        .filter(status__in=[QuoteStatus.SUCCESS, QuoteStatus.PARTIAL_SUCCESS, QuoteStatus.RUNNING, QuoteStatus.PENDING])
        .order_by("-created_at")[:30]
    )

    return [
        {
            "quote_id": int(quote.id),
            "status": str(quote.status),
            "success_count": int(quote.success_count),
            "total_companies": int(quote.total_companies),
            "created_at": quote.created_at.isoformat() if quote.created_at else None,
            "created_at_display": (
                timezone.localtime(quote.created_at, timezone.get_fixed_timezone(480)).strftime("%Y-%m-%d %H:%M")
                if quote.created_at
                else None
            ),
            "preserve_amount": str(quote.preserve_amount),
            "is_bound": int(quote.id) in bound_quote_ids,
        }
        for quote in reusable_quotes
    ]


def _extract_quote_company_options(*, quote_context: dict[str, Any] | None) -> list[str]:
    if not quote_context:
        return []

    items = quote_context.get("items") if isinstance(quote_context, dict) else None
    if not isinstance(items, list):
        return []

    preferred: list[str] = []
    fallback: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        company_name = str(item.get("company_name") or "").strip()
        if not company_name:
            continue
        if str(item.get("status") or "") == "success":
            preferred.append(company_name)
        else:
            fallback.append(company_name)

    dedup: list[str] = []
    seen: set[str] = set()
    for name in [*preferred, *fallback]:
        if name in seen:
            continue
        seen.add(name)
        dedup.append(name)
    return dedup


def _resolve_insurance_company_defaults(*, quote_context: dict[str, Any] | None) -> tuple[str, list[str]]:
    quote_options = _extract_quote_company_options(quote_context=quote_context)
    if quote_options:
        recommended = str((quote_context or {}).get("recommended_company") or "").strip()
        if recommended and recommended in quote_options:
            return recommended, quote_options
        return quote_options[0], quote_options
    return _DEFAULT_INSURANCE_COMPANY, _GUARANTEE_INSURANCE_COMPANY_OPTIONS


def _build_guarantee_material_paths(case: Any) -> list[dict[str, str]]:
    """构建担保立案材料列表，返回 ``[{"path": ..., "type_name": ...}, ...]``。

    type_name 来自 CaseMaterial.type_name（用户/系统明确分类），供 Playwright 层
    做精确匹配，避免文件名歧义（如"营业执照"出现在"委托材料"类型中）。
    """
    from django.db.models import Q

    from apps.cases.models import CaseMaterial, CaseMaterialCategory, CaseMaterialSide

    allowed_suffixes = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}

    def _collect(qs: Any) -> list[tuple[int, str, str, str]]:
        files: list[tuple[int, str, str, str]] = []
        for material in qs.select_related("source_attachment").order_by("id"):
            attachment = getattr(material, "source_attachment", None)
            if attachment is None or not getattr(attachment, "file", None):
                continue
            try:
                file_path = Path(str(attachment.file.path))
            except Exception:
                continue
            if not file_path.exists() or file_path.suffix.lower() not in allowed_suffixes:
                continue
            files.append(
                (
                    int(getattr(material, "id", 0) or 0),
                    str(getattr(material, "type_name", "") or ""),
                    str(file_path.name),
                    file_path.as_posix(),
                )
            )
        return files

    def _pick(
        *,
        records: list[tuple[int, str, str, str]],
        keywords: list[str],
        used: set[str],
        type_name_keywords: list[str] | None = None,
    ) -> tuple[str, str] | None:
        primary_keywords = type_name_keywords or keywords
        for _, type_name, filename, path in records:
            if path in used:
                continue
            if any(keyword in type_name for keyword in primary_keywords):
                return path, type_name
        for _, type_name, filename, path in records:
            if path in used:
                continue
            haystack = f"{type_name} {filename}"
            if any(keyword in haystack for keyword in keywords):
                return path, type_name
        return None

    our_party_qs = CaseMaterial.objects.filter(case=case, category=CaseMaterialCategory.PARTY).filter(
        Q(side=CaseMaterialSide.OUR) | Q(side__isnull=True) | Q(side="")
    )
    non_party_qs = CaseMaterial.objects.filter(case=case, category=CaseMaterialCategory.NON_PARTY)

    our_files = _collect(our_party_qs)
    non_party_files = _collect(non_party_qs)

    selected: list[dict[str, str]] = []
    used: set[str] = set()

    required_rules: list[tuple[list[tuple[int, str, str, str]], list[str], list[str] | None]] = [
        (our_files, ["财产保全申请书", "保全申请书"], ["保全申请", "保全", "保全申请书及保函"]),
        (our_files, ["起诉状", "起诉书", "起诉"], ["起诉状"]),
        (non_party_files, ["立案受理通知书", "受理通知书", "立案通知书", "受理通知", "立案通知"], None),
        (our_files, ["身份证明", "营业执照", "身份证", "法定代表人身份证明"], ["身份证明", "当事人身份证明"]),
        (our_files, ["证据", "证据材料", "明细", "清单"], ["证据"]),
    ]

    for records, keywords, type_name_keywords in required_rules:
        picked = _pick(records=records, keywords=keywords, used=used, type_name_keywords=type_name_keywords)
        if not picked:
            continue
        path, type_name = picked
        used.add(path)
        selected.append({"path": path, "type_name": type_name})

    for records in (our_files, non_party_files):
        for _, type_name, _, path in records:
            if path in used:
                continue
            used.add(path)
            selected.append({"path": path, "type_name": type_name})
            if len(selected) >= 12:
                return selected

    return selected


def _build_cause_candidates(raw_cause: str) -> list[str]:
    text = str(raw_cause or "").replace("　", " ").strip()
    if not text:
        return []

    candidates: list[str] = []
    for part in [text, *re.split(r"[、,，;；/\\|\n]+", text)]:
        token = str(part).strip()
        if not token:
            continue
        candidates.append(token)
        if token.endswith("纠纷"):
            candidates.append(token.removesuffix("纠纷"))

    dedup: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        dedup.append(normalized)
    return dedup[:8]


def _normalize_party_type(raw_party_type: Any) -> str:
    value = str(raw_party_type or "").strip().lower()
    if value in {"natural", "person", "individual"}:
        return "natural"
    if value in {"legal", "corp", "company", "enterprise", "organization", "org"}:
        return "legal"
    if value in {"non_legal_org", "nonlegal", "non_legal", "other_org"}:
        return "non_legal_org"
    return "natural"


def _build_party_payload_from_case_party(*, party: Any) -> dict[str, Any]:
    client = getattr(party, "client", None)
    party_type = _normalize_party_type(getattr(client, "client_type", "natural"))
    is_natural = party_type == "natural"

    name = str(getattr(client, "name", "") or "").strip() or "张三"
    id_number = str(getattr(client, "id_number", "") or "").strip()
    if not id_number:
        id_number = _DEFAULT_NATURAL_ID_NUMBER if is_natural else _DEFAULT_LEGAL_ID_NUMBER

    phone = str(getattr(client, "phone", "") or "").strip()
    address = str(getattr(client, "address", "") or "").strip() or "广东省广州市天河区测试地址1号"
    legal_representative = str(getattr(client, "legal_representative", "") or "").strip()
    legal_representative_id_number = str(getattr(client, "legal_representative_id_number", "") or "").strip()

    return {
        "party_id": int(getattr(party, "id", 0) or 0),
        "party_type": party_type,
        "name": name,
        "id_number": id_number,
        "phone": phone,
        "address": address,
        "legal_representative": legal_representative,
        "legal_representative_id_number": legal_representative_id_number,
    }


def _list_party_payloads(
    *, case_parties: list[Any], preferred_statuses: set[str], prefer_our: bool
) -> list[dict[str, Any]]:
    def _match_status_and_side(party: Any) -> bool:
        status = str(getattr(party, "legal_status", "") or "").strip()
        if status not in preferred_statuses:
            return False
        client = getattr(party, "client", None)
        is_our = bool(getattr(client, "is_our_client", False))
        return is_our if prefer_our else (not is_our)

    candidates = [p for p in case_parties if _match_status_and_side(p)]
    if not candidates:
        candidates = [
            p for p in case_parties if str(getattr(p, "legal_status", "") or "").strip() in preferred_statuses
        ]
    if not candidates:
        candidates = [
            p for p in case_parties if bool(getattr(getattr(p, "client", None), "is_our_client", False)) == prefer_our
        ]
    if not candidates and case_parties:
        candidates = [case_parties[0]]

    return [_build_party_payload_from_case_party(party=party) for party in candidates]


def _pick_party_payload(*, case_parties: list[Any], preferred_statuses: set[str], prefer_our: bool) -> dict[str, Any]:
    payloads = _list_party_payloads(
        case_parties=case_parties,
        preferred_statuses=preferred_statuses,
        prefer_our=prefer_our,
    )
    if payloads:
        return payloads[0]
    return _build_party_payload_from_case_party(party=None)


def _normalize_selected_party_ids(raw_ids: list[int] | None) -> set[int] | None:
    if raw_ids is None:
        return None
    ids: set[int] = set()
    for raw in raw_ids:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            ids.add(value)
    return ids


def _list_opponent_case_parties(*, case_parties: list[Any]) -> list[Any]:
    opponents = [
        party for party in case_parties if not bool(getattr(getattr(party, "client", None), "is_our_client", False))
    ]
    if opponents:
        return opponents

    fallback = [
        party
        for party in case_parties
        if str(getattr(party, "legal_status", "") or "").strip() in _RESPONDENT_SIDE_STATUSES
    ]
    if fallback:
        return fallback

    return list(case_parties)


def _list_opponent_party_payloads(*, case_parties: list[Any]) -> list[dict[str, Any]]:
    return [
        _build_party_payload_from_case_party(party=party)
        for party in _list_opponent_case_parties(case_parties=case_parties)
    ]


def _build_respondent_options(*, case_parties: list[Any]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for party in _list_opponent_case_parties(case_parties=case_parties):
        status = str(getattr(party, "legal_status", "") or "").strip()
        client = getattr(party, "client", None)
        options.append(
            {
                "party_id": int(getattr(party, "id", 0) or 0),
                "name": str(getattr(client, "name", "") or "").strip() or "-",
                "legal_status": status,
                "legal_status_display": str(party.get_legal_status_display() or status),
                "is_our_client": bool(getattr(client, "is_our_client", False)),
            }
        )

    return options


def _build_plaintiff_agent_payload(
    *, case: Any, requester_id: int | None, fallback_party: dict[str, Any]
) -> dict[str, str]:
    from apps.organization.models import Lawyer

    lawyer = None
    if requester_id is not None:
        lawyer = Lawyer.objects.select_related("law_firm").filter(id=int(requester_id)).first()

    if lawyer is None:
        assignment = case.assignments.select_related("lawyer__law_firm").order_by("id").first()
        lawyer = getattr(assignment, "lawyer", None)

    fallback_name = str(fallback_party.get("name") or "").strip() or "张三"
    if lawyer is None:
        return {
            "party_type": "agent",
            "name": fallback_name,
            "id_number": "",
            "phone": str(fallback_party.get("phone") or "").strip(),
            "law_firm": "",
            "license_number": "",
        }

    real_name = str(getattr(lawyer, "real_name", "") or "").strip()
    username = str(getattr(lawyer, "username", "") or "").strip()
    law_firm = getattr(lawyer, "law_firm", None)

    return {
        "party_type": "agent",
        "name": real_name or username or fallback_name,
        "id_number": str(getattr(lawyer, "id_card", "") or "").strip(),
        "phone": str(getattr(lawyer, "phone", "") or "").strip() or str(fallback_party.get("phone") or "").strip(),
        "law_firm": str(getattr(law_firm, "name", "") or "").strip(),
        "license_number": str(getattr(lawyer, "license_no", "") or "").strip(),
    }


def _build_session_status_payload(*, task: Any) -> dict[str, Any]:
    from apps.automation.models import ScraperTaskStatus

    if task.status in {ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING}:
        message = "担保任务执行中..."
        if isinstance(task.result, dict):
            message = str(task.result.get("message") or message)
        return {"success": True, "message": message, "session_id": task.id, "status": "in_progress"}

    if task.status == ScraperTaskStatus.SUCCESS:
        message = "担保流程执行完成（已到预览页，未提交）"
        if isinstance(task.result, dict):
            message = str(task.result.get("message") or message)
        return {"success": True, "message": message, "session_id": task.id, "status": "completed"}

    message = str(task.error_message or "").strip()
    if not message and isinstance(task.result, dict):
        message = str(task.result.get("message") or "").strip()
    if not message:
        message = "担保失败"
    return {"success": False, "message": message, "session_id": task.id, "status": "failed"}


def _update_session_task(
    *,
    session_id: int | None,
    status: str,
    error_message: str | None = None,
    result: dict[str, Any] | None = None,
    set_started: bool = False,
    set_finished: bool = False,
) -> None:
    if session_id is None:
        return

    now = timezone.now()
    updates: dict[str, Any] = {"status": status, "updated_at": now}
    if error_message is not None:
        updates["error_message"] = error_message
    if result is not None:
        updates["result"] = result
    if set_started:
        updates["started_at"] = now
    if set_finished:
        updates["finished_at"] = now

    def _do_update() -> None:
        from django.db import close_old_connections

        from apps.automation.models import ScraperTask

        close_old_connections()
        try:
            ScraperTask.objects.filter(id=session_id).update(**updates)
        except Exception:
            logger.exception(
                "court_guarantee_session_update_failed", extra={"session_id": session_id, "status": status}
            )
        finally:
            close_old_connections()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _do_update()
        return

    _SESSION_UPDATE_EXECUTOR.submit(_do_update)


def _run_guarantee(
    *,
    account: str,
    password: str,
    case_data: dict[str, Any],
    session_id: int | None,
) -> None:
    from playwright.sync_api import sync_playwright

    from apps.automation.models import ScraperTaskStatus
    from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
    from apps.automation.services.scraper.sites.court_zxfw_guarantee import CourtZxfwGuaranteeService

    _update_session_task(
        session_id=session_id,
        status=ScraperTaskStatus.RUNNING,
        error_message="",
        result={"stage": "login", "message": "正在登录一张网..."},
        set_started=True,
    )

    with sync_playwright() as pw:
        _headless = not bool(os.environ.get("DISPLAY"))
        browser = pw.chromium.launch(headless=_headless, slow_mo=_BROWSER_SLOW_MO_MS)
        context = browser.new_context()
        page = context.new_page()
        run_success = False

        try:
            login_service = CourtZxfwService(page=page, context=context)
            login_service._try_http_login = lambda *args, **kwargs: None  # type: ignore[method-assign]
            login_result = login_service.login(account=account, password=password)
            if not login_result.get("success"):
                message = str(login_result.get("message") or "一张网登录失败")
                _update_session_task(
                    session_id=session_id,
                    status=ScraperTaskStatus.FAILED,
                    error_message=message,
                    result={"stage": "login.failed", "message": message, "success": False},
                    set_finished=True,
                )
                return

            token_result = login_service.fetch_baoquan_token(save_debug=False)
            logger.info(
                "court_guarantee_token_status",
                extra={"session_id": session_id, "token_success": bool(token_result.get("success"))},
            )

            _update_session_task(
                session_id=session_id,
                status=ScraperTaskStatus.RUNNING,
                error_message="",
                result={"stage": "guarantee.running", "message": "正在执行担保流程..."},
            )

            guarantee_service = CourtZxfwGuaranteeService(page=page, save_debug=True)
            result = guarantee_service.apply_guarantee(case_data)

            if result.get("success"):
                run_success = True
                _update_session_task(
                    session_id=session_id,
                    status=ScraperTaskStatus.SUCCESS,
                    error_message="",
                    result={"stage": "guarantee.success", **result},
                    set_finished=True,
                )
                return

            message = str(result.get("message") or "担保执行失败")
            _update_session_task(
                session_id=session_id,
                status=ScraperTaskStatus.FAILED,
                error_message=message,
                result={"stage": "guarantee.failed", **result, "success": False},
                set_finished=True,
            )

        except Exception as exc:
            message = f"一张网担保执行失败: {exc}"
            logger.error(message, exc_info=True)
            _update_session_task(
                session_id=session_id,
                status=ScraperTaskStatus.FAILED,
                error_message=message,
                result={"stage": "guarantee.exception", "message": message, "success": False},
                set_finished=True,
            )
        finally:
            hold_seconds = _BROWSER_HOLD_SECONDS if run_success else _BROWSER_HOLD_SECONDS_ON_FAILURE
            try:
                logger.info(
                    "court_guarantee_browser_hold",
                    extra={"session_id": session_id, "run_success": run_success, "hold_seconds": hold_seconds},
                )
                page.wait_for_timeout(hold_seconds * 1000)
            except Exception:
                logger.debug("court_guarantee_wait_before_close_failed", exc_info=True)
            context.close()
            browser.close()
