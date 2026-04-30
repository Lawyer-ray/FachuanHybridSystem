"""法院一张网在线立案 API"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema

logger = logging.getLogger("apps.automation")
router = Router()


_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="court-filing")
_SESSION_UPDATE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="court-filing-session")

_FILING_TYPE_CIVIL = "civil"
_FILING_TYPE_EXECUTION = "execution"
_VALID_FILING_TYPES = {_FILING_TYPE_CIVIL, _FILING_TYPE_EXECUTION}
_FILING_ENGINE_API = "api"
_FILING_ENGINE_PLAYWRIGHT = "playwright"
_VALID_FILING_ENGINES = {_FILING_ENGINE_API, _FILING_ENGINE_PLAYWRIGHT}

_PLAINTIFF_SIDE_STATUSES = {"plaintiff", "applicant", "appellant", "orig_plaintiff"}
_DEFENDANT_SIDE_STATUSES = {"defendant", "respondent", "appellee", "orig_defendant", "criminal_defendant"}
_THIRD_SIDE_STATUSES = {"third", "third_party", "orig_third", "victim"}
_EXECUTION_HINT_STATUSES = {"applicant", "respondent"}

_TEXT_NORMALIZE_PATTERN = re.compile(r"[\s\-_./\\()（）【】\[\]<>《》:：,，;；'\"`]+")
_DEFAULT_SLOT_BY_FILING_TYPE = {_FILING_TYPE_CIVIL: "5", _FILING_TYPE_EXECUTION: "4"}

_SLOT_RULES: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    _FILING_TYPE_CIVIL: {
        "0": {
            "strong": ("民事起诉状", "起诉状", "诉状", "起诉书"),
            "weak": ("诉讼请求", "事实与理由"),
            "exclude": ("执行申请书", "证据目录", "送达地址确认书"),
        },
        "1": {
            "strong": (
                "当事人身份证明",
                "身份证明",
                "身份证",
                "营业执照",
                "统一社会信用代码",
                "法定代表人身份证明",
                "户口簿",
                "户籍证明",
            ),
            "weak": ("主体资格", "自然人身份证明"),
            "exclude": ("授权委托书", "证据目录", "委托代理", "委托手续"),
        },
        "2": {
            "strong": (
                "授权委托书",
                "授权委托",
                "委托代理",
                "委托手续",
                "委托材料",
                "律师执业证",
                "执业证",
                "律师证",
                "所函",
                "代理人身份证明",
            ),
            "weak": ("代理人", "受托人"),
            "exclude": (
                "送达地址确认书",
                "营业执照",
                "统一社会信用代码",
                "法定代表人身份证明",
            ),
        },
        "3": {
            "strong": ("证据目录", "证据清单", "证据明细", "证据材料"),
            "weak": ("证据", "证明材料", "聊天记录", "转账记录", "录音"),
            "exclude": ("身份证明", "授权委托书", "委托材料"),
        },
        "4": {
            "strong": ("送达地址确认书", "送达地址确认", "地址确认书"),
            "weak": ("送达地址",),
            "exclude": (),
        },
    },
    _FILING_TYPE_EXECUTION: {
        "0": {
            "strong": ("执行申请书", "申请执行书", "强制执行申请书", "恢复执行申请书"),
            "weak": ("申请执行", "执行申请"),
            "exclude": ("限制高消费", "纳入失信", "公开信息", "出境", "送达地址确认书"),
        },
        "1": {
            "strong": ("执行依据", "判决书", "裁定书", "调解书", "生效法律文书", "执行裁定"),
            "weak": ("生效证明", "裁判文书"),
            "exclude": ("执行申请书",),
        },
        "2": {
            "strong": (
                "授权委托书",
                "授权委托",
                "委托代理",
                "委托手续",
                "委托材料",
                "律师执业证",
                "执业证",
                "律师证",
                "所函",
                "代理人身份证明",
            ),
            "weak": ("代理人", "受托人"),
            "exclude": (
                "营业执照",
                "统一社会信用代码",
                "法定代表人身份证明",
            ),
        },
        "3": {
            "strong": (
                "申请人身份材料",
                "申请执行人身份材料",
                "申请人身份证明",
                "申请执行人身份证明",
                "身份证明",
                "身份证",
                "营业执照",
                "统一社会信用代码",
                "法定代表人身份证明",
                "户口簿",
            ),
            "weak": ("主体资格",),
            "exclude": ("授权委托书", "委托材料", "送达地址确认书", "委托代理", "委托手续"),
        },
        "4": {
            "strong": ("送达地址确认书", "送达地址确认", "地址确认书"),
            "weak": ("送达地址",),
            "exclude": (),
        },
    },
}


# ==================== Schemas ====================


class CaseFilingInfoOut(Schema):
    """案件立案信息"""

    case_id: int
    case_name: str
    cause_of_action: str
    court_name: str | None
    target_amount: str | None
    plaintiff_name: str | None
    defendant_name: str | None
    our_party_is_plaintiff_side: bool = False
    has_court_credential: bool = False
    has_http_plugin: bool = False
    suggested_filing_type: str = _FILING_TYPE_CIVIL
    default_filing_engine: str = _FILING_ENGINE_API


class ExecuteCourtFilingIn(Schema):
    """执行立案请求"""

    case_id: int
    filing_type: str | None = None  # civil / execution，留空则自动判断
    filing_engine: str | None = None  # api / playwright，留空默认 api


class ExecuteCourtFilingOut(Schema):
    """执行立案响应"""

    success: bool
    message: str
    session_id: int | None = None
    status: str | None = None


# ==================== API ====================


def _get_organization_service() -> Any:
    from apps.core.dependencies import build_organization_service

    return build_organization_service()


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
    if third_parties and filing_type == _FILING_TYPE_CIVIL:
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
            "message": "未找到可上传的 PDF 材料，请先在“当事人材料”中绑定有效 PDF",
            "session_id": None,
            "status": "failed",
        }
    case_data["materials"] = materials_map

    if filing_type == _FILING_TYPE_EXECUTION:
        original_case_number = _resolve_original_case_number(case)
        if not original_case_number:
            return {
                "success": False,
                "message": "申请执行需要执行依据案号，请先在案件“案号”中维护（优先生效案号）",
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


# ==================== 内部函数 ====================


def _resolve_court_name(authority_name: str) -> str | None:
    """将管辖机关名称解析为完整法院名称

    例如: "天河区" -> "广州市天河区人民法院"
    """
    if "人民法院" in authority_name:
        return authority_name

    from apps.core.models import Court

    court = Court.objects.filter(name__contains=authority_name).first()
    if court and court.name:
        return str(court.name)

    return f"{authority_name}人民法院"


def _normalize_filing_type(*, requested_filing_type: str | None, case: Any, parties: list[Any]) -> str:
    requested = str(requested_filing_type or "").strip().lower()
    if requested in _VALID_FILING_TYPES:
        return requested
    return _infer_filing_type(case=case, parties=parties)


def _normalize_filing_engine(requested_engine: str | None) -> str:
    requested = str(requested_engine or "").strip().lower()
    if requested in _VALID_FILING_ENGINES:
        return requested
    return _FILING_ENGINE_API


def _infer_filing_type(*, case: Any, parties: list[Any]) -> str:
    """自动推断立案类型：执行优先，默认民事。"""
    from apps.cases.models import CaseMaterial

    statuses = {str(getattr(p, "legal_status", "") or "").strip() for p in parties}
    if statuses & _EXECUTION_HINT_STATUSES:
        return _FILING_TYPE_EXECUTION

    text = " ".join([str(getattr(case, "name", "") or ""), str(getattr(case, "cause_of_action", "") or "")])
    if any(keyword in text for keyword in ("申请执行", "执行")):
        return _FILING_TYPE_EXECUTION

    type_names = CaseMaterial.objects.filter(case=case).values_list("type_name", flat=True)
    execution_keywords = ("执行申请书", "执行依据", "被执行", "申请执行")
    for type_name in type_names:
        current_type_name = str(type_name or "")
        if any(keyword in current_type_name for keyword in execution_keywords):
            return _FILING_TYPE_EXECUTION

    return _FILING_TYPE_CIVIL


def _resolve_original_case_number(case: Any) -> str:
    """解析执行依据案号：优先生效案号，其次第一条案号。"""
    case_numbers = getattr(case, "case_numbers", None)
    if case_numbers is None:
        return ""

    active_number = case_numbers.filter(is_active=True).order_by("id").values_list("number", flat=True).first()
    if active_number:
        return str(active_number).strip()

    fallback_number = case_numbers.order_by("id").values_list("number", flat=True).first()
    if fallback_number:
        return str(fallback_number).strip()
    return ""


def _build_party_payloads(
    parties: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from apps.core.utils.id_card_utils import IdCardUtils

    plaintiffs: list[dict[str, Any]] = []
    defendants: list[dict[str, Any]] = []
    third_parties: list[dict[str, Any]] = []

    for party in parties:
        client = party.client
        is_natural = client.client_type == "natural"
        client_type = "natural" if is_natural else "legal"

        party_data: dict[str, Any] = {
            "client_type": client_type,
            "type": client_type,
            "name": client.name,
            "address": client.address or "",
            "phone": client.phone or "",
        }

        if is_natural:
            id_number = client.id_number or ""
            party_data["id_number"] = id_number
            party_data["gender"] = IdCardUtils.extract_gender(id_number) or "男"
        else:
            party_data["uscc"] = client.id_number or ""
            party_data["legal_rep"] = client.legal_representative or ""
            party_data["legal_rep_id_number"] = client.legal_representative_id_number or ""

        legal_status = str(getattr(party, "legal_status", "") or "").strip()
        if legal_status in _PLAINTIFF_SIDE_STATUSES:
            plaintiffs.append(party_data)
        elif legal_status in _DEFENDANT_SIDE_STATUSES:
            defendants.append(party_data)
        elif legal_status in _THIRD_SIDE_STATUSES:
            third_parties.append(party_data)

    return plaintiffs, defendants, third_parties


def _to_valid_mobile(value: str) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    return digits if re.fullmatch(r"1\d{10}", digits) else ""


def _apply_execution_party_fallbacks(*, plaintiffs: list[dict[str, Any]], agents: list[dict[str, Any]]) -> None:
    fallback_phone = ""
    for agent in agents:
        mobile = _to_valid_mobile(str(agent.get("phone", "") or ""))
        if mobile:
            fallback_phone = mobile
            break

    for plaintiff in plaintiffs:
        if plaintiff.get("client_type") != "natural":
            continue

        address = str(plaintiff.get("address", "") or "").strip()
        if address:
            plaintiff["address"] = address

        phone = _to_valid_mobile(str(plaintiff.get("phone", "") or ""))
        if not phone and fallback_phone:
            plaintiff["phone"] = fallback_phone


def _build_agent_payloads(*, case: Any, requester_id: int | None, parties: list[Any]) -> list[dict[str, Any]]:
    from apps.organization.models import Lawyer

    assignments = list(case.assignments.select_related("lawyer__law_firm").order_by("id"))
    lawyers: list[Any] = []
    seen_ids: set[int] = set()

    for assignment in assignments:
        lawyer = getattr(assignment, "lawyer", None)
        lawyer_id = int(getattr(lawyer, "id", 0) or 0)
        if lawyer is None or lawyer_id <= 0 or lawyer_id in seen_ids:
            continue
        seen_ids.add(lawyer_id)
        lawyers.append(lawyer)

    requester = None
    if requester_id is not None and int(requester_id or 0) > 0 and int(requester_id) not in seen_ids:
        requester = Lawyer.objects.select_related("law_firm").filter(id=int(requester_id)).first()
    if requester is not None:
        seen_ids.add(int(requester.id))
        lawyers.append(requester)

    fallback_phones: list[str] = []
    for party in parties:
        phone = _to_valid_mobile(str(getattr(getattr(party, "client", None), "phone", "") or ""))
        if phone and phone not in fallback_phones:
            fallback_phones.append(phone)

    agents: list[dict[str, Any]] = []
    for index, lawyer in enumerate(lawyers):
        real_name = str(getattr(lawyer, "real_name", "") or "").strip()
        username = str(getattr(lawyer, "username", "") or "").strip()
        name = real_name or username
        if not name:
            continue

        law_firm = getattr(lawyer, "law_firm", None)
        law_firm_name = str(getattr(law_firm, "name", "") or "").strip()
        law_firm_address = str(getattr(law_firm, "address", "") or "").strip()
        mobile = _to_valid_mobile(str(getattr(lawyer, "phone", "") or ""))
        if not mobile and index < len(fallback_phones):
            mobile = fallback_phones[index]
        if not mobile and fallback_phones:
            mobile = fallback_phones[0]

        agents.append(
            {
                "name": name,
                "id_number": str(getattr(lawyer, "id_card", "") or "").strip(),
                "bar_number": str(getattr(lawyer, "license_no", "") or "").strip(),
                "law_firm": law_firm_name,
                "address": law_firm_address,
                "phone": mobile,
            }
        )

    return agents


def _build_execution_reason_text(*, case: Any, original_case_number: str) -> str:
    cause_text = str(getattr(case, "cause_of_action", "") or "").strip()
    case_number_text = original_case_number or "相关"
    reason = f"被执行人未履行{case_number_text}生效法律文书确定的义务。"
    if cause_text:
        reason = f"被执行人未履行{case_number_text}生效法律文书确定的{cause_text}相关义务。"
    return reason


def _build_execution_request_text(*, case: Any) -> str:
    from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

    generated_text = ""
    try:
        from apps.documents.services.placeholders.litigation.execution_request_service import ExecutionRequestService

        generated = ExecutionRequestService().generate({"case_id": int(case.id)})
        generated_text = str(
            generated.get(LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST)
            or generated.get("申请执行事项")
            or ""
        ).strip()
    except Exception:
        logger.exception("build_execution_request_text_failed", extra={"case_id": int(case.id)})

    if generated_text:
        return generated_text.replace("\a", "\n").replace("\r\n", "\n").replace("\r", "\n").strip()

    original_case_number = _resolve_original_case_number(case)
    case_number_text = original_case_number or "相关"
    fallback_lines = [
        f"一、请求依法强制执行{case_number_text}生效法律文书确定的全部给付义务。",
        "二、请求被执行人承担本案执行费用。",
    ]
    return "\n".join(fallback_lines).strip()


def _normalize_text(value: str) -> str:
    return _TEXT_NORMALIZE_PATTERN.sub("", str(value or "").strip().lower())


def _score_slot_for_signal(
    *, signal: str, strong: tuple[str, ...], weak: tuple[str, ...], exclude: tuple[str, ...]
) -> int:
    if not signal:
        return 0

    score = 0
    for keyword in strong:
        if _normalize_text(keyword) in signal:
            score += 5
    for keyword in weak:
        if _normalize_text(keyword) in signal:
            score += 2
    for keyword in exclude:
        if _normalize_text(keyword) in signal:
            score -= 6
    return score


def _build_material_slot_signals(*, material: Any, file_path: Path) -> tuple[list[str], list[str]]:
    """构建材料匹配信号，返回 (主信号列表, 辅信号列表)。

    主信号：type_name、CaseMaterialType.name —— 由用户/系统明确分类，权重最高。
    辅信号：文件名、路径等 —— 可能含歧义关键词，权重较低且去重。
    """
    primary_signals: list[str] = []
    secondary_signals: list[str] = []

    def _append_primary(raw_text: str) -> None:
        text = _normalize_text(raw_text)
        if text and text not in primary_signals:
            primary_signals.append(text)

    def _append_secondary(raw_text: str) -> None:
        text = _normalize_text(raw_text)
        if text and text not in secondary_signals:
            secondary_signals.append(text)

    # 主信号：type_name 和 CaseMaterialType.name
    _append_primary(str(material.type_name or ""))

    material_type = getattr(material, "type", None)
    if material_type is not None:
        _append_primary(str(getattr(material_type, "name", "") or ""))

    # 辅信号：文件名、路径等
    _append_secondary(file_path.name)
    _append_secondary(file_path.stem)
    _append_secondary(file_path.as_posix())
    _append_secondary(file_path.parent.as_posix())

    attachment = getattr(material, "source_attachment", None)
    if attachment is not None:
        attachment_name = str(getattr(getattr(attachment, "file", None), "name", "") or "")
        _append_secondary(attachment_name)
        attachment_log = getattr(attachment, "log", None)
        if attachment_log is not None:
            _append_secondary(str(getattr(attachment_log, "content", "") or ""))

    return primary_signals, secondary_signals


def _score_slot_deduplicated(
    *,
    primary_signals: list[str],
    secondary_signals: list[str],
    strong: tuple[str, ...],
    weak: tuple[str, ...],
    exclude: tuple[str, ...],
) -> int:
    """对槽位评分，主信号权重 ×2，辅信号按关键词去重避免重复计分。

    核心改进：
    1. 主信号（type_name）得分 ×2，因为这是用户/系统明确分类
    2. 辅信号（文件名、路径）中相同关键词只计一次最高分，
       防止 "营业执照" 在文件名+stem+路径中重复计算3次
    3. 当主信号已强匹配时，辅信号的反向匹配（exclude）也 ×2
    """
    if not primary_signals and not secondary_signals:
        return 0

    score = 0

    # 主信号评分（权重 ×2）
    for signal in primary_signals:
        if not signal:
            continue
        for keyword in strong:
            if _normalize_text(keyword) in signal:
                score += 10  # 5 × 2
        for keyword in weak:
            if _normalize_text(keyword) in signal:
                score += 4  # 2 × 2
        for keyword in exclude:
            if _normalize_text(keyword) in signal:
                score -= 12  # 6 × 2

    # 辅信号评分（按关键词去重：同一关键词在多个辅信号中只计一次最高分）
    for keyword in strong:
        norm_kw = _normalize_text(keyword)
        if any(norm_kw in s for s in secondary_signals):
            score += 5  # 命中一次即可，不重复
    for keyword in weak:
        norm_kw = _normalize_text(keyword)
        if any(norm_kw in s for s in secondary_signals):
            score += 2
    for keyword in exclude:
        norm_kw = _normalize_text(keyword)
        if any(norm_kw in s for s in secondary_signals):
            score -= 6

    return score


def _match_slot(*, material: Any, file_path: Path, filing_type: str) -> str:
    rules_by_slot = _SLOT_RULES.get(filing_type) or _SLOT_RULES[_FILING_TYPE_CIVIL]
    default_slot = _DEFAULT_SLOT_BY_FILING_TYPE.get(filing_type, "5")
    primary_signals, secondary_signals = _build_material_slot_signals(material=material, file_path=file_path)

    best_slot = default_slot
    best_score = 0

    for slot, rule in rules_by_slot.items():
        strong = rule.get("strong", ())
        weak = rule.get("weak", ())
        exclude = rule.get("exclude", ())
        slot_score = _score_slot_deduplicated(
            primary_signals=primary_signals,
            secondary_signals=secondary_signals,
            strong=strong,
            weak=weak,
            exclude=exclude,
        )
        if slot_score > best_score:
            best_slot = slot
            best_score = slot_score

    if best_score > 0:
        return best_slot

    joined_signal = "".join(primary_signals + secondary_signals)
    if filing_type == _FILING_TYPE_EXECUTION:
        execution_apply_hits = ("执行申请书", "申请执行书", "强制执行", "申请执行")
        execution_apply_excludes = ("限制高消费", "纳入失信", "公开信息", "出境")
        if any(keyword in joined_signal for keyword in execution_apply_hits) and not any(
            keyword in joined_signal for keyword in execution_apply_excludes
        ):
            return "0"
    if "送达地址" in joined_signal:
        return "4"
    if any(kw in joined_signal for kw in ("保全", "保函", "保全申请")):
        return "5"

    return default_slot


def _build_materials_map(*, case: Any, filing_type: str) -> dict[str, list[str]]:
    from django.db.models import Q

    from apps.cases.models import CaseMaterial, CaseMaterialCategory, CaseMaterialSide

    case_materials = (
        CaseMaterial.objects.filter(case=case, category=CaseMaterialCategory.PARTY)
        .filter(Q(side=CaseMaterialSide.OUR) | Q(side__isnull=True) | Q(side=""))
        .select_related("type", "source_attachment", "source_attachment__log")
        .order_by("id")
    )

    if not case_materials.exists():
        case_materials = (
            CaseMaterial.objects.filter(case=case)
            .select_related("type", "source_attachment", "source_attachment__log")
            .order_by("id")
        )

    materials_map: dict[str, list[str]] = {}
    dedup_keys: set[tuple[str, str]] = set()

    for material in case_materials:
        if not material.source_attachment_id:
            continue

        attachment = material.source_attachment
        if not attachment or not getattr(attachment, "file", None):
            continue

        try:
            source_path = attachment.file.path
        except Exception:
            continue

        if not source_path:
            continue

        file_path = Path(source_path)
        if not file_path.exists() or file_path.suffix.lower() != ".pdf":
            continue

        slot = _match_slot(material=material, file_path=file_path, filing_type=filing_type)
        normalized_path = file_path.as_posix()
        dedup_key = (slot, normalized_path)
        if dedup_key in dedup_keys:
            continue
        dedup_keys.add(dedup_key)
        materials_map.setdefault(slot, []).append(normalized_path)

    return materials_map


def _build_session_status_payload(*, task: Any) -> dict[str, Any]:
    from apps.automation.models import ScraperTaskStatus

    if task.status in {ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING}:
        message = "立案任务执行中..."
        if isinstance(task.result, dict):
            message = str(task.result.get("message") or message)
        return {"success": True, "message": message, "session_id": task.id, "status": "in_progress"}

    if task.status == ScraperTaskStatus.SUCCESS:
        message = "立案流程执行完成（已到预览页，未提交）"
        if isinstance(task.result, dict):
            message = str(task.result.get("message") or message)
        return {"success": True, "message": message, "session_id": task.id, "status": "completed"}

    message = str(task.error_message or "").strip()
    if not message and isinstance(task.result, dict):
        message = str(task.result.get("message") or "").strip()
    if not message:
        message = "立案失败"
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
    updates: dict[str, Any] = {
        "status": status,
        "updated_at": now,
    }
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
            logger.exception("court_filing_session_update_failed", extra={"session_id": session_id, "status": status})
        finally:
            close_old_connections()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _do_update()
        return

    _SESSION_UPDATE_EXECUTOR.submit(_do_update)


def _run_filing(
    account: str,
    password: str,
    case_data: dict[str, Any],
    filing_type: str = _FILING_TYPE_CIVIL,
    session_id: int | None = None,
) -> None:
    """在后台线程中执行立案"""
    from playwright.sync_api import sync_playwright

    from apps.automation.models import ScraperTaskStatus
    from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
    from apps.automation.services.scraper.sites.court_zxfw_filing import CourtZxfwFilingService

    progress_logs: list[dict[str, str]] = []
    http_failure_reason = ""
    fallback_used = False

    def _phase_label(phase: str) -> str:
        normalized = phase.strip().lower()
        if normalized == "http":
            return "HTTP阶段"
        if normalized == "playwright":
            return "回退阶段"
        if normalized == "login":
            return "登录阶段"
        return "执行阶段"

    def _build_progress_payload(*, message: str, stage: str, phase: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": message,
            "stage": stage,
            "phase": phase,
            "progress_logs": progress_logs[-80:],
        }
        if http_failure_reason:
            payload["http_failure_reason"] = http_failure_reason
        if fallback_used:
            payload["fallback_used"] = True
        return payload

    def _record_progress(
        *,
        phase: str,
        stage: str,
        message: str,
        level: str = "info",
        detail: str = "",
        persist_running: bool = True,
        set_started: bool = False,
    ) -> None:
        nonlocal http_failure_reason, fallback_used

        normalized_phase = str(phase or "system").strip().lower() or "system"
        normalized_stage = str(stage or "unknown").strip() or "unknown"
        normalized_level = str(level or "info").strip().lower() or "info"
        normalized_message = str(message or "").strip() or normalized_stage
        normalized_detail = str(detail or "").strip()
        if normalized_detail:
            normalized_message = f"{normalized_message} | {normalized_detail}"

        if progress_logs:
            latest = progress_logs[-1]
            if (
                latest.get("phase") == normalized_phase
                and latest.get("stage") == normalized_stage
                and latest.get("level") == normalized_level
                and latest.get("message") == normalized_message
            ):
                return

        if normalized_phase == "http" and normalized_level == "error":
            http_failure_reason = normalized_message
        if normalized_phase == "playwright":
            fallback_used = True

        if normalized_level == "error":
            logger.error(
                "court_filing_progress[%s/%s] %s",
                normalized_phase,
                normalized_stage,
                normalized_message,
            )
        elif normalized_level == "warning":
            logger.warning(
                "court_filing_progress[%s/%s] %s",
                normalized_phase,
                normalized_stage,
                normalized_message,
            )
        else:
            logger.info(
                "court_filing_progress[%s/%s] %s",
                normalized_phase,
                normalized_stage,
                normalized_message,
            )

        progress_logs.append(
            {
                "time": timezone.now().strftime("%H:%M:%S"),
                "phase": normalized_phase,
                "stage": normalized_stage,
                "level": normalized_level,
                "message": normalized_message,
            }
        )
        if len(progress_logs) > 160:
            del progress_logs[:-160]

        if not persist_running:
            return

        display_message = f"{_phase_label(normalized_phase)}: {normalized_message}"
        _update_session_task(
            session_id=session_id,
            status=ScraperTaskStatus.RUNNING,
            error_message="",
            result=_build_progress_payload(
                message=display_message,
                stage=normalized_stage,
                phase=normalized_phase,
            ),
            set_started=set_started,
        )

    def _service_progress_reporter(event: dict[str, Any]) -> None:
        _record_progress(
            phase=str(event.get("phase") or "system"),
            stage=str(event.get("stage") or "service"),
            level=str(event.get("level") or "info"),
            message=str(event.get("message") or ""),
            detail=str(event.get("detail") or ""),
        )

    _record_progress(
        phase="login",
        stage="login.start",
        message="正在登录一张网...",
        set_started=True,
    )

    with sync_playwright() as p:
        # Docker/NAS 环境通常没有 XServer，缺少 DISPLAY 时自动走无头模式。
        _headless = not bool(os.environ.get("DISPLAY"))
        browser = p.chromium.launch(headless=_headless)
        context = browser.new_context()
        page = context.new_page()

        try:
            login_service = CourtZxfwService(page=page, context=context)
            login_result = login_service.login(account=account, password=password)
            if not login_result.get("success"):
                message = str(login_result.get("message") or "一张网登录失败")
                logger.error("一张网登录失败: %s", login_result)
                _record_progress(
                    phase="login",
                    stage="login.failed",
                    level="error",
                    message=f"登录失败: {message}",
                    persist_running=False,
                )
                failed_result = _build_progress_payload(
                    message=f"登录阶段: 登录失败: {message}",
                    stage="login.failed",
                    phase="login",
                )
                failed_result["success"] = False
                _update_session_task(
                    session_id=session_id,
                    status=ScraperTaskStatus.FAILED,
                    error_message=message,
                    result=failed_result,
                    set_finished=True,
                )
                return

            _record_progress(
                phase="login",
                stage="login.success",
                message="一张网登录成功",
            )

            token_value = str(login_result.get("token") or "").strip() or None
            filing_service = CourtZxfwFilingService(page=page, save_debug=True)
            case_data_runtime = dict(case_data)
            case_data_runtime["_progress_reporter"] = _service_progress_reporter

            _record_progress(
                phase="system",
                stage="filing.start",
                message="开始执行立案流程",
            )

            if filing_type == _FILING_TYPE_EXECUTION:
                result = filing_service.file_execution(case_data_runtime, token=token_value)
            else:
                result = filing_service.file_case(case_data_runtime, token=token_value)

            if not result.get("success", False):
                message = str(result.get("message") or "立案失败")
                _record_progress(
                    phase="system",
                    stage="filing.failed",
                    level="error",
                    message=message,
                    persist_running=False,
                )
                failed_result = _build_progress_payload(
                    message=f"执行阶段: {message}",
                    stage="filing.failed",
                    phase="system",
                )
                failed_result["success"] = False
                _update_session_task(
                    session_id=session_id,
                    status=ScraperTaskStatus.FAILED,
                    error_message=message,
                    result=failed_result,
                    set_finished=True,
                )
                return

            success_message = str(result.get("message") or "立案流程执行完成")
            if fallback_used and http_failure_reason:
                success_message = f"{success_message}（HTTP失败后已回退Playwright）"
            _record_progress(
                phase="system",
                stage="filing.success",
                message=success_message,
                persist_running=False,
            )
            final_result = dict(result)
            final_result.update(
                _build_progress_payload(
                    message=f"执行阶段: {success_message}",
                    stage="filing.success",
                    phase="system",
                )
            )
            final_result["success"] = True
            final_result["message"] = success_message
            _update_session_task(
                session_id=session_id,
                status=ScraperTaskStatus.SUCCESS,
                error_message="",
                result=final_result,
                set_finished=True,
            )
            logger.info("立案结果: %s", final_result)

        except Exception as exc:
            error_message = f"一张网立案执行失败: {exc}"
            logger.error(error_message, exc_info=True)
            _record_progress(
                phase="system",
                stage="filing.exception",
                level="error",
                message=error_message,
                persist_running=False,
            )
            failed_result = _build_progress_payload(
                message=f"执行阶段: {error_message}",
                stage="filing.exception",
                phase="system",
            )
            failed_result["success"] = False
            _update_session_task(
                session_id=session_id,
                status=ScraperTaskStatus.FAILED,
                error_message=error_message,
                result=failed_result,
                set_finished=True,
            )
        finally:
            context.close()
            browser.close()
