"""全国法院"一张网"在线立案服务 facade。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _
from playwright.sync_api import Page

from .filing_steps import FilingStepsMixin
from .party_info_handler import PartyInfoHandlerMixin
from .progress_reporter import ProgressReporterMixin

if TYPE_CHECKING:
    from plugins.court_filing_http.api_service import CourtZxfwFilingApiService

logger = logging.getLogger("apps.automation")


class CourtZxfwFilingService(FilingStepsMixin, PartyInfoHandlerMixin, ProgressReporterMixin):
    """
    全国法院"一张网"在线立案服务

    前置条件: 需要已登录的 Page 对象（由 CourtZxfwService.login() 完成）

    民事一审流程（6步）:
    1. 选择受理法院 → 2. 阅读须知 → 3. 选择案由 → 4. 上传材料 → 5. 完善信息 → 6. 预览

    申请执行流程（5步）:
    1. 选择受理法院 → 2. 阅读须知 → 3. 上传材料(含执行依据) → 4. 完善信息 → 5. 预览
    """

    BASE_URL = "https://zxfw.court.gov.cn/zxfw"
    CASE_TYPE_URL = f"{BASE_URL}/#/pagesWsla/pc/zxla/pick-case-type/index"

    PROVINCE_CODES: dict[str, str] = {
        "广东省": "440000",
        "北京市": "110000",
        "上海市": "310000",
        "浙江省": "330000",
        "江苏省": "320000",
        "山东省": "370000",
        "四川省": "510000",
        "湖北省": "420000",
        "湖南省": "430000",
        "福建省": "350000",
        "河南省": "410000",
        "河北省": "130000",
        "安徽省": "340000",
        "重庆市": "500000",
        "天津市": "120000",
    }

    EXEC_SECTION_MAP: dict[str, str] = {
        "plaintiffs": "申请执行人信息",
        "defendants": "被执行人信息",
    }

    CIVIL_SECTION_MAP: dict[str, str] = {
        "plaintiffs": "原告信息",
        "defendants": "被告信息",
        "third_parties": "第三人信息",
    }

    CIVIL_UPLOAD_SLOT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
        ("0", ("起诉状", "诉状")),
        ("1", ("当事人身份证明", "身份证明", "营业执照", "身份证")),
        ("2", ("委托代理人委托手续和身份材料", "授权委托书", "律师执业证", "委托代理")),
        ("3", ("证据目录及证据材料", "证据目录", "证据材料")),
        ("4", ("送达地址确认书", "送达地址")),
        ("5", ("其他材料",)),
    ]

    EXEC_UPLOAD_SLOT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
        ("0", ("执行申请书", "申请执行书", "申请书")),
        ("1", ("执行依据文书", "执行依据", "判决书", "裁定书", "调解书")),
        ("2", ("授权委托书及代理人身份证明", "授权委托书", "律师执业证", "代理人身份证明")),
        ("3", ("申请人身份材料", "身份证明", "营业执照", "身份证")),
        ("4", ("送达地址确认书", "送达地址")),
    ]

    def __init__(self, page: Page, *, save_debug: bool = False) -> None:
        self.page = page
        self.save_debug = save_debug

    # ==================== 主入口 ====================

    def file_case(self, case_data: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        """执行民事一审在线立案全流程。"""
        filing_engine = self._resolve_filing_engine(case_data)
        api_error: Exception | None = None
        if filing_engine == "api":
            self._report_progress(
                case_data, phase="http", stage="http.start",
                message="HTTP主链路：开始民事一审立案",
            )
            if not token:
                api_error = ValueError(str(_("HTTP立案缺少登录令牌")))
                if not self._allow_playwright_fallback(case_data):
                    raise ValueError(str(_("接口立案失败: %(error)s")) % {"error": api_error}) from api_error
                self._report_progress(
                    case_data, phase="http", stage="http.failed", level="error",
                    message=f"HTTP主链路失败: {api_error}",
                )
                logger.warning("HTTP立案缺少登录令牌，回退 Playwright")
            else:
                try:
                    from plugins import has_court_filing_api_plugin

                    if not has_court_filing_api_plugin():
                        raise ImportError("HTTP链路插件未安装")

                    self._report_progress(
                        case_data, phase="http", stage="http.submit",
                        message="HTTP主链路：正在提交一张网草稿",
                    )
                    from plugins.court_filing_http.api_service import CourtZxfwFilingApiService

                    api_svc = CourtZxfwFilingApiService(token)
                    result: dict[str, object] = api_svc.file_civil_case_sync(case_data)
                    self._report_progress(
                        case_data, phase="http", stage="http.success",
                        message="HTTP主链路提交成功",
                    )
                    logger.info("HTTP立案成功: %s", result)
                    return result
                except Exception as api_err:
                    api_error = api_err
                    self._report_progress(
                        case_data, phase="http", stage="http.failed", level="error",
                        message=f"HTTP主链路失败: {api_err}",
                    )
                    if not self._allow_playwright_fallback(case_data):
                        logger.error("HTTP立案失败: %s", api_err, exc_info=True)
                        raise ValueError(str(_("接口立案失败: %(error)s")) % {"error": api_err}) from api_err
                    logger.warning("HTTP立案失败，回退 Playwright: %s", api_err, exc_info=True)

        self._report_progress(
            case_data, phase="playwright", stage="playwright.start",
            message="进入Playwright回退流程（民事一审）",
        )

        court_name: str = case_data["court_name"]
        cause_of_action: str = case_data["cause_of_action"]

        logger.info("=" * 60)
        logger.info(str(_("开始民事一审立案: 法院=%s, 案由=%s")), court_name, cause_of_action)
        logger.info("=" * 60)

        try:
            province = case_data.get("province", "广东省")
            province_code = self.PROVINCE_CODES.get(province, "440000")

            self._report_progress(case_data, phase="playwright", stage="playwright.step.open_case_type", message="回退阶段：打开案件类型页")
            self._open_case_type_page("民事一审", province_code)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.select_court", message="回退阶段：选择受理法院")
            self._step1_select_court(court_name)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.read_notice", message="回退阶段：确认立案须知")
            self._step2_read_notice()
            self._report_progress(case_data, phase="playwright", stage="playwright.step.select_cause", message="回退阶段：选择案由")
            self._step3_select_cause(cause_of_action)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.upload_materials", message="回退阶段：上传诉讼材料")
            self._step4_upload_materials(case_data.get("materials", {}), is_execution=False)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.fill_case_info", message="回退阶段：完善当事人和代理人信息")
            self._step5_complete_info(case_data, section_map=self.CIVIL_SECTION_MAP)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.next", message="回退阶段：进入预览页")
            self._click_next_step()
            self._step6_preview_submit()
            self._report_progress(case_data, phase="playwright", stage="playwright.success", message="Playwright回退流程完成（已到预览页）")

            logger.info(str(_("民事一审立案流程执行完成")))
            return {"success": True, "message": str(_("立案流程执行完成（已到预览页，未提交）")), "url": self.page.url}

        except Exception as e:
            self._report_progress(case_data, phase="playwright", stage="playwright.failed", level="error", message=f"Playwright回退失败: {e}")
            logger.error("民事一审立案失败: %s", e, exc_info=True)
            if self.save_debug:
                self._save_screenshot("error_civil_filing")
            merged_error = str(e)
            if api_error is not None:
                merged_error = f"HTTP主链路失败({api_error})，且Playwright回退失败({e})"
            raise ValueError(str(_("立案失败: %(error)s")) % {"error": merged_error}) from e

    def file_execution(self, case_data: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        """执行申请执行在线立案全流程。"""
        filing_engine = self._resolve_filing_engine(case_data)
        api_error: Exception | None = None
        if filing_engine == "api":
            self._report_progress(case_data, phase="http", stage="http.start", message="HTTP主链路：开始申请执行立案")
            if not token:
                api_error = ValueError(str(_("HTTP立案缺少登录令牌")))
                if not self._allow_playwright_fallback(case_data):
                    raise ValueError(str(_("接口立案失败: %(error)s")) % {"error": api_error}) from api_error
                self._report_progress(case_data, phase="http", stage="http.failed", level="error", message=f"HTTP主链路失败: {api_error}")
                logger.warning("HTTP立案缺少登录令牌，回退 Playwright")
            else:
                try:
                    from plugins import has_court_filing_api_plugin

                    if not has_court_filing_api_plugin():
                        raise ImportError("HTTP链路插件未安装")

                    self._report_progress(case_data, phase="http", stage="http.submit", message="HTTP主链路：正在提交一张网草稿")
                    from plugins.court_filing_http.api_service import CourtZxfwFilingApiService

                    api_svc = CourtZxfwFilingApiService(token)
                    result: dict[str, object] = api_svc.file_execution_sync(case_data)
                    self._report_progress(case_data, phase="http", stage="http.success", message="HTTP主链路提交成功")
                    logger.info("HTTP立案成功: %s", result)
                    return result
                except Exception as api_err:
                    api_error = api_err
                    self._report_progress(case_data, phase="http", stage="http.failed", level="error", message=f"HTTP主链路失败: {api_err}")
                    if not self._allow_playwright_fallback(case_data):
                        logger.error("HTTP立案失败: %s", api_err, exc_info=True)
                        raise ValueError(str(_("接口立案失败: %(error)s")) % {"error": api_err}) from api_err
                    logger.warning("HTTP立案失败，回退 Playwright: %s", api_err, exc_info=True)

        self._report_progress(case_data, phase="playwright", stage="playwright.start", message="进入Playwright回退流程（申请执行）")

        court_name: str = case_data["court_name"]

        logger.info("=" * 60)
        logger.info(str(_("开始申请执行立案: 法院=%s")), court_name)
        logger.info("=" * 60)

        try:
            province = case_data.get("province", "广东省")
            province_code = self.PROVINCE_CODES.get(province, "440000")

            self._report_progress(case_data, phase="playwright", stage="playwright.step.open_case_type", message="回退阶段：打开案件类型页")
            self._open_case_type_page("申请执行", province_code)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.select_court", message="回退阶段：选择受理法院")
            self._step1_select_court(court_name)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.read_notice", message="回退阶段：确认立案须知")
            self._step2_read_notice(has_prepared_doc=False)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.select_execution_basis", message="回退阶段：填写执行依据信息")
            self._step_exec_select_basis(case_data)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.upload_materials", message="回退阶段：上传执行材料")
            self._step4_upload_materials(case_data.get("materials", {}), is_execution=True)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.fill_case_info", message="回退阶段：完善当事人和代理人信息")
            self._step5_complete_info(case_data, section_map=self.EXEC_SECTION_MAP)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.fill_execution_target", message="回退阶段：填写执行标的信息")
            self._fill_execution_target_info(case_data)
            self._report_progress(case_data, phase="playwright", stage="playwright.step.next", message="回退阶段：进入预览页")
            self._click_next_step()
            self._step6_preview_submit()
            self._report_progress(case_data, phase="playwright", stage="playwright.success", message="Playwright回退流程完成（已到预览页）")

            logger.info(str(_("申请执行立案流程执行完成")))
            return {"success": True, "message": str(_("申请执行流程执行完成（已到预览页，未提交）")), "url": self.page.url}

        except Exception as e:
            self._report_progress(case_data, phase="playwright", stage="playwright.failed", level="error", message=f"Playwright回退失败: {e}")
            logger.error("申请执行立案失败: %s", e, exc_info=True)
            if self.save_debug:
                self._save_screenshot("error_exec_filing")
            merged_error = str(e)
            if api_error is not None:
                merged_error = f"HTTP主链路失败({api_error})，且Playwright回退失败({e})"
            raise ValueError(str(_("申请执行立案失败: %(error)s")) % {"error": merged_error}) from e
