"""法院一张网在线立案 API"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.http import HttpRequest
from ninja import Router

from .court_filing_helpers import (
    _apply_execution_party_fallbacks,
    _build_agent_payloads,
    _build_execution_reason_text,
    _build_execution_request_text,
    _build_materials_map,
    _build_party_payloads,
    _build_session_status_payload,
    _get_organization_service,
    _infer_filing_type,
    _normalize_filing_engine,
    _normalize_filing_type,
    _resolve_court_name,
    _resolve_original_case_number,
    _run_filing,
)
from .court_filing_schemas import (
    _DEFENDANT_SIDE_STATUSES,
    _FILING_ENGINE_API,
    _FILING_ENGINE_PLAYWRIGHT,
    _FILING_TYPE_EXECUTION,
    _PLAINTIFF_SIDE_STATUSES,
    _VALID_FILING_ENGINES,
    CaseFilingInfoOut,
    ExecuteCourtFilingIn,
    ExecuteCourtFilingOut,
)

logger = logging.getLogger("apps.automation")
router = Router()

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="court-filing")


@router.get("/case-info/{case_id}", response=CaseFilingInfoOut)
def get_case_filing_info(request: HttpRequest, case_id: int) -> Any:
    """获取案件立案所需信息"""
    from apps.cases.models import Case, CaseParty, SupervisingAuthority

    case = Case.objects.get(pk=case_id)

    sa = SupervisingAuthority.objects.filter(case=case, authority_type="trial").first()
    court_name: str | None = _resolve_court_name(sa.name) if sa else None  # type: ignore[arg-type]

    parties = list(CaseParty.objects.filter(case=case).select_related("client"))

    plaintiff_name: str | None = None
    defendant_name: str | None = None
    our_party_is_plaintiff_side = False

    for p in parties:
        legal_status = str(p.legal_status or "").strip()
        if legal_status in _PLAINTIFF_SIDE_STATUSES and not plaintiff_name:
            plaintiff_name = p.client.name
        elif legal_status in _DEFENDANT_SIDE_STATUSES and not defendant_name:
            defendant_name = p.client.name

        if getattr(getattr(p, "client", None), "is_our_client", False) and legal_status in _PLAINTIFF_SIDE_STATUSES:
            our_party_is_plaintiff_side = True

    lawyer_id = getattr(request.user, "id", None)
    has_court_credential = bool(
        lawyer_id and _get_organization_service().has_credential_for_lawyer(int(lawyer_id), "一张网")
    )

    suggested_filing_type = _infer_filing_type(case=case, parties=parties)

    # 检测 HTTP 链路插件是否存在
    has_http_plugin = False
    default_filing_engine = _FILING_ENGINE_PLAYWRIGHT
    try:
        from plugins import has_court_filing_api_plugin

        has_http_plugin = has_court_filing_api_plugin()
        default_filing_engine = _FILING_ENGINE_API if has_http_plugin else _FILING_ENGINE_PLAYWRIGHT
    except ImportError:
        pass

    return {
        "case_id": case.id,
        "case_name": case.name,
        "cause_of_action": case.cause_of_action or "",
        "court_name": court_name,
        "target_amount": str(case.target_amount) if case.target_amount else None,
        "plaintiff_name": plaintiff_name,
        "defendant_name": defendant_name,
        "our_party_is_plaintiff_side": our_party_is_plaintiff_side,
        "has_court_credential": has_court_credential,
        "has_http_plugin": has_http_plugin,
        "suggested_filing_type": suggested_filing_type,
        "default_filing_engine": default_filing_engine,
    }


@router.post("/execute", response=ExecuteCourtFilingOut)
def execute_court_filing(request: HttpRequest, payload: ExecuteCourtFilingIn) -> Any:
    """执行一张网在线立案（后台线程）"""
    from apps.automation.models import ScraperTask, ScraperTaskStatus, ScraperTaskType
    from apps.cases.models import Case, CaseParty, SupervisingAuthority
    from apps.core.models import Court as CourtModel

    case = Case.objects.get(pk=payload.case_id)
    parties = list(CaseParty.objects.filter(case=case).select_related("client"))

    filing_type = _normalize_filing_type(
        requested_filing_type=payload.filing_type,
        case=case,
        parties=parties,
    )
    filing_engine = _normalize_filing_engine(payload.filing_engine)
    if filing_engine not in _VALID_FILING_ENGINES:
        return {
            "success": False,
            "message": "立案方式仅支持 api 或 playwright",
            "session_id": None,
            "status": "failed",
        }

    organization_service = _get_organization_service()
    lawyer_id = getattr(request.user, "id", None)

    # 获取一张网凭证
    credential = (
        organization_service.get_credential_for_lawyer(int(lawyer_id), "一张网") if lawyer_id is not None else None
    )
    if not credential:
        return {"success": False, "message": "未找到一张网账号凭证", "session_id": None, "status": "failed"}

    # 获取法院名称
    sa = SupervisingAuthority.objects.filter(case=case, authority_type="trial").first()
    if not sa:
        return {"success": False, "message": "未设置管辖法院", "session_id": None, "status": "failed"}

    court_name = _resolve_court_name(sa.name)  # type: ignore[arg-type]
    if not court_name:
        return {"success": False, "message": "无法解析管辖法院名称", "session_id": None, "status": "failed"}

    case_data: dict[str, Any] = {
        "court_name": court_name,
        "cause_of_action": case.cause_of_action or "",
        "target_amount": str(case.target_amount) if case.target_amount else "",
        "case_id": case.id,
        "filing_engine": filing_engine,
    }

    court_obj = CourtModel.objects.filter(name=court_name).first()
    if court_obj and court_obj.province:
        case_data["province"] = court_obj.province

    plaintiffs, defendants, third_parties = _build_party_payloads(parties)
    if not plaintiffs:
        role_text = "申请执行人" if filing_type == _FILING_TYPE_EXECUTION else "原告"
        return {
            "success": False,
            "message": f"未识别到{role_text}当事人，请先在案件当事人中完善诉讼地位",
            "session_id": None,
            "status": "failed",
        }
    if not defendants:
        role_text = "被执行人" if filing_type == _FILING_TYPE_EXECUTION else "被告"
        return {
            "success": False,
            "message": f"未识别到{role_text}当事人，请先在案件当事人中完善诉讼地位",
            "session_id": None,
            "status": "failed",
        }

    case_data["plaintiffs"] = plaintiffs
    case_data["defendants"] = defendants
    if third_parties and filing_type != _FILING_TYPE_EXECUTION:
        case_data["third_parties"] = third_parties

    agents = _build_agent_payloads(case=case, requester_id=lawyer_id, parties=parties)
    if not agents:
        return {
            "success": False,
            "message": "未找到可用代理律师，请先在案件中绑定承办律师并完善手机号",
            "session_id": None,
            "status": "failed",
        }
    if filing_type == _FILING_TYPE_EXECUTION:
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
    case_data["agents"] = agents
    case_data["agent"] = agents[0]

    materials_map = _build_materials_map(case=case, filing_type=filing_type)
    if not materials_map:
        return {
            "success": False,
            "message": '未找到可上传的 PDF 材料，请先在"当事人材料"中绑定有效 PDF',
            "session_id": None,
            "status": "failed",
        }
    case_data["materials"] = materials_map

    if filing_type == _FILING_TYPE_EXECUTION:
        original_case_number = _resolve_original_case_number(case)
        if not original_case_number:
            return {
                "success": False,
                "message": '申请执行需要执行依据案号，请先在案件"案号"中维护（优先生效案号）',
                "session_id": None,
                "status": "failed",
            }
        case_data["original_case_number"] = original_case_number
        case_data["execution_basis_type"] = "民商"
        case_data["execution_reason"] = _build_execution_reason_text(
            case=case,
            original_case_number=original_case_number,
        )
        case_data["execution_request"] = _build_execution_request_text(case=case)

    session = ScraperTask.objects.create(
        task_type=ScraperTaskType.COURT_FILING,
        status=ScraperTaskStatus.PENDING,
        url="https://zxfw.court.gov.cn/zxfw",
        case=case,
        config={
            "filing_type": filing_type,
            "case_id": case.id,
            "court_name": court_name,
            "credential_account": str(getattr(credential, "account", "") or ""),
        },
        result={"stage": "queued"},
        started_at=None,
        finished_at=None,
    )

    _EXECUTOR.submit(
        _run_filing,
        account=str(credential.account),
        password=str(credential.password),
        case_data=case_data,
        filing_type=filing_type,
        session_id=session.id,
    )

    filing_label = "申请执行" if filing_type == _FILING_TYPE_EXECUTION else "民事一审"
    return {
        "success": True,
        "message": f"{filing_label}立案任务已启动，浏览器即将打开...",
        "session_id": session.id,
        "status": "in_progress",
    }


@router.get("/session/{session_id}", response=ExecuteCourtFilingOut)
def get_court_filing_session_status(request: HttpRequest, session_id: int) -> Any:
    """查询一张网立案会话状态"""
    from apps.automation.models import ScraperTask, ScraperTaskType

    task = ScraperTask.objects.filter(id=session_id, task_type=ScraperTaskType.COURT_FILING).first()
    if not task:
        return {"success": False, "message": "会话不存在", "session_id": session_id, "status": "failed"}

    return _build_session_status_payload(task=task)
