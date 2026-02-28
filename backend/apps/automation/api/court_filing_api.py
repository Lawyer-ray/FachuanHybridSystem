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

    from apps.cases.models import Case, SupervisingAuthority
    from apps.organization.models import AccountCredential

    case = Case.objects.get(pk=payload.case_id)

    # 获取一张网凭证
    credential = AccountCredential.objects.filter(
        lawyer=request.user,
        url__contains="zxfw.court.gov.cn",
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
        "case_id": case.id,
    }

    # 后台线程执行
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(
        _run_filing,
        account=str(credential.account),
        password=str(credential.password),
        case_data=case_data,
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


def _run_filing(account: str, password: str, case_data: dict[str, Any]) -> None:
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
            # 登录
            login_service = CourtZxfwService(page=page, context=context)
            login_result = login_service.login(account=account, password=password)
            if not login_result.get("success"):
                logger.error("一张网登录失败: %s", login_result)
                return

            # 立案
            filing_service = CourtZxfwFilingService(page=page, save_debug=True)
            result = filing_service.file_case(case_data)
            logger.info("立案结果: %s", result)

        except Exception as e:
            logger.error("一张网立案执行失败: %s", e, exc_info=True)
        finally:
            context.close()
            browser.close()
