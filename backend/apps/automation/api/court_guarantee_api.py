"""法院一张网申请担保 API。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.core.tasking import submit_task

from .court_guarantee_helpers import (
    _build_case_quote_context,
    _build_cause_candidates,
    _build_guarantee_material_paths,
    _build_plaintiff_agent_payload,
    _build_primary_respondent_property_clue,
    _build_respondent_options,
    _build_reusable_quote_options,
    _build_selected_respondent_property_clues,
    _build_session_status_payload,
    _extract_quote_company_options,
    _find_reusable_binding,
    _get_case_court_name,
    _get_case_number,
    _get_organization_service,
    _list_opponent_party_payloads,
    _normalize_consultant_code,
    _normalize_insurance_company,
    _normalize_selected_party_ids,
    _parse_preserve_amount,
    _pick_party_payload,
    _resolve_court_name,
    _resolve_insurance_company_defaults,
    _run_guarantee,
)
from .court_guarantee_schemas import (
    _PLAINTIFF_SIDE_STATUSES,
    _QUOTE_RETRY_ALLOWED_STATUSES,
    CaseGuaranteeInfoOut,
    CaseQuoteOperationIn,
    CaseQuoteOperationOut,
    ExecuteCourtGuaranteeIn,
    ExecuteCourtGuaranteeOut,
)

logger = logging.getLogger("apps.automation")
router = Router()

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="court-guarantee")


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
            "message": "请先维护案件保全金额（preservation_amount）",
            "quote_context": _build_case_quote_context(case=case),
        }

    existing_binding = _find_reusable_binding(case_id=case.id, preserve_amount=preserve_amount)
    if existing_binding is not None:
        return {
            "success": True,
            "message": "已复用当前金额对应的询价记录",
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
            "message": "未找到一张网账号凭证，无法发起询价",
            "quote_context": _build_case_quote_context(case=case),
        }

    quote_service = PreservationQuoteService()
    quote = quote_service.create_quote(
        preserve_amount=preserve_amount,
        corp_id="2550",
        category_id="127000",
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
        "message": "询价任务已发起",
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
            "message": "请先维护案件保全金额（preservation_amount）",
            "quote_context": _build_case_quote_context(case=case),
        }

    quote = PreservationQuote.objects.filter(id=quote_id).first()
    if quote is None:
        return {
            "success": False,
            "message": "询价记录不存在",
            "quote_context": _build_case_quote_context(case=case),
        }

    if quote.preserve_amount != preserve_amount:
        return {
            "success": False,
            "message": "仅支持绑定同保全金额的询价记录",
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
        "message": "已绑定所选询价记录",
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
            "message": "未找到该案件对应的询价绑定记录",
            "quote_context": _build_case_quote_context(case=case),
        }

    quote = PreservationQuote.objects.filter(id=quote_id).first()
    if quote is None:
        return {
            "success": False,
            "message": "询价记录不存在",
            "quote_context": _build_case_quote_context(case=case),
        }

    if quote.status not in _QUOTE_RETRY_ALLOWED_STATUSES:
        return {
            "success": False,
            "message": "当前状态不支持重试，仅失败或部分成功可重试",
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

    submit_task(
        "apps.automation.tasks.execute_preservation_quote_task",
        quote.id,
        task_name=f"询价任务重试 #{quote.id}",
        timeout=600,
    )

    return {
        "success": True,
        "message": "已重新提交询价任务",
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
            "message": "未找到该案件对应的询价记录",
            "quote_context": _build_case_quote_context(case=case),
        }

    quote = PreservationQuote.objects.filter(id=quote_id).first()
    if quote is None:
        return {
            "success": False,
            "message": "询价记录不存在",
            "quote_context": _build_case_quote_context(case=case),
        }

    quote.delete()
    return {
        "success": True,
        "message": "询价记录已删除",
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
            "message": "绑定关系不存在",
            "quote_context": _build_case_quote_context(case=case),
        }

    binding.delete()
    return {
        "success": True,
        "message": "绑定关系已删除",
        "quote_context": _build_case_quote_context(case=case),
    }


@router.post("/execute", response=ExecuteCourtGuaranteeOut)
def execute_court_guarantee(request: HttpRequest, payload: ExecuteCourtGuaranteeIn) -> Any:
    from apps.automation.models import ScraperTask, ScraperTaskStatus, ScraperTaskType
    from apps.cases.models import Case, CaseParty

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
            "message": "请至少选择一个被申请人",
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
    property_clues = _build_selected_respondent_property_clues(
        case_parties=case_parties,
        selected_respondents=selected_respondents,
        preserve_amount=preserve_amount,
    )
    property_clue = (
        property_clues[0]
        if property_clues
        else _build_primary_respondent_property_clue(
            case_parties=case_parties,
            selected_respondents=selected_respondents,
            preserve_amount=preserve_amount,
        )
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
        "property_clues": property_clues,
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
