"""法院一张网在线立案 API"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

logger = logging.getLogger("apps.automation")
router = Router()


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


class ExecuteCourtFilingIn(Schema):
    """执行立案请求"""

    case_id: int
    filing_type: str = "civil"  # "civil" 或 "execution"


class ExecuteCourtFilingOut(Schema):
    """执行立案响应"""

    success: bool
    message: str
    session_id: int | None = None
    status: str | None = None


# ==================== API ====================


@router.get("/case-info/{case_id}", response=CaseFilingInfoOut)
def get_case_filing_info(request: HttpRequest, case_id: int) -> Any:
    """获取案件立案所需信息"""
    from apps.cases.models import Case, CaseParty, SupervisingAuthority

    case = Case.objects.get(pk=case_id)

    # 从 SupervisingAuthority 获取管辖法院名称
    court_name: str | None = None
    sa = SupervisingAuthority.objects.filter(
        case=case, authority_type="trial"
    ).first()
    if sa:
        court_name = _resolve_court_name(sa.name)

    # 获取原被告
    parties = CaseParty.objects.filter(case=case).select_related("client")
    plaintiff_name: str | None = None
    defendant_name: str | None = None
    for p in parties:
        if p.legal_status == "plaintiff":
            plaintiff_name = p.client.name
        elif p.legal_status == "defendant":
            defendant_name = p.client.name

    return {
        "case_id": case.id,
        "case_name": case.name,
        "cause_of_action": case.cause_of_action or "",
        "court_name": court_name,
        "target_amount": str(case.target_amount) if case.target_amount else None,
        "plaintiff_name": plaintiff_name,
        "defendant_name": defendant_name,
    }


@router.post("/execute", response=ExecuteCourtFilingOut)
def execute_court_filing(request: HttpRequest, payload: ExecuteCourtFilingIn) -> Any:
    """执行一张网在线立案（后台线程）"""
    from concurrent.futures import ThreadPoolExecutor

    from apps.cases.models import Case, CaseParty, SupervisingAuthority
    from apps.organization.models import AccountCredential

    case = Case.objects.get(pk=payload.case_id)

    # 获取一张网凭证
    credential = AccountCredential.objects.filter(
        lawyer=request.user,
        site_name="一张网",
    ).first()
    if not credential:
        return {"success": False, "message": "未找到一张网账号凭证", "session_id": None}

    # 获取法院名称
    sa = SupervisingAuthority.objects.filter(case=case, authority_type="trial").first()
    if not sa:
        return {"success": False, "message": "未设置管辖法院", "session_id": None}

    court_name = _resolve_court_name(sa.name)
    if not court_name:
        return {"success": False, "message": "无法解析管辖法院名称", "session_id": None}

    case_data = {
        "court_name": court_name,
        "cause_of_action": case.cause_of_action or "",
        "target_amount": str(case.target_amount) if case.target_amount else "",
        "case_id": case.id,
    }

    # 从 Court 模型获取省份
    from apps.core.models import Court as CourtModel

    court_obj = CourtModel.objects.filter(name=court_name).first()
    if court_obj and court_obj.province:
        case_data["province"] = court_obj.province

    # 构建多原告/多被告列表
    from apps.core.utils.id_card_utils import IdCardUtils

    parties = CaseParty.objects.filter(case=case).select_related("client")
    plaintiffs: list[dict[str, Any]] = []
    defendants: list[dict[str, Any]] = []
    third_parties: list[dict[str, Any]] = []

    for p in parties:
        c = p.client
        is_natural = c.client_type == "natural"
        party_data: dict[str, Any] = {
            "type": "natural" if is_natural else "legal",
            "name": c.name,
            "address": c.address or "",
            "phone": c.phone or "",
        }
        if is_natural:
            party_data["id_number"] = c.id_number or ""
            party_data["gender"] = (
                IdCardUtils.extract_gender(c.id_number or "") or "男"
            )
        else:
            party_data["uscc"] = c.id_number or ""
            party_data["legal_rep"] = c.legal_representative or ""

        if p.legal_status == "plaintiff":
            plaintiffs.append(party_data)
        elif p.legal_status == "defendant":
            defendants.append(party_data)
        elif p.legal_status == "third_party":
            third_parties.append(party_data)

    case_data["plaintiffs"] = plaintiffs
    case_data["defendants"] = defendants
    if third_parties:
        case_data["third_parties"] = third_parties

    # 构建上传材料映射 (槽位索引 -> 文件路径列表)
    # 一张网上传槽位: 0=起诉状, 1=当事人身份证明, 2=委托代理人材料,
    #                3=证据目录及证据材料, 4=送达地址确认书, 5=其他材料
    from apps.cases.models import CaseMaterial

    SLOT_KEYWORDS: list[tuple[str, list[str]]] = [
        ("0", ["起诉状", "诉状"]),
        ("1", ["身份证明", "营业执照", "身份证", "户口"]),
        ("2", ["委托", "授权", "代理", "律师执业证", "执业证"]),
        ("3", ["证据目录", "证据材料", "证据"]),
        ("4", ["送达地址确认书", "送达地址"]),
    ]

    def _match_slot(type_name: str) -> str:
        for slot, keywords in SLOT_KEYWORDS:
            if any(kw in type_name for kw in keywords):
                return slot
        return "5"

    materials_map: dict[str, list[str]] = {}
    case_materials = CaseMaterial.objects.filter(
        case=case,
    ).select_related("source_attachment")
    for m in case_materials:
        if not m.source_attachment_id:
            continue
        file_path = m.source_attachment.file.path
        slot = _match_slot(m.type_name)
        materials_map.setdefault(slot, []).append(file_path)
    case_data["materials"] = materials_map

    # 申请执行额外字段
    if payload.filing_type == "execution":
        case_data["original_case_number"] = case.case_number or ""
        case_data["execution_basis_type"] = "民商"
        case_data["execution_reason"] = ""  # TODO: 从强制执行申请书提取
        case_data["execution_request"] = ""  # TODO: 从强制执行申请书提取

        # 申请执行的材料槽位不同
        exec_slot_keywords: list[tuple[str, list[str]]] = [
            ("0", ["执行申请书", "申请书"]),
            ("1", ["执行依据", "判决书", "裁定书", "调解书"]),
            ("2", ["委托", "授权", "代理", "律师执业证", "执业证"]),
            ("3", ["身份证明", "营业执照", "身份证", "户口"]),
            ("4", ["送达地址确认书", "送达地址"]),
        ]

        def _match_exec_slot(type_name: str) -> str:
            for slot, keywords in exec_slot_keywords:
                if any(kw in type_name for kw in keywords):
                    return slot
            return "4"

        exec_materials: dict[str, list[str]] = {}
        for m in case_materials:
            if not m.source_attachment_id:
                continue
            file_path = m.source_attachment.file.path
            slot = _match_exec_slot(m.type_name)
            exec_materials.setdefault(slot, []).append(file_path)
        case_data["materials"] = exec_materials

    # 后台线程执行
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(
        _run_filing,
        account=str(credential.account),
        password=str(credential.password),
        case_data=case_data,
        filing_type=payload.filing_type,
    )

    return {
        "success": True,
        "message": "立案任务已启动，浏览器即将打开...",
        "session_id": None,
        "status": "in_progress",
    }


# ==================== 内部函数 ====================


def _resolve_court_name(authority_name: str) -> str | None:
    """将管辖机关名称解析为完整法院名称

    例如: "天河区" -> "广州市天河区人民法院"
    """
    if "人民法院" in authority_name:
        return authority_name

    from apps.core.models import Court

    court = Court.objects.filter(name__contains=authority_name).first()
    if court:
        return court.name

    return f"{authority_name}人民法院"


def _run_filing(account: str, password: str, case_data: dict[str, Any], filing_type: str = "civil") -> None:
    """在后台线程中执行立案"""
    from playwright.sync_api import sync_playwright

    from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
    from apps.automation.services.scraper.sites.court_zxfw_filing import (
        CourtZxfwFilingService,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        try:
            login_service = CourtZxfwService(page=page, context=context)
            login_result = login_service.login(account=account, password=password)
            if not login_result.get("success"):
                logger.error("一张网登录失败: %s", login_result)
                return

            filing_service = CourtZxfwFilingService(page=page, save_debug=True)
            if filing_type == "execution":
                result = filing_service.file_execution(case_data)
            else:
                result = filing_service.file_case(case_data)
            logger.info("立案结果: %s", result)

        except Exception as e:
            logger.error("一张网立案执行失败: %s", e, exc_info=True)
        finally:
            context.close()
            browser.close()
