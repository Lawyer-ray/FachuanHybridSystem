"""法院一张网申请担保 API。"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_q.tasks import async_task
from ninja import Router, Schema

logger = logging.getLogger("apps.automation")
router = Router()

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="court-guarantee")
_SESSION_UPDATE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="court-guarantee-session")


def _read_int_env(name: str, default_value: int) -> int:
    raw_value = str(os.getenv(name, str(default_value))).strip()
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default_value
    return parsed if parsed >= 0 else default_value


_PLAINTIFF_SIDE_STATUSES = {"plaintiff", "applicant", "appellant", "orig_plaintiff"}
_RESPONDENT_SIDE_STATUSES = {"defendant", "respondent", "appellee", "orig_defendant"}
_DEFAULT_INSURANCE_COMPANY = "中国平安财产保险股份有限公司"
_SUNSHINE_INSURANCE_COMPANY = "阳光财产保险股份有限公司"
_SUNSHINE_DEFAULT_CONSULTANT_CODE = "08740007"
_PROPERTY_CLUE_TYPE_DISPLAY = {
    "house": "房产",
    "vehicle": "车辆",
    "bank_account": "银行账户",
    "equity": "股权",
    "income": "收入",
    "other": "其他",
}
_GUARANTEE_INSURANCE_COMPANY_OPTIONS = [
    "中国平安财产保险股份有限公司",
    "中国人民财产保险股份有限公司",
    "中国太平洋财产保险股份有限公司",
    "中国人寿财产保险股份有限公司",
    "中华联合财产保险股份有限公司",
    "阳光财产保险股份有限公司",
    "大地财产保险股份有限公司",
    "太平财产保险有限公司",
    "永安财产保险股份有限公司",
    "安盛天平财产保险有限公司",
]
_DEFAULT_PRESERVATION_CORP_ID = "2550"
_DEFAULT_PRESERVATION_CATEGORY_ID = "127000"
_QUOTE_RETRY_ALLOWED_STATUSES = {"failed", "partial_success"}
_BROWSER_SLOW_MO_MS = 300
_BROWSER_HOLD_SECONDS = _read_int_env("COURT_GUARANTEE_BROWSER_HOLD_SECONDS", 8)
_BROWSER_HOLD_SECONDS_ON_FAILURE = _read_int_env("COURT_GUARANTEE_BROWSER_HOLD_SECONDS_ON_FAILURE", 30)
_DEFAULT_NATURAL_ID_NUMBER = "110101" + "19900307" + "7719"
_DEFAULT_LEGAL_ID_NUMBER = "91440101MA59TEST8X"


class CaseGuaranteeInfoOut(Schema):
    case_id: int
    case_name: str
    court_name: str | None
    cause_of_action: str
    preserve_amount: str | None
    preserve_category: str
    has_case_number: bool
    has_court_credential: bool = False
    our_party_is_plaintiff_side: bool = False
    insurance_company_name: str = _DEFAULT_INSURANCE_COMPANY
    insurance_company_options: list[str] = _GUARANTEE_INSURANCE_COMPANY_OPTIONS
    consultant_code: str = ""
    quote_context: dict[str, Any] | None = None
    reusable_quotes: list[dict[str, Any]] = []
    respondent_options: list[dict[str, Any]] = []


class CaseQuoteOperationIn(Schema):
    case_id: int


class CaseQuoteOperationOut(Schema):
    success: bool
    message: str
    quote_context: dict[str, Any] | None = None


class ExecuteCourtGuaranteeIn(Schema):
    case_id: int
    insurance_company_name: str | None = None
    consultant_code: str | None = None
    selected_respondent_ids: list[int] | None = None


class ExecuteCourtGuaranteeOut(Schema):
    success: bool
    message: str
    session_id: int | None = None
    status: str | None = None


@router.get("/case-info/{case_id}", response=CaseGuaranteeInfoOut)
def get_case_guarantee_info(request: HttpRequest, case_id: int) -> Any:
    from apps.cases.models import Case, CaseNumber, CaseParty, SupervisingAuthority

    case = Case.objects.get(pk=case_id)

    sa = SupervisingAuthority.objects.filter(case=case, authority_type="trial").first()
    court_name: str | None = _resolve_court_name(sa.name) if sa else None

    has_case_number = CaseNumber.objects.filter(case=case).exclude(number__isnull=True).exclude(number="").exists()
    preserve_category = "诉讼保全" if has_case_number else "诉前保全"

    parties = list(CaseParty.objects.filter(case=case).select_related("client"))
    our_party_is_plaintiff_side = any(
        getattr(getattr(p, "client", None), "is_our_client", False)
        and str(getattr(p, "legal_status", "") or "").strip() in _PLAINTIFF_SIDE_STATUSES
        for p in parties
    )

    lawyer_id = getattr(request.user, "id", None)
    organization_service = _get_organization_service()
    has_court_credential = bool(lawyer_id and organization_service.has_credential_for_lawyer(int(lawyer_id), "一张网"))

    quote_context = _build_case_quote_context(case=case)
    insurance_company_name, insurance_company_options = _resolve_insurance_company_defaults(quote_context=quote_context)
    reusable_quotes = _build_reusable_quote_options(case=case)
    respondent_options = _build_respondent_options(case_parties=parties)

    return {
        "case_id": case.id,
        "case_name": case.name,
        "court_name": court_name,
        "cause_of_action": case.cause_of_action or "",
        "preserve_amount": str(case.preservation_amount) if case.preservation_amount else None,
        "preserve_category": preserve_category,
        "has_case_number": has_case_number,
        "has_court_credential": has_court_credential,
        "our_party_is_plaintiff_side": our_party_is_plaintiff_side,
        "insurance_company_name": insurance_company_name,
        "insurance_company_options": insurance_company_options,
        "consultant_code": "",
        "quote_context": quote_context,
        "reusable_quotes": reusable_quotes,
        "respondent_options": respondent_options,
    }


@router.post("/quote/ensure", response=CaseQuoteOperationOut)
def ensure_case_quote(request: HttpRequest, payload: CaseQuoteOperationIn) -> Any:
    from apps.automation.models import CasePreservationQuoteBinding
    from apps.automation.services.insurance.preservation_quote_service import PreservationQuoteService
    from apps.cases.models import Case

    case = Case.objects.get(pk=payload.case_id)
    preserve_amount = _parse_preserve_amount(case.preservation_amount)
    if preserve_amount is None or preserve_amount <= 0:
        return {
            "success": False,
            "message": str(_("请先维护案件保全金额（preservation_amount）")),
            "quote_context": _build_case_quote_context(case=case),
        }

    existing_binding = _find_reusable_binding(case_id=case.id, preserve_amount=preserve_amount)
    if existing_binding is not None:
        return {
            "success": True,
            "message": str(_("已复用当前金额对应的询价记录")),
            "quote_context": _build_case_quote_context(case=case),
        }

    lawyer_id = getattr(request.user, "id", None)
    organization_service = _get_organization_service()
    credential = (
        organization_service.get_credential_for_lawyer(int(lawyer_id), "一张网") if lawyer_id is not None else None
    )
    if credential is None:
        return {
            "success": False,
            "message": str(_("未找到一张网账号凭证，无法发起询价")),
            "quote_context": _build_case_quote_context(case=case),
        }

    quote_service = PreservationQuoteService()
    quote = quote_service.create_quote(
        preserve_amount=preserve_amount,
        corp_id=_DEFAULT_PRESERVATION_CORP_ID,
        category_id=_DEFAULT_PRESERVATION_CATEGORY_ID,
        credential_id=int(credential.id),
    )

    created_by_id = int(lawyer_id) if lawyer_id is not None else None
    CasePreservationQuoteBinding.objects.create(
        case=case,
        preservation_quote=quote,
        preserve_amount_snapshot=preserve_amount,
        created_by_id=created_by_id,
    )

    return {
        "success": True,
        "message": str(_("询价任务已发起")),
        "quote_context": _build_case_quote_context(case=case),
    }


@router.post("/quote/{quote_id}/bind", response=CaseQuoteOperationOut)
def bind_case_quote(request: HttpRequest, quote_id: int, payload: CaseQuoteOperationIn) -> Any:
    from apps.automation.models import CasePreservationQuoteBinding, PreservationQuote
    from apps.cases.models import Case

    case = Case.objects.get(pk=payload.case_id)
    preserve_amount = _parse_preserve_amount(case.preservation_amount)
    if preserve_amount is None or preserve_amount <= 0:
        return {
            "success": False,
            "message": str(_("请先维护案件保全金额（preservation_amount）")),
            "quote_context": _build_case_quote_context(case=case),
        }

    quote = PreservationQuote.objects.filter(id=quote_id).first()
    if quote is None:
        return {
            "success": False,
            "message": str(_("询价记录不存在")),
            "quote_context": _build_case_quote_context(case=case),
        }

    if quote.preserve_amount != preserve_amount:
        return {
            "success": False,
            "message": str(_("仅支持绑定同保全金额的询价记录")),
            "quote_context": _build_case_quote_context(case=case),
        }

    binding = CasePreservationQuoteBinding.objects.filter(case_id=case.id, preservation_quote_id=quote.id).first()
    if binding is None:
        created_by_id = int(getattr(request.user, "id", 0) or 0) or None
        CasePreservationQuoteBinding.objects.create(
            case=case,
            preservation_quote=quote,
            preserve_amount_snapshot=preserve_amount,
            created_by_id=created_by_id,
        )

    return {
        "success": True,
        "message": str(_("已绑定所选询价记录")),
        "quote_context": _build_case_quote_context(case=case),
    }


@router.post("/quote/{quote_id}/retry", response=CaseQuoteOperationOut)
def retry_case_quote(request: HttpRequest, quote_id: int, payload: CaseQuoteOperationIn) -> Any:
    from apps.automation.models import CasePreservationQuoteBinding, PreservationQuote, QuoteStatus
    from apps.cases.models import Case

    case = Case.objects.get(pk=payload.case_id)
    binding = (
        CasePreservationQuoteBinding.objects.select_related("preservation_quote")
        .filter(case_id=case.id, preservation_quote_id=quote_id)
        .first()
    )
    if binding is None:
        return {
            "success": False,
            "message": str(_("未找到该案件对应的询价绑定记录")),
            "quote_context": _build_case_quote_context(case=case),
        }

    quote = PreservationQuote.objects.filter(id=quote_id).first()
    if quote is None:
        return {
            "success": False,
            "message": str(_("询价记录不存在")),
            "quote_context": _build_case_quote_context(case=case),
        }

    if quote.status not in _QUOTE_RETRY_ALLOWED_STATUSES:
        return {
            "success": False,
            "message": str(_("当前状态不支持重试，仅失败或部分成功可重试")),
            "quote_context": _build_case_quote_context(case=case),
        }

    quote.status = QuoteStatus.PENDING
    quote.error_message = ""
    quote.started_at = None
    quote.finished_at = None
    quote.total_companies = 0
    quote.success_count = 0
    quote.failed_count = 0
    quote.save(
        update_fields=[
            "status",
            "error_message",
            "started_at",
            "finished_at",
            "total_companies",
            "success_count",
            "failed_count",
        ]
    )

    async_task(
        "apps.automation.tasks.execute_preservation_quote_task",
        quote.id,
        task_name=f"询价任务重试 #{quote.id}",
        timeout=600,
    )

    return {
        "success": True,
        "message": str(_("已重新提交询价任务")),
        "quote_context": _build_case_quote_context(case=case),
    }


@router.post("/quote/{quote_id}/delete", response=CaseQuoteOperationOut)
def delete_case_quote(request: HttpRequest, quote_id: int, payload: CaseQuoteOperationIn) -> Any:
    from apps.automation.models import CasePreservationQuoteBinding, PreservationQuote
    from apps.cases.models import Case

    case = Case.objects.get(pk=payload.case_id)
    has_binding = CasePreservationQuoteBinding.objects.filter(case_id=case.id, preservation_quote_id=quote_id).exists()
    if not has_binding:
        return {
            "success": False,
            "message": str(_("未找到该案件对应的询价记录")),
            "quote_context": _build_case_quote_context(case=case),
        }

    quote = PreservationQuote.objects.filter(id=quote_id).first()
    if quote is None:
        return {
            "success": False,
            "message": str(_("询价记录不存在")),
            "quote_context": _build_case_quote_context(case=case),
        }

    quote.delete()
    return {
        "success": True,
        "message": str(_("询价记录已删除")),
        "quote_context": _build_case_quote_context(case=case),
    }


@router.post("/quote-binding/{binding_id}/delete", response=CaseQuoteOperationOut)
def delete_case_quote_binding(request: HttpRequest, binding_id: int, payload: CaseQuoteOperationIn) -> Any:
    from apps.automation.models import CasePreservationQuoteBinding
    from apps.cases.models import Case

    case = Case.objects.get(pk=payload.case_id)
    binding = CasePreservationQuoteBinding.objects.filter(id=binding_id, case_id=case.id).first()
    if binding is None:
        return {
            "success": False,
            "message": str(_("绑定关系不存在")),
            "quote_context": _build_case_quote_context(case=case),
        }

    binding.delete()
    return {
        "success": True,
        "message": str(_("绑定关系已删除")),
        "quote_context": _build_case_quote_context(case=case),
    }


@router.post("/execute", response=ExecuteCourtGuaranteeOut)
def execute_court_guarantee(request: HttpRequest, payload: ExecuteCourtGuaranteeIn) -> Any:
    from apps.automation.models import ScraperTask, ScraperTaskStatus, ScraperTaskType
    from apps.cases.models import Case, CaseNumber, CaseParty, SupervisingAuthority

    case = Case.objects.get(pk=payload.case_id)

    organization_service = _get_organization_service()
    lawyer_id = getattr(request.user, "id", None)
    credential = (
        organization_service.get_credential_for_lawyer(int(lawyer_id), "一张网") if lawyer_id is not None else None
    )
    if not credential:
        return {"success": False, "message": "未找到一张网账号凭证", "session_id": None, "status": "failed"}

    court_name = _get_case_court_name(case)
    if not court_name:
        return {"success": False, "message": "未设置管辖法院", "session_id": None, "status": "failed"}

    preserve_amount = case.preservation_amount
    if preserve_amount is None or preserve_amount <= 0:
        return {
            "success": False,
            "message": "案件保全金额为空，请先维护 preservation_amount",
            "session_id": None,
            "status": "failed",
        }

    case_number = _get_case_number(case)
    has_case_number = bool(case_number)
    preserve_category = "诉讼保全" if has_case_number else "诉前保全"

    from apps.automation.services.scraper.sites.court_zxfw_guarantee import CourtZxfwGuaranteeService

    case_year, case_court_code, case_type_code, case_seq = CourtZxfwGuaranteeService.parse_case_number(
        str(case_number or "")
    )
    material_paths = _build_guarantee_material_paths(case)
    case_parties = list(CaseParty.objects.filter(case=case).select_related("client").order_by("id"))

    applicant = _pick_party_payload(
        case_parties=case_parties, preferred_statuses=_PLAINTIFF_SIDE_STATUSES, prefer_our=True
    )
    respondent_candidates = _list_opponent_party_payloads(case_parties=case_parties)
    selected_respondent_ids = _normalize_selected_party_ids(payload.selected_respondent_ids)
    if selected_respondent_ids is None:
        selected_respondents = respondent_candidates
    else:
        selected_respondents = [
            item for item in respondent_candidates if int(item.get("party_id") or 0) in selected_respondent_ids
        ]
    if not selected_respondents:
        return {
            "success": False,
            "message": str(_("请至少选择一个被申请人")),
            "session_id": None,
            "status": "failed",
        }
    respondent = selected_respondents[0]

    plaintiff_agent = _build_plaintiff_agent_payload(case=case, requester_id=lawyer_id, fallback_party=applicant)

    quote_context = _build_case_quote_context(case=case)
    quote_based_options = _extract_quote_company_options(quote_context=quote_context)
    insurance_company_name = _normalize_insurance_company(
        str(payload.insurance_company_name or "").strip(),
        allowed_options=quote_based_options,
    )
    consultant_code = _normalize_consultant_code(
        insurance_company_name=insurance_company_name,
        consultant_code=payload.consultant_code,
    )
    property_clue = _build_primary_respondent_property_clue(
        case_parties=case_parties,
        selected_respondents=selected_respondents,
        preserve_amount=preserve_amount,
    )

    case_data: dict[str, Any] = {
        "case_id": case.id,
        "case_name": case.name,
        "court_name": court_name,
        "cause_of_action": case.cause_of_action or "",
        "cause_candidates": _build_cause_candidates(case.cause_of_action or ""),
        "preserve_amount": str(preserve_amount),
        "preserve_category": preserve_category,
        "case_number": str(case_number or ""),
        "case_year": case_year,
        "case_court_code": case_court_code,
        "case_type_code": case_type_code,
        "case_seq": case_seq,
        "material_paths": material_paths,
        "insurance_company_name": insurance_company_name,
        "consultant_code": consultant_code,
        "applicant": applicant,
        "respondent": respondent,
        "respondents": selected_respondents,
        "selected_respondent_ids": [int(item.get("party_id") or 0) for item in selected_respondents],
        "plaintiff_agent": plaintiff_agent,
        "property_clue": property_clue,
    }

    session = ScraperTask.objects.create(
        task_type=ScraperTaskType.COURT_FILING,
        status=ScraperTaskStatus.PENDING,
        url="https://zxfw.court.gov.cn/yzwbqww/index.html#/CreateGuarantee/applyGuaranteeInformation/gOne",
        case=case,
        config={
            "scene": "court_guarantee",
            "case_id": case.id,
            "court_name": court_name,
            "credential_account": str(getattr(credential, "account", "") or ""),
            "insurance_company_name": case_data["insurance_company_name"],
            "consultant_code": case_data["consultant_code"],
        },
        result={"stage": "queued", "message": "担保任务已排队"},
        started_at=None,
        finished_at=None,
    )

    _EXECUTOR.submit(
        _run_guarantee,
        account=str(credential.account),
        password=str(credential.password),
        case_data=case_data,
        session_id=session.id,
    )

    return {
        "success": True,
        "message": "担保任务已启动（有头模式），浏览器即将打开...",
        "session_id": session.id,
        "status": "in_progress",
    }


@router.get("/session/{session_id}", response=ExecuteCourtGuaranteeOut)
def get_court_guarantee_session_status(request: HttpRequest, session_id: int) -> Any:
    from apps.automation.models import ScraperTask

    task = ScraperTask.objects.filter(id=session_id).first()
    if not task:
        return {"success": False, "message": "会话不存在", "session_id": session_id, "status": "failed"}

    return _build_session_status_payload(task=task)


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


def _build_primary_respondent_property_clue(
    *,
    case_parties: list[Any],
    selected_respondents: list[dict[str, Any]],
    preserve_amount: Any | None = None,
) -> dict[str, str]:
    party_id_set = {
        int(item.get("party_id") or 0) for item in selected_respondents if int(item.get("party_id") or 0) > 0
    }

    selected_case_parties = [party for party in case_parties if int(getattr(party, "id", 0) or 0) in party_id_set]
    if not selected_case_parties:
        selected_case_parties = _list_opponent_case_parties(case_parties=case_parties)

    primary_party = selected_case_parties[0] if selected_case_parties else None
    primary_client = getattr(primary_party, "client", None)
    owner_name = (
        str(getattr(primary_client, "name", "") or "").strip()
        or str((selected_respondents[0].get("name") if selected_respondents else "") or "被申请人").strip()
    )

    property_info = ""
    if primary_client is not None:
        client_service = _get_client_service()
        clue_dtos = client_service.get_property_clues_by_client_internal(int(getattr(primary_client, "id", 0) or 0))
        clue_lines: list[str] = []
        for clue in clue_dtos:
            clue_type = str(getattr(clue, "clue_type", "") or "").strip()
            type_display = _PROPERTY_CLUE_TYPE_DISPLAY.get(clue_type, clue_type or "财产线索")
            normalized_content = _normalize_property_clue_content(str(getattr(clue, "content", "") or ""))
            if normalized_content:
                clue_lines.append(f"{type_display}：{normalized_content}")
            else:
                clue_lines.append(type_display)
        property_info = "；".join(clue_lines)

    if not property_info:
        property_info = f"{owner_name}名下财产线索"

    property_location = str(getattr(primary_client, "address", "") or "").strip() if primary_client is not None else ""
    normalized_property_value = ""
    if preserve_amount is not None:
        normalized_property_value = str(preserve_amount).strip().replace(",", "")
        if "." in normalized_property_value:
            normalized_property_value = normalized_property_value.rstrip("0").rstrip(".")

    return {
        "owner_name": owner_name,
        "property_type": "其他",
        "property_info": property_info,
        "property_location": property_location,
        "property_province": "",
        "property_cert_no": "",
        "property_value": normalized_property_value,
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


def _build_guarantee_material_paths(case: Any) -> list[str]:
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
    ) -> str | None:
        for _, type_name, filename, path in records:
            if path in used:
                continue
            haystack = f"{type_name} {filename}"
            if any(keyword in haystack for keyword in keywords):
                return path
        return None

    our_party_qs = CaseMaterial.objects.filter(case=case, category=CaseMaterialCategory.PARTY).filter(
        Q(side=CaseMaterialSide.OUR) | Q(side__isnull=True) | Q(side="")
    )
    non_party_qs = CaseMaterial.objects.filter(case=case, category=CaseMaterialCategory.NON_PARTY)

    our_files = _collect(our_party_qs)
    non_party_files = _collect(non_party_qs)

    selected: list[str] = []
    used: set[str] = set()

    required_rules: list[tuple[list[tuple[int, str, str, str]], list[str]]] = [
        (our_files, ["财产保全申请书", "保全申请书"]),
        (our_files, ["起诉状", "起诉书", "起诉"]),
        (non_party_files, ["立案受理通知书", "受理通知书", "立案通知书", "受理通知", "立案通知"]),
        (our_files, ["身份证明", "营业执照", "身份证", "法定代表人身份证明"]),
        (our_files, ["证据", "证据材料", "明细", "清单"]),
    ]

    for records, keywords in required_rules:
        picked = _pick(records=records, keywords=keywords, used=used)
        if not picked:
            continue
        used.add(picked)
        selected.append(picked)

    for records in (our_files, non_party_files):
        for _, _, _, path in records:
            if path in used:
                continue
            used.add(path)
            selected.append(path)
            if len(selected) >= 8:
                return selected

    return selected


def _build_cause_candidates(raw_cause: str) -> list[str]:
    text = str(raw_cause or "").replace("\u3000", " ").strip()
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
        browser = pw.chromium.launch(headless=False, slow_mo=_BROWSER_SLOW_MO_MS)
        context = browser.new_context()
        page = context.new_page()
        run_success = False

        try:
            login_service = CourtZxfwService(page=page, context=context)
            login_service._try_http_login = lambda *args, **kwargs: None
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
