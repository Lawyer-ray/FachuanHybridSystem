"""
文书送达查询服务

负责页面抓取、下载和后续处理协调。
"""

import logging
import traceback
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, cast

from playwright.sync_api import Page

from apps.automation.models import DocumentQueryHistory
from apps.automation.utils.logging import AutomationLogger
from apps.core.interfaces import ServiceLocator

from ._downloading_mixin import DocumentDeliveryDownloadingMixin
from ._matching_mixin import DocumentDeliveryMatchingMixin
from ._parsing_mixin import DocumentDeliveryParsingMixin
from .data_classes import DocumentDeliveryRecord, DocumentProcessResult, DocumentQueryResult, DocumentRecord

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService
    from apps.core.interfaces import IAutoLoginService

    from .court_document_api_client import CourtDocumentApiClient
    from .token.document_delivery_token_service import DocumentDeliveryTokenService

logger = logging.getLogger("apps.automation")


class DocumentDeliveryService(
    DocumentDeliveryMatchingMixin,
    DocumentDeliveryDownloadingMixin,
    DocumentDeliveryParsingMixin,
):
    """文书送达查询服务"""

    # 页面 URL
    DELIVERY_PAGE_URL = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/common/wssd/index"

    # 选择器常量 (使用精确 xpath)
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

    # 页面加载等待时间（毫秒）
    PAGE_LOAD_WAIT = 3000

    def __init__(
        self,
        case_matcher: Optional["CaseMatcher"] = None,
        document_renamer: Optional["DocumentRenamer"] = None,
        notification_service: Optional["SMSNotificationService"] = None,
        auto_login_service: Optional["IAutoLoginService"] = None,
        api_client: Optional["CourtDocumentApiClient"] = None,
        token_service: Optional["DocumentDeliveryTokenService"] = None,
    ) -> None:
        self._case_matcher = case_matcher
        self._document_renamer = document_renamer
        self._notification_service = notification_service
        self._auto_login_service = auto_login_service
        self._api_client = api_client
        self._token_service = token_service
        logger.debug("DocumentDeliveryService 初始化完成")

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

    @property
    def auto_login_service(self) -> "IAutoLoginService":
        if self._auto_login_service is None:
            self._auto_login_service = ServiceLocator.get_auto_login_service()
        return self._auto_login_service

    @property
    def api_client(self) -> "CourtDocumentApiClient":
        if self._api_client is None:
            from .court_document_api_client import CourtDocumentApiClient
            self._api_client = CourtDocumentApiClient(auto_login_service=self.auto_login_service)
        return self._api_client

    @property
    def token_service(self) -> "DocumentDeliveryTokenService":
        if self._token_service is None:
            from .token.document_delivery_token_service import DocumentDeliveryTokenService
            self._token_service = DocumentDeliveryTokenService()
        return self._token_service

    # ==================== API 优先策略方法 ====================

    def _query_via_api(self, token: str, cutoff_time: datetime, credential_id: int) -> DocumentQueryResult:
        """通过 API 查询文书（分页遍历）"""
        import math

        logger.info(f"开始 API 查询文书: cutoff_time={cutoff_time}")
        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        page_size = 20
        page_num = 1
        try:
            first_response = self.api_client.fetch_document_list(token=token, page_num=page_num, page_size=page_size)
            total = first_response.total
            result.total_found = total
            logger.info(f"API 查询: 总文书数={total}")
            if total == 0:
                return result
            total_pages = math.ceil(total / page_size)
            self._process_document_page(
                documents=first_response.documents,
                token=token, cutoff_time=cutoff_time, credential_id=credential_id, result=result,
            )
            for page_num in range(2, total_pages + 1):
                logger.info(f"处理第 {page_num}/{total_pages} 页")
                try:
                    page_response = self.api_client.fetch_document_list(
                        token=token, page_num=page_num, page_size=page_size
                    )
                    self._process_document_page(
                        documents=page_response.documents,
                        token=token, cutoff_time=cutoff_time, credential_id=credential_id, result=result,
                    )
                except Exception as e:
                    error_msg = f"处理第 {page_num} 页失败: {e!s}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
        except Exception as e:
            error_msg = f"API 查询失败: {e!s}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            raise
        logger.info(
            f"API 查询完成: 发现={result.total_found}, 处理={result.processed_count}, "
            f"跳过={result.skipped_count}, 失败={result.failed_count}"
        )
        return result

    def _process_document_page(
        self,
        documents: list[DocumentRecord],
        token: str,
        cutoff_time: datetime,
        credential_id: int,
        result: DocumentQueryResult,
    ) -> None:
        """处理一页文书记录"""
        for record in documents:
            try:
                logger.info(f"🔍 检查文书: {record.ah} - {record.fssj}")
                if not self._should_process_api_document(record, cutoff_time, credential_id):
                    result.skipped_count += 1
                    logger.info(f"⏭️ 跳过文书: {record.ah}")
                    continue
                logger.info(f"✅ 开始处理文书: {record.ah}")
                process_result = self._process_document_via_api(record=record, token=token, credential_id=credential_id)
                if process_result.success:
                    result.processed_count += 1
                    if process_result.case_log_id:
                        result.case_log_ids.append(process_result.case_log_id)
                else:
                    result.failed_count += 1
                    if process_result.error_message:
                        result.errors.append(process_result.error_message)
            except Exception as e:
                result.failed_count += 1
                error_msg = f"处理文书 {record.ah} 失败: {e!s}"
                result.errors.append(error_msg)
                logger.error(error_msg)

    def _process_document_via_api(
        self, record: DocumentRecord, token: str, credential_id: int
    ) -> DocumentProcessResult:
        """通过 API 处理单个文书"""
        import tempfile
        from pathlib import Path

        logger.info(f"开始 API 处理文书: {record.ah}, sdbh={record.sdbh}")
        result = DocumentProcessResult(
            success=False, case_id=None, case_log_id=None,
            renamed_path=None, notification_sent=False, error_message=None,
        )
        try:
            details = self.api_client.fetch_document_details(token=token, sdbh=record.sdbh)
            if not details:
                result.error_message = f"未获取到文书详情: sdbh={record.sdbh}"
                logger.warning(result.error_message)
                return result
            logger.info(f"获取到 {len(details)} 个文书下载链接")
            temp_dir = tempfile.mkdtemp(prefix="court_document_api_")
            downloaded_files = []
            for detail in details:
                if not detail.wjlj:
                    logger.warning(f"文书缺少下载链接: {detail.c_wsmc}")
                    continue
                file_ext = detail.c_wjgs or "pdf"
                file_name = f"{detail.c_wsmc}.{file_ext}"
                save_path = Path(temp_dir) / file_name
                success = self.api_client.download_document(url=detail.wjlj, save_path=save_path)
                if success:
                    downloaded_files.append(str(save_path))
                    logger.info(f"文书下载成功: {file_name}")
                else:
                    logger.warning(f"文书下载失败: {file_name}")
            if not downloaded_files:
                result.error_message = "所有文书下载失败"
                logger.error(result.error_message)
                return result
            send_time = record.parse_fssj()
            if send_time:
                from django.utils import timezone
                send_time = timezone.make_aware(send_time)
            else:
                from django.utils import timezone
                send_time = timezone.now()
            delivery_record = DocumentDeliveryRecord(
                case_number=record.ah, send_time=send_time,
                element_index=0, document_name=record.wsmc, court_name=record.fymc,
            )
            process_result = self._process_sms_in_thread(
                record=delivery_record, file_path=downloaded_files[0],
                extracted_files=downloaded_files, credential_id=credential_id,
            )
            self._record_query_history_in_thread(credential_id, delivery_record)
            result.success = process_result.get("success", False)
            result.case_id = process_result.get("case_id")
            result.case_log_id = process_result.get("case_log_id")
            result.renamed_path = process_result.get("renamed_path")
            result.notification_sent = process_result.get("notification_sent", False)
            result.error_message = process_result.get("error_message")
        except Exception as e:
            error_msg = f"API 处理文书失败: {e!s}"
            logger.error(error_msg)
            result.error_message = error_msg
        return result

    def _should_process_api_document(self, record: DocumentRecord, cutoff_time: datetime, credential_id: int) -> bool:
        """判断是否需要处理该 API 文书记录"""
        send_time = record.parse_fssj()
        if send_time is None:
            logger.warning(f"无法解析发送时间: {record.fssj}, 默认处理")
            return True
        from django.utils import timezone
        if timezone.is_aware(cutoff_time):
            send_time = timezone.make_aware(send_time)
        if send_time <= cutoff_time:
            logger.info(f"⏰ 文书时间 {send_time} 早于截止时间 {cutoff_time}，跳过")
            return False
        return self._check_api_document_not_processed(credential_id, record)

    def _check_api_document_not_processed(self, credential_id: int, record: DocumentRecord) -> bool:
        """检查 API 文书是否已成功处理完成"""
        import queue
        import threading

        result_queue: queue.Queue[bool] = queue.Queue()

        def do_check() -> None:
            try:
                from django.db import connection
                from apps.automation.models import CourtSMS, CourtSMSStatus
                connection.ensure_connection()
                completed_sms = CourtSMS.objects.filter(
                    case_numbers__contains=[record.ah], status=CourtSMSStatus.COMPLETED
                ).first()
                if completed_sms:
                    logger.info(f"🔄 文书已成功处理完成: {record.ah} - {record.fssj}, SMS ID={completed_sms.id}")
                    result_queue.put(False)
                else:
                    send_time = record.parse_fssj()
                    if send_time:
                        from django.utils import timezone
                        send_time = timezone.make_aware(send_time)
                    if send_time:
                        existing_history = DocumentQueryHistory.objects.filter(
                            credential_id=credential_id, case_number=record.ah, send_time=send_time
                        ).first()
                        if existing_history:
                            logger.info(f"🔄 文书有历史记录但未成功完成，重新处理: {record.ah}")
                            existing_history.delete()
                    logger.info(f"🆕 文书符合处理条件: {record.ah} - {record.fssj}")
                    result_queue.put(True)
            except Exception as e:
                logger.warning(f"检查文书处理历史失败: {e!s}")
                result_queue.put(True)

        thread = threading.Thread(target=do_check)
        thread.start()
        thread.join(timeout=10)
        if not result_queue.empty():
            return result_queue.get()
        logger.warning("检查文书处理历史超时，默认处理")
        return True

    def _sync_login_with_page(self, browser_service: Any, credential: Any, page: Page) -> str:
        """同步登录方法 - 使用传入的 page 进行登录"""
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

        court_service = CourtZxfwService(page=page, context=page.context, site_name=credential.site_name)
        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"登录尝试 {attempt}/{max_retries}")
                login_result = court_service.login(
                    account=credential.account, password=credential.password,
                    max_captcha_retries=3, save_debug=False,
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

    def query_and_download(
        self,
        credential_id: int,
        cutoff_time: datetime,
        tab: str = "pending",
        debug_mode: bool = True,
    ) -> DocumentQueryResult:
        """查询并下载文书（三级降级策略：API → Playwright）"""
        logger.info(
            f"开始查询文书: credential_id={credential_id}, cutoff_time={cutoff_time},"
            f" tab={tab}, debug_mode={debug_mode}"
        )
        api_result = self._try_api_approach(credential_id, cutoff_time)
        if api_result is not None:
            return api_result
        logger.info("🔄 API 方式失败，降级到 Playwright 方式")
        return self._query_via_playwright(
            credential_id=credential_id, cutoff_time=cutoff_time, tab=tab, debug_mode=debug_mode
        )

    def _try_api_approach(self, credential_id: int, cutoff_time: datetime) -> DocumentQueryResult | None:
        """尝试使用 API 方式查询文书"""
        logger.info("🚀 尝试 API 方式查询文书")
        try:
            token = self._acquire_token(credential_id)
            if not token:
                AutomationLogger.log_fallback_triggered(
                    from_method="api", to_method="playwright",
                    reason="Token 获取失败", credential_id=credential_id,
                )
                return None
            logger.info(f"✅ Token 获取成功: {token[:20]}...")
            result = self._query_via_api(token=token, cutoff_time=cutoff_time, credential_id=credential_id)
            AutomationLogger.log_document_query_statistics(
                total_found=result.total_found, processed_count=result.processed_count,
                skipped_count=result.skipped_count, failed_count=result.failed_count,
                query_method="api", credential_id=credential_id,
            )
            return result
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            AutomationLogger.log_fallback_triggered(
                from_method="api", to_method="playwright",
                reason=error_msg, error_type=error_type, credential_id=credential_id,
            )
            AutomationLogger.log_api_error_detail(
                api_name="document_query_api", error_type=error_type,
                error_message=error_msg, stack_trace=traceback.format_exc(),
            )
            return None

    def _acquire_token(self, credential_id: int) -> str | None:
        """获取 Token（委托给 DocumentDeliveryTokenService）"""
        return self.token_service.acquire_token(credential_id)

    def _acquire_token_via_service(self, site_name: str, credential_id: int) -> str | None:
        """通过 AutoTokenAcquisitionService 获取 Token（委托给 token_service）"""
        return self.token_service.acquire_token(credential_id)

    def _refresh_token_if_expired(self, credential_id: int, current_token: str) -> str | None:
        """检查 Token 是否过期，如果过期则刷新"""
        return self.token_service.refresh_token_if_expired(credential_id, current_token)

    def _try_api_after_login(self, token: str, cutoff_time: datetime, credential_id: int) -> DocumentQueryResult | None:
        """登录成功后尝试使用 API 方式获取文书列表"""
        logger.info("🚀 登录成功后尝试 API 方式获取文书列表")
        try:
            result = self._query_via_api(token=token, cutoff_time=cutoff_time, credential_id=credential_id)
            AutomationLogger.log_document_query_statistics(
                total_found=result.total_found, processed_count=result.processed_count,
                skipped_count=result.skipped_count, failed_count=result.failed_count,
                query_method="api_after_login", credential_id=credential_id,
            )
            return result
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            AutomationLogger.log_fallback_triggered(
                from_method="api_after_login", to_method="playwright_page",
                reason=error_msg, error_type=error_type, credential_id=credential_id,
            )
            AutomationLogger.log_api_error_detail(
                api_name="api_after_login", error_type=error_type,
                error_message=error_msg, stack_trace=traceback.format_exc(),
            )
            return None

    def _should_process(self, record: DocumentDeliveryRecord, cutoff_time: datetime, credential_id: int) -> bool:
        """判断是否需要处理该文书（Playwright 上下文）"""
        if record.send_time <= cutoff_time:
            logger.info(f"⏰ 文书时间 {record.send_time} 早于截止时间 {cutoff_time}，跳过")
            return False
        return self._check_not_processed_in_thread(credential_id, record)

    def _process_single_entry(
        self,
        page: Any,
        entry: Any,
        cutoff_time: datetime,
        credential_id: int,
        result: DocumentQueryResult,
    ) -> bool:
        """处理单个文书条目，返回是否需要继续翻页"""
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
            return bool(entry.send_time > cutoff_time)
        else:
            result.skipped_count += 1
            return False

    def _process_playwright_page(
        self,
        page: Any,
        cutoff_time: datetime,
        credential_id: int,
        result: DocumentQueryResult,
    ) -> None:
        """用 Playwright 页面方式分页处理文书"""
        page_num = 1
        while True:
            logger.info(f"处理第 {page_num} 页")
            entries = self._extract_document_entries(page)
            result.total_found += len(entries)
            if not entries:
                logger.info("当前页面没有文书条目，结束处理")
                break
            should_continue = False
            for entry in entries:
                logger.info(f"🔍 检查文书条目: {entry.case_number} - {entry.send_time}")
                if self._should_process(entry, cutoff_time, credential_id):
                    should_continue = self._process_single_entry(page, entry, cutoff_time, credential_id, result)
                else:
                    result.skipped_count += 1
                    if entry.send_time <= cutoff_time:
                        should_continue = False
                        break
            if not should_continue or not self._has_next_page(page):
                break
            self._go_to_next_page(page)
            page_num += 1

    def _process_document_entry(
        self, page: Page, entry: DocumentDeliveryRecord, credential_id: int
    ) -> DocumentProcessResult:
        """处理单个文书条目（Playwright 上下文）"""
        logger.info(f"开始处理文书: {entry.case_number} - {entry.send_time}")
        result = DocumentProcessResult(
            success=False, case_id=None, case_log_id=None,
            renamed_path=None, notification_sent=False, error_message=None,
        )
        try:
            file_path = self._download_document(page, entry)
            if not file_path:
                result.error_message = "文书下载失败"
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
            error_msg = f"处理文书失败: {e!s}"
            logger.error(error_msg)
            result.error_message = error_msg
        return result

    def _query_via_playwright(
        self, credential_id: int, cutoff_time: datetime, tab: str = "pending", debug_mode: bool = True
    ) -> DocumentQueryResult:
        """使用 Playwright 方式查询文书"""
        logger.info(f"Playwright 方式查询文书: credential_id={credential_id}")
        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        page = None
        try:
            organization_service = ServiceLocator.get_organization_service()
            credential = organization_service.get_credential_internal(credential_id)
            if not credential:
                error_msg = f"账号凭证不存在: {credential_id}"
                logger.error(error_msg)
                result.errors.append(error_msg)
                return result

            from apps.automation.services.scraper.core.browser_service import BrowserService
            browser_service = BrowserService()
            browser = browser_service.get_browser()
            page = browser.new_page()

            try:
                try:
                    token = self._sync_login_with_page(browser_service, credential, page)
                    logger.info(f"登录成功，获得token: {token[:20] if token else 'None'}...")
                except Exception as login_error:
                    error_msg = f"登录失败: {login_error!s}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    return result

                if token:
                    api_result = self._try_api_after_login(
                        token=token, cutoff_time=cutoff_time, credential_id=credential_id
                    )
                    if api_result is not None:
                        logger.info("✅ 登录后 API 方式成功，返回结果")
                        return api_result
                    logger.info("🔄 登录后 API 方式失败，继续使用 Playwright 页面方式")

                self._navigate_to_delivery_page(page, tab)
                self._process_playwright_page(page, cutoff_time, credential_id, result)

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
            total_found=result.total_found, processed_count=result.processed_count,
            skipped_count=result.skipped_count, failed_count=result.failed_count,
            query_method="playwright", credential_id=credential_id,
        )
        return result
