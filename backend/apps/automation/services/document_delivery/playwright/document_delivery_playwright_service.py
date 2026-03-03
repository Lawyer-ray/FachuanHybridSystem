"""
文书送达 Playwright 查询服务

负责通过 Playwright 浏览器自动化查询文书。
"""

import logging
import traceback
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, cast

from django.utils.translation import gettext_lazy as _
from playwright.sync_api import Page

from apps.automation.services.document_delivery._downloading_mixin import DocumentDeliveryDownloadingMixin
from apps.automation.services.document_delivery._matching_mixin import DocumentDeliveryMatchingMixin
from apps.automation.services.document_delivery._parsing_mixin import DocumentDeliveryParsingMixin
from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentProcessResult,
    DocumentQueryResult,
)
from apps.automation.utils.logging import AutomationLogger
from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.automation.services.scraper.core.browser_service import BrowserService
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService

logger = logging.getLogger("apps.automation")


class DocumentDeliveryPlaywrightService(
    DocumentDeliveryMatchingMixin,
    DocumentDeliveryDownloadingMixin,
    DocumentDeliveryParsingMixin,
):
    """文书送达 Playwright 查询服务"""

    DELIVERY_PAGE_URL = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/common/wssd/index"
    PENDING_TAB_SELECTOR = (
        "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[1]"
        "/uni-view/uni-view[1]/uni-view/uni-text"
    )
    REVIEWED_TAB_SELECTOR = (
        "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[1]"
        "/uni-view/uni-view[2]/uni-view/uni-text"
    )
    CASE_NUMBER_SELECTOR = (
        "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]"
        "/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view"
        "/uni-form/span/uni-view[1]/uni-view"
    )
    SEND_TIME_SELECTOR = (
        "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]"
        "/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view"
        "/uni-form/span/uni-view[3]/uni-view"
    )
    DOWNLOAD_BUTTON_SELECTOR = (
        "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]"
        "/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view[2]/uni-text[2]"
    )
    NEXT_PAGE_SELECTOR = (
        "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]"
        "/uni-view/uni-view/uni-view/uni-view[4]"
    )
    PAGE_LOAD_WAIT = 3000

    def __init__(
        self,
        browser_service: Optional["BrowserService"] = None,
        case_matcher: Optional["CaseMatcher"] = None,
        document_renamer: Optional["DocumentRenamer"] = None,
        notification_service: Optional["SMSNotificationService"] = None,
    ) -> None:
        self._browser_service = browser_service
        self._case_matcher = case_matcher
        self._document_renamer = document_renamer
        self._notification_service = notification_service
        logger.debug("DocumentDeliveryPlaywrightService 初始化完成")

    @property
    def browser_service(self) -> "BrowserService":
        if self._browser_service is None:
            from apps.automation.services.scraper.core.browser_service import BrowserService

            self._browser_service = BrowserService()
        return self._browser_service

    @property
    def case_matcher(self) -> "CaseMatcher":
        if self._case_matcher is None:
            from apps.automation.services.sms.case_matcher import CaseMatcher

            self._case_matcher = CaseMatcher()
        return self._case_matcher

    @property
    def document_renamer(self) -> "DocumentRenamer":
        if self._document_renamer is None:
            from apps.automation.services.sms.document_renamer import DocumentRenamer

            self._document_renamer = DocumentRenamer()
        return self._document_renamer

    @property
    def notification_service(self) -> "SMSNotificationService":
        if self._notification_service is None:
            from apps.automation.services.sms.sms_notification_service import SMSNotificationService

            self._notification_service = SMSNotificationService()
        return self._notification_service

    def _should_process(self, record: DocumentDeliveryRecord, cutoff_time: datetime, credential_id: int) -> bool:
        if record.send_time is None or record.send_time <= cutoff_time:
            logger.info(f"⏰ 文书时间 {record.send_time} 早于截止时间 {cutoff_time}，跳过")
            return False
        return self._check_not_processed_in_thread(credential_id, record)

    def _process_document_entry(
        self, page: Page, entry: DocumentDeliveryRecord, credential_id: int
    ) -> DocumentProcessResult:
        """处理单个文书条目"""
        logger.info(f"开始处理文书: {entry.case_number} - {entry.send_time}")
        result = DocumentProcessResult(
            success=False,
            case_id=None,
            case_log_id=None,
            renamed_path=None,
            notification_sent=False,
            error_message=None,
        )
        try:
            file_path = self._download_document(page, entry)
            if not file_path:
                result.error_message = str(_("文书下载失败"))
                return result
            process_result = self._process_downloaded_document(file_path, entry, credential_id)
            self._record_query_history_in_thread(credential_id, entry)
            result.success = process_result.success
            result.case_id = process_result.case_id
            result.case_log_id = process_result.case_log_id
            result.renamed_path = process_result.renamed_path
            result.notification_sent = process_result.notification_sent
            result.error_message = process_result.error_message
        except Exception as e:
            result.error_message = f"处理文书失败: {e!s}"
            logger.error(result.error_message)
        return result

    def _process_page_entries(
        self,
        page: Page,
        cutoff_time: datetime,
        credential_id: int,
        result: DocumentQueryResult,
    ) -> bool:
        """处理当前页的文书条目，返回是否需要继续翻页"""
        entries = self._extract_document_entries(page)
        result.total_found += len(entries)
        if not entries:
            logger.info("当前页面没有文书条目，结束处理")
            return False
        should_continue = False
        for entry in entries:
            if self._should_process(entry, cutoff_time, credential_id):
                process_result = self._process_document_entry(page, entry, credential_id)
                if process_result.success:
                    result.processed_count += 1
                    if process_result.case_log_id:
                        result.case_log_ids.append(process_result.case_log_id)
                else:
                    result.failed_count += 1
                    if process_result.error_message:
                        result.errors.append(process_result.error_message)
                if entry.send_time is not None and entry.send_time > cutoff_time:
                    should_continue = True
            else:
                result.skipped_count += 1
                if entry.send_time is None or entry.send_time <= cutoff_time:
                    return False
        return should_continue

    def _paginate_documents(
        self,
        page: Page,
        cutoff_time: datetime,
        credential_id: int,
        result: DocumentQueryResult,
    ) -> None:
        """分页处理所有文书"""
        page_num = 1
        while True:
            logger.info(f"处理第 {page_num} 页")
            should_continue = self._process_page_entries(page, cutoff_time, credential_id, result)
            if not should_continue or not self._has_next_page(page):
                break
            self._go_to_next_page(page)
            page_num += 1

    def _sync_login_with_page(self, credential: Any, page: Page) -> str:
        """同步登录方法"""
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

        court_service = CourtZxfwService(page=page, context=page.context, site_name=credential.site_name)
        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"登录尝试 {attempt}/{max_retries}")
                login_result = court_service.login(
                    account=credential.account,
                    password=credential.password,
                    max_captcha_retries=3,
                    save_debug=False,
                )
                if login_result.get("success"):
                    token = login_result.get("token")
                    if token:
                        return cast(str, token)
                    raise Exception("登录成功但未获取到token")
                raise Exception(f"登录失败: {login_result.get('message', '未知错误')}")
            except Exception as e:
                last_error = e
                logger.warning(f"登录尝试 {attempt} 失败: {e!s}")
                if attempt < max_retries:
                    import time

                    time.sleep(2)
        raise last_error or Exception("登录失败，已达最大重试次数")

    def query_documents(
        self, credential_id: int, cutoff_time: datetime, tab: str = "pending", debug_mode: bool = True
    ) -> DocumentQueryResult:
        """使用 Playwright 方式查询文书"""
        logger.info(f"Playwright 方式查询文书: credential_id={credential_id}")
        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        try:
            organization_service = ServiceLocator.get_organization_service()
            credential = organization_service.get_credential_internal(credential_id)
            if not credential:
                error_msg = f"账号凭证不存在: {credential_id}"
                logger.error(error_msg)
                result.errors.append(error_msg)
                return result
            browser = self.browser_service.get_browser()
            page = browser.new_page()
            try:
                try:
                    token = self._sync_login_with_page(credential, page)
                    logger.info(f"登录成功，获得token: {token[:20] if token else 'None'}...")
                except Exception as login_error:
                    error_msg = f"登录失败: {login_error!s}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    return result
                self._navigate_to_delivery_page(page, tab)
                self._paginate_documents(page, cutoff_time, credential_id, result)
            finally:
                if not debug_mode:
                    try:
                        page.close()
                    except Exception as e:
                        logger.warning(f"关闭页面失败: {e!s}")
                else:
                    logger.info("🔍 调试模式：浏览器保持打开，请手动检查页面状态")
        except Exception as e:
            error_msg = f"查询文书失败: {e!s}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            AutomationLogger.log_api_error_detail(
                api_name="playwright_document_query",
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc(),
            )
        AutomationLogger.log_document_query_statistics(
            total_found=result.total_found,
            processed_count=result.processed_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count,
            query_method="playwright",
            credential_id=credential_id,
        )
        return result

    def query_documents_with_token(
        self, credential_id: int, cutoff_time: datetime, page: Page, tab: str = "pending", debug_mode: bool = True
    ) -> DocumentQueryResult:
        """使用已登录的 page 查询文书"""
        logger.info(f"使用已登录页面查询文书: credential_id={credential_id}")
        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        try:
            self._navigate_to_delivery_page(page, tab)
            self._paginate_documents(page, cutoff_time, credential_id, result)
        except Exception as e:
            error_msg = f"查询文书失败: {e!s}"
            logger.error(error_msg)
            result.errors.append(error_msg)
        return result
