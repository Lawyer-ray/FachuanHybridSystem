"""
文书送达查询服务

负责页面抓取、下载和后续处理协调。
"""
import logging
import traceback
from datetime import datetime, timedelta
from typing import Optional, List, TYPE_CHECKING
from playwright.sync_api import Page

from apps.core.exceptions import ValidationException, NotFoundError
from apps.core.interfaces import ServiceLocator
from apps.automation.models import DocumentQueryHistory
from apps.automation.utils.logging import AutomationLogger
from .data_classes import (
    DocumentDeliveryRecord, DocumentQueryResult, DocumentProcessResult,
    DocumentRecord, DocumentListResponse
)
from .court_document_api_client import TokenExpiredError

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService
    from apps.core.interfaces import IAutoLoginService
    from .court_document_api_client import CourtDocumentApiClient
    from .token.document_delivery_token_service import DocumentDeliveryTokenService

logger = logging.getLogger("apps.automation")


class DocumentDeliveryService:
    """文书送达查询服务"""
    
    # 页面 URL
    DELIVERY_PAGE_URL = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/common/wssd/index"
    
    # 选择器常量 (使用精确 xpath)
    # 待查阅标签页
    PENDING_TAB_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[1]/uni-view/uni-view[1]/uni-view/uni-text"
    
    # 已查阅标签页
    REVIEWED_TAB_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[1]/uni-view/uni-view[2]/uni-view/uni-text"
    
    # 案号选择器（遍历获取所有案号）
    CASE_NUMBER_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view/uni-form/span/uni-view[1]/uni-view"
    
    # 发送时间选择器（遍历获取所有时间）
    SEND_TIME_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view/uni-form/span/uni-view[3]/uni-view"
    
    # 下载按钮选择器（遍历获取所有下载按钮）
    DOWNLOAD_BUTTON_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view[2]/uni-text[2]"
    
    # 翻页按钮
    NEXT_PAGE_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]/uni-view/uni-view/uni-view/uni-view[4]"
    
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
    ):
        """
        初始化文书送达服务
        
        Args:
            case_matcher: 案件匹配服务实例（可选，用于依赖注入）
            document_renamer: 文书重命名服务实例（可选，用于依赖注入）
            notification_service: 通知服务实例（可选，用于依赖注入）
            auto_login_service: 自动登录服务实例（可选，用于依赖注入）
            api_client: API 客户端实例（可选，用于依赖注入）
            token_service: Token 管理服务实例（可选，用于依赖注入）
            
        Requirements: 8.4, 3.2
        """
        self._case_matcher = case_matcher
        self._document_renamer = document_renamer
        self._notification_service = notification_service
        self._auto_login_service = auto_login_service
        self._api_client = api_client
        self._token_service = token_service
        
        logger.debug("DocumentDeliveryService 初始化完成")
    
    @property
    def case_matcher(self) -> "CaseMatcher":
        """延迟加载案件匹配服务"""
        if self._case_matcher is None:
            from apps.automation.services.sms.case_matcher import CaseMatcher
            self._case_matcher = CaseMatcher()
        return self._case_matcher
    
    @property
    def document_renamer(self) -> "DocumentRenamer":
        """延迟加载文书重命名服务"""
        if self._document_renamer is None:
            from apps.automation.services.sms.document_renamer import DocumentRenamer
            self._document_renamer = DocumentRenamer()
        return self._document_renamer
    
    @property
    def notification_service(self) -> "SMSNotificationService":
        """延迟加载通知服务"""
        if self._notification_service is None:
            from apps.automation.services.sms.sms_notification_service import SMSNotificationService
            self._notification_service = SMSNotificationService()
        return self._notification_service
    
    @property
    def auto_login_service(self) -> "IAutoLoginService":
        """延迟加载自动登录服务"""
        if self._auto_login_service is None:
            self._auto_login_service = ServiceLocator.get_auto_login_service()
        return self._auto_login_service
    
    @property
    def api_client(self) -> "CourtDocumentApiClient":
        """
        延迟加载 API 客户端
        
        Requirements: 8.4
        """
        if self._api_client is None:
            from .court_document_api_client import CourtDocumentApiClient
            self._api_client = CourtDocumentApiClient(
                auto_login_service=self.auto_login_service
            )
        return self._api_client
    
    @property
    def token_service(self) -> "DocumentDeliveryTokenService":
        """
        延迟加载 Token 管理服务
        
        统一使用 DocumentDeliveryTokenService 获取 Token
        Requirements: 3.2
        """
        if self._token_service is None:
            from .token.document_delivery_token_service import DocumentDeliveryTokenService
            self._token_service = DocumentDeliveryTokenService()
        return self._token_service
    
    # ==================== API 优先策略方法 ====================
    
    def _query_via_api(
        self,
        token: str,
        cutoff_time: datetime,
        credential_id: int
    ) -> DocumentQueryResult:
        """
        通过 API 查询文书
        
        流程：
        1. 调用 fetch_document_list 获取文书列表
        2. 根据 total 计算分页，遍历所有页
        3. 对每条记录检查 fssj 是否需要处理
        4. 调用 _process_document_via_api 处理文书
        
        Args:
            token: 认证令牌
            cutoff_time: 截止时间
            credential_id: 账号凭证 ID
            
        Returns:
            DocumentQueryResult: 查询结果
            
        Requirements: 1.1, 1.4, 3.4, 5.1
        """
        import math
        
        logger.info(f"开始 API 查询文书: cutoff_time={cutoff_time}")
        
        result = DocumentQueryResult(
            total_found=0,
            processed_count=0,
            skipped_count=0,
            failed_count=0,
            case_log_ids=[],
            errors=[]
        )
        
        page_size = 20
        page_num = 1
        
        try:
            # 获取第一页，确定总数
            first_response = self.api_client.fetch_document_list(
                token=token,
                page_num=page_num,
                page_size=page_size
            )
            
            total = first_response.total
            result.total_found = total
            
            logger.info(f"API 查询: 总文书数={total}")
            
            if total == 0:
                logger.info("没有文书需要处理")
                return result
            
            # 计算总页数
            total_pages = math.ceil(total / page_size)
            logger.info(f"分页计算: total={total}, page_size={page_size}, total_pages={total_pages}")
            
            # 处理第一页的文书
            self._process_document_page(
                documents=first_response.documents,
                token=token,
                cutoff_time=cutoff_time,
                credential_id=credential_id,
                result=result
            )
            
            # 遍历剩余页
            for page_num in range(2, total_pages + 1):
                logger.info(f"处理第 {page_num}/{total_pages} 页")
                
                try:
                    page_response = self.api_client.fetch_document_list(
                        token=token,
                        page_num=page_num,
                        page_size=page_size
                    )
                    
                    self._process_document_page(
                        documents=page_response.documents,
                        token=token,
                        cutoff_time=cutoff_time,
                        credential_id=credential_id,
                        result=result
                    )
                    
                except Exception as e:
                    error_msg = f"处理第 {page_num} 页失败: {str(e)}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    # 继续处理下一页
                    continue
            
        except Exception as e:
            error_msg = f"API 查询失败: {str(e)}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            raise  # 重新抛出异常，触发降级
        
        logger.info(f"API 查询完成: 发现={result.total_found}, 处理={result.processed_count}, "
                   f"跳过={result.skipped_count}, 失败={result.failed_count}")
        
        return result
    
    def _process_document_page(
        self,
        documents: List[DocumentRecord],
        token: str,
        cutoff_time: datetime,
        credential_id: int,
        result: DocumentQueryResult
    ) -> None:
        """
        处理一页文书记录
        
        Args:
            documents: 文书记录列表
            token: 认证令牌
            cutoff_time: 截止时间
            credential_id: 账号凭证 ID
            result: 查询结果（会被修改）
        """
        for record in documents:
            try:
                logger.info(f"🔍 检查文书: {record.ah} - {record.fssj}")
                
                # 检查是否需要处理
                if not self._should_process_api_document(record, cutoff_time, credential_id):
                    result.skipped_count += 1
                    logger.info(f"⏭️ 跳过文书: {record.ah}")
                    continue
                
                logger.info(f"✅ 开始处理文书: {record.ah}")
                
                # 处理文书
                process_result = self._process_document_via_api(
                    record=record,
                    token=token,
                    credential_id=credential_id
                )
                
                if process_result.success:
                    result.processed_count += 1
                    if process_result.case_log_id:
                        result.case_log_ids.append(process_result.case_log_id)
                    logger.info(f"✅ 文书处理成功: {record.ah}")
                else:
                    result.failed_count += 1
                    if process_result.error_message:
                        result.errors.append(process_result.error_message)
                    logger.warning(f"❌ 文书处理失败: {record.ah}, 错误: {process_result.error_message}")
                    
            except Exception as e:
                result.failed_count += 1
                error_msg = f"处理文书 {record.ah} 失败: {str(e)}"
                result.errors.append(error_msg)
                logger.error(error_msg)
    
    def _process_document_via_api(
        self,
        record: DocumentRecord,
        token: str,
        credential_id: int
    ) -> DocumentProcessResult:
        """
        通过 API 处理单个文书
        
        流程：
        1. 调用 api_client.fetch_document_details 获取下载链接
        2. 遍历文书列表，下载每个文书
        3. 调用现有的案件匹配、重命名、通知流程
        
        Args:
            record: 文书记录
            token: 认证令牌
            credential_id: 账号凭证 ID
            
        Returns:
            DocumentProcessResult: 处理结果
            
        Requirements: 2.1, 2.2, 2.3, 4.1, 4.2, 4.3
        """
        import tempfile
        from pathlib import Path
        
        logger.info(f"开始 API 处理文书: {record.ah}, sdbh={record.sdbh}")
        
        result = DocumentProcessResult(
            success=False,
            case_id=None,
            case_log_id=None,
            renamed_path=None,
            notification_sent=False,
            error_message=None
        )
        
        try:
            # 1. 获取文书详情（下载链接）
            details = self.api_client.fetch_document_details(
                token=token,
                sdbh=record.sdbh
            )
            
            if not details:
                result.error_message = f"未获取到文书详情: sdbh={record.sdbh}"
                logger.warning(result.error_message)
                return result
            
            logger.info(f"获取到 {len(details)} 个文书下载链接")
            
            # 2. 下载所有文书
            temp_dir = tempfile.mkdtemp(prefix="court_document_api_")
            downloaded_files = []
            
            for detail in details:
                if not detail.wjlj:
                    logger.warning(f"文书缺少下载链接: {detail.c_wsmc}")
                    continue
                
                # 构建文件名
                file_ext = detail.c_wjgs or "pdf"
                file_name = f"{detail.c_wsmc}.{file_ext}"
                save_path = Path(temp_dir) / file_name
                
                # 下载文书
                success = self.api_client.download_document(
                    url=detail.wjlj,
                    save_path=save_path
                )
                
                if success:
                    downloaded_files.append(str(save_path))
                    logger.info(f"文书下载成功: {file_name}")
                else:
                    logger.warning(f"文书下载失败: {file_name}")
            
            if not downloaded_files:
                result.error_message = "所有文书下载失败"
                logger.error(result.error_message)
                return result
            
            logger.info(f"成功下载 {len(downloaded_files)} 个文书")
            
            # 3. 创建 DocumentDeliveryRecord 用于后续处理
            send_time = record.parse_fssj()
            if send_time:
                from django.utils import timezone
                send_time = timezone.make_aware(send_time)
            else:
                from django.utils import timezone
                send_time = timezone.now()
            
            delivery_record = DocumentDeliveryRecord(
                case_number=record.ah,
                send_time=send_time,
                element_index=0,  # API 方式不需要元素索引
                document_name=record.wsmc,
                court_name=record.fymc
            )
            
            # 4. 在独立线程中执行后续处理（创建 CourtSMS、案件匹配、通知等）
            process_result = self._process_sms_in_thread(
                record=delivery_record,
                file_path=downloaded_files[0],
                extracted_files=downloaded_files,
                credential_id=credential_id
            )
            
            # 5. 记录查询历史
            self._record_query_history_in_thread(credential_id, delivery_record)
            
            result.success = process_result.get('success', False)
            result.case_id = process_result.get('case_id')
            result.case_log_id = process_result.get('case_log_id')
            result.renamed_path = process_result.get('renamed_path')
            result.notification_sent = process_result.get('notification_sent', False)
            result.error_message = process_result.get('error_message')
            
        except Exception as e:
            error_msg = f"API 处理文书失败: {str(e)}"
            logger.error(error_msg)
            result.error_message = error_msg
        
        return result
    
    def _should_process_api_document(
        self,
        record: DocumentRecord,
        cutoff_time: datetime,
        credential_id: int
    ) -> bool:
        """
        判断是否需要处理该 API 文书记录
        
        检查：
        1. fssj（发送时间）是否晚于 cutoff_time
        2. 是否已在 DocumentQueryHistory 中记录
        3. 对应的 CourtSMS 是否已 COMPLETED
        
        Args:
            record: API 文书记录
            cutoff_time: 截止时间
            credential_id: 账号凭证 ID
            
        Returns:
            是否需要处理
            
        Requirements: 3.1, 3.2, 3.3
        """
        # 1. 解析 fssj 字符串为 datetime
        send_time = record.parse_fssj()
        
        if send_time is None:
            logger.warning(f"无法解析发送时间: {record.fssj}, 默认处理")
            return True
        
        # 2. 比较 fssj 与 cutoff_time（需要处理时区）
        # cutoff_time 可能是 aware datetime，send_time 是 naive datetime
        from django.utils import timezone
        
        # 如果 cutoff_time 是 aware，将 send_time 也转为 aware
        if timezone.is_aware(cutoff_time):
            send_time = timezone.make_aware(send_time)
        
        if send_time <= cutoff_time:
            logger.info(f"⏰ 文书时间 {send_time} 早于截止时间 {cutoff_time}，跳过")
            return False
        
        # 3. 检查是否已经处理过（在独立线程中执行 ORM 操作）
        return self._check_api_document_not_processed(credential_id, record)
    
    def _check_api_document_not_processed(
        self,
        credential_id: int,
        record: DocumentRecord
    ) -> bool:
        """
        检查 API 文书是否已成功处理完成
        
        检查逻辑：
        1. 如果有查询历史记录，检查对应的 CourtSMS 是否已成功完成
        2. 如果 CourtSMS 状态为 COMPLETED，则跳过
        3. 如果 CourtSMS 状态为其他（失败、待处理等），则重新处理
        
        Args:
            credential_id: 账号凭证 ID
            record: API 文书记录
            
        Returns:
            是否需要处理（True=需要处理，False=已处理完成）
        """
        import threading
        import queue
        
        result_queue = queue.Queue()
        
        def do_check():
            try:
                from django.db import connection
                from apps.automation.models import CourtSMS, CourtSMSStatus
                
                # 确保数据库连接在新线程中可用
                connection.ensure_connection()
                
                # 检查是否有已成功完成的 CourtSMS 记录
                completed_sms = CourtSMS.objects.filter(
                    case_numbers__contains=[record.ah],
                    status=CourtSMSStatus.COMPLETED
                ).first()
                
                if completed_sms:
                    logger.info(f"🔄 文书已成功处理完成: {record.ah} - {record.fssj}, SMS ID={completed_sms.id}")
                    result_queue.put(False)
                else:
                    # 解析发送时间
                    send_time = record.parse_fssj()
                    if send_time:
                        from django.utils import timezone
                        send_time = timezone.make_aware(send_time)
                    
                    # 检查是否有未完成的记录，如果有则删除重新处理
                    if send_time:
                        existing_history = DocumentQueryHistory.objects.filter(
                            credential_id=credential_id,
                            case_number=record.ah,
                            send_time=send_time
                        ).first()
                        
                        if existing_history:
                            # 有历史记录但没有成功完成的 SMS，删除历史记录重新处理
                            logger.info(f"🔄 文书有历史记录但未成功完成，重新处理: {record.ah}")
                            existing_history.delete()
                    
                    logger.info(f"🆕 文书符合处理条件: {record.ah} - {record.fssj}")
                    result_queue.put(True)
                    
            except Exception as e:
                logger.warning(f"检查文书处理历史失败: {str(e)}")
                # 出错时默认处理
                result_queue.put(True)
        
        # 在独立线程中执行 ORM 操作
        thread = threading.Thread(target=do_check)
        thread.start()
        thread.join(timeout=10)  # 最多等待10秒
        
        if not result_queue.empty():
            return result_queue.get()
        
        # 超时时默认处理
        logger.warning("检查文书处理历史超时，默认处理")
        return True
    
    def _sync_login_with_page(self, browser_service, credential, page) -> str:
        """
        同步登录方法 - 使用传入的 page 进行登录
        
        直接使用 CourtZxfwService 进行登录，登录后 page 保持登录状态
        
        Args:
            browser_service: 浏览器服务实例
            credential: 账号凭证 DTO
            page: Playwright 页面实例
            
        Returns:
            登录成功后的 token
            
        Raises:
            Exception: 登录失败
        """
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
        
        # 创建法院服务实例（使用传入的 page）
        court_service = CourtZxfwService(
            page=page,
            context=page.context,
            site_name=credential.site_name
        )
        
        # 执行登录（最多重试3次）
        max_retries = 3
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"登录尝试 {attempt}/{max_retries}")
                
                login_result = court_service.login(
                    account=credential.account,
                    password=credential.password,
                    max_captcha_retries=3,
                    save_debug=False
                )
                
                if login_result.get("success"):
                    token = login_result.get("token")
                    if token:
                        return token
                    else:
                        raise Exception("登录成功但未获取到token")
                else:
                    raise Exception(f"登录失败: {login_result.get('message', '未知错误')}")
                    
            except Exception as e:
                last_error = e
                logger.warning(f"登录尝试 {attempt} 失败: {str(e)}")
                
                if attempt < max_retries:
                    import time
                    time.sleep(2)  # 等待2秒后重试
                
        raise last_error or Exception("登录失败，已达最大重试次数")
    
    def query_and_download(
        self,
        credential_id: int,
        cutoff_time: datetime,
        tab: str = "pending",  # "pending" | "reviewed"
        debug_mode: bool = True  # 调试模式：不关闭浏览器
    ) -> DocumentQueryResult:
        """
        查询并下载文书（三级降级策略）
        
        降级策略：
        1. 优先：直接 API 调用（使用 getSdListByZjhmAndAhdmNew）
        2. 次选：Playwright 浏览器自动化
        3. 回退：传统页面点击（已集成在 Playwright 方法中）
        
        Args:
            credential_id: 账号凭证ID
            cutoff_time: 截止时间，早于此时间的文书不处理
            tab: 查询标签页，"pending"=待查阅，"reviewed"=已查阅
            debug_mode: 调试模式，为 True 时不关闭浏览器
            
        Returns:
            DocumentQueryResult: 查询结果
            
        Requirements: 1.3, 2.4, 5.3, 6.3
        """
        logger.info(f"开始查询文书: credential_id={credential_id}, cutoff_time={cutoff_time}, tab={tab}, debug_mode={debug_mode}")
        
        # 1. 优先尝试 API 方式
        api_result = self._try_api_approach(credential_id, cutoff_time)
        if api_result is not None:
            return api_result
        
        # 2. API 失败，降级到 Playwright 方式
        logger.info("🔄 API 方式失败，降级到 Playwright 方式")
        return self._query_via_playwright(
            credential_id=credential_id,
            cutoff_time=cutoff_time,
            tab=tab,
            debug_mode=debug_mode
        )
    
    def _try_api_approach(
        self,
        credential_id: int,
        cutoff_time: datetime
    ) -> Optional[DocumentQueryResult]:
        """
        尝试使用 API 方式查询文书
        
        Args:
            credential_id: 账号凭证 ID
            cutoff_time: 截止时间
            
        Returns:
            查询结果，如果 API 方式失败则返回 None
            
        Requirements: 1.3, 5.1, 5.2, 5.3, 5.4, 7.3, 7.4
        """
        logger.info("🚀 尝试 API 方式查询文书")
        
        try:
            # 获取 Token
            token = self._acquire_token(credential_id)
            if not token:
                # 记录降级日志
                AutomationLogger.log_fallback_triggered(
                    from_method="api",
                    to_method="playwright",
                    reason="Token 获取失败",
                    credential_id=credential_id
                )
                return None
            
            logger.info(f"✅ Token 获取成功: {token[:20]}...")
            
            # 调用 API 查询
            result = self._query_via_api(
                token=token,
                cutoff_time=cutoff_time,
                credential_id=credential_id
            )
            
            # 记录查询统计
            AutomationLogger.log_document_query_statistics(
                total_found=result.total_found,
                processed_count=result.processed_count,
                skipped_count=result.skipped_count,
                failed_count=result.failed_count,
                query_method="api",
                credential_id=credential_id
            )
            
            return result
            
        except Exception as e:
            # 记录详细错误信息
            error_type = type(e).__name__
            error_msg = str(e)
            
            # 记录降级日志
            AutomationLogger.log_fallback_triggered(
                from_method="api",
                to_method="playwright",
                reason=error_msg,
                error_type=error_type,
                credential_id=credential_id
            )
            
            # 记录详细错误信息（包含堆栈跟踪）
            AutomationLogger.log_api_error_detail(
                api_name="document_query_api",
                error_type=error_type,
                error_message=error_msg,
                stack_trace=traceback.format_exc()
            )
            
            return None
    
    def _acquire_token(self, credential_id: int) -> Optional[str]:
        """
        获取 Token（带缓存和自动刷新）
        
        委托给 DocumentDeliveryTokenService 执行，统一 Token 获取逻辑
        
        Args:
            credential_id: 账号凭证 ID
            
        Returns:
            Token 字符串，获取失败返回 None
            
        Requirements: 3.2, 5.1, 5.2, 5.3, 5.4
        """
        return self.token_service.acquire_token(credential_id)
    
    def _acquire_token_via_service(
        self,
        site_name: str,
        credential_id: int
    ) -> Optional[str]:
        """
        通过 AutoTokenAcquisitionService 获取 Token
        
        委托给 DocumentDeliveryTokenService 执行，统一 Token 获取逻辑
        
        Args:
            site_name: 网站名称
            credential_id: 凭证 ID
            
        Returns:
            Token 字符串，获取失败返回 None
            
        Requirements: 3.2, 5.1, 5.2
        """
        # 直接使用 token_service 获取 Token
        return self.token_service.acquire_token(credential_id)
    
    def _refresh_token_if_expired(
        self,
        credential_id: int,
        current_token: str
    ) -> Optional[str]:
        """
        检查 Token 是否过期，如果过期则刷新
        
        委托给 DocumentDeliveryTokenService 执行，统一 Token 获取逻辑
        
        Args:
            credential_id: 凭证 ID
            current_token: 当前 Token
            
        Returns:
            有效的 Token（可能是原 Token 或新获取的 Token），
            刷新失败返回 None
            
        Requirements: 3.2, 5.2, 5.4
        """
        return self.token_service.refresh_token_if_expired(credential_id, current_token)
    
    def _try_api_after_login(
        self,
        token: str,
        cutoff_time: datetime,
        credential_id: int
    ) -> Optional[DocumentQueryResult]:
        """
        登录成功后尝试使用 API 方式获取文书列表
        
        在 Playwright 登录成功获得 token 后，优先尝试 API 方式。
        如果 API 成功则返回结果，失败则返回 None 让调用方继续用 Playwright。
        
        Args:
            token: 登录成功后获得的 token
            cutoff_time: 截止时间
            credential_id: 凭证 ID
            
        Returns:
            查询结果，如果 API 失败则返回 None
            
        Requirements: 1.3, 5.1, 5.3
        """
        logger.info("🚀 登录成功后尝试 API 方式获取文书列表")
        
        try:
            # 调用 API 查询
            result = self._query_via_api(
                token=token,
                cutoff_time=cutoff_time,
                credential_id=credential_id
            )
            
            # 记录查询统计
            AutomationLogger.log_document_query_statistics(
                total_found=result.total_found,
                processed_count=result.processed_count,
                skipped_count=result.skipped_count,
                failed_count=result.failed_count,
                query_method="api_after_login",
                credential_id=credential_id
            )
            
            return result
            
        except Exception as e:
            # 记录详细错误信息
            error_type = type(e).__name__
            error_msg = str(e)
            
            # 记录降级日志
            AutomationLogger.log_fallback_triggered(
                from_method="api_after_login",
                to_method="playwright_page",
                reason=error_msg,
                error_type=error_type,
                credential_id=credential_id
            )
            
            # 记录详细错误信息（包含堆栈跟踪）
            AutomationLogger.log_api_error_detail(
                api_name="api_after_login",
                error_type=error_type,
                error_message=error_msg,
                stack_trace=traceback.format_exc()
            )
            
            return None
    
    def _query_via_playwright(
        self,
        credential_id: int,
        cutoff_time: datetime,
        tab: str = "pending",
        debug_mode: bool = True
    ) -> DocumentQueryResult:
        """
        使用 Playwright 方式查询文书（原有逻辑）
        
        Args:
            credential_id: 账号凭证ID
            cutoff_time: 截止时间
            tab: 查询标签页
            debug_mode: 调试模式
            
        Returns:
            DocumentQueryResult: 查询结果
        """
        logger.info(f"Playwright 方式查询文书: credential_id={credential_id}")
        
        result = DocumentQueryResult(
            total_found=0,
            processed_count=0,
            skipped_count=0,
            failed_count=0,
            case_log_ids=[],
            errors=[]
        )
        
        page = None
        
        try:
            # 获取凭证信息
            organization_service = ServiceLocator.get_organization_service()
            credential = organization_service.get_credential_internal(credential_id)
            
            if not credential:
                error_msg = f"账号凭证不存在: {credential_id}"
                logger.error(error_msg)
                result.errors.append(error_msg)
                return result
            
            # 使用同步的浏览器服务
            from apps.automation.services.scraper.core.browser_service import BrowserService
            browser_service = BrowserService()
            
            # 获取同步浏览器实例
            browser = browser_service.get_browser()
            page = browser.new_page()
            
            try:
                # 在同一个 page 上登录，保持登录状态
                try:
                    token = self._sync_login_with_page(browser_service, credential, page)
                    logger.info(f"登录成功，获得token: {token[:20] if token else 'None'}...")
                    
                except Exception as login_error:
                    error_msg = f"登录失败: {str(login_error)}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    return result
                
                # 登录成功后，优先尝试 API 方式获取文书列表
                # 如果 API 成功，直接返回结果；如果失败，继续用 Playwright 页面方式
                if token:
                    api_result = self._try_api_after_login(
                        token=token,
                        cutoff_time=cutoff_time,
                        credential_id=credential_id
                    )
                    if api_result is not None:
                        logger.info("✅ 登录后 API 方式成功，返回结果")
                        return api_result
                    else:
                        logger.info("🔄 登录后 API 方式失败，继续使用 Playwright 页面方式")
                
                # API 失败或无 token，继续用 Playwright 页面方式
                # 导航到文书送达页面（同一个 page，保持登录状态）
                self._navigate_to_delivery_page(page, tab)
                
                # 分页处理文书
                page_num = 1
                while True:
                    logger.info(f"处理第 {page_num} 页")
                    
                    # 提取当前页面的文书条目
                    entries = self._extract_document_entries(page)
                    result.total_found += len(entries)
                    
                    if not entries:
                        logger.info("当前页面没有文书条目，结束处理")
                        break
                    
                    # 检查是否需要继续翻页
                    should_continue = False
                    
                    # 处理每个文书条目
                    for entry in entries:
                        logger.info(f"🔍 检查文书条目: {entry.case_number} - {entry.send_time}")
                        logger.info(f"📅 截止时间: {cutoff_time}")
                        
                        if self._should_process(entry, cutoff_time, credential_id):
                            logger.info(f"✅ 开始处理文书: {entry.case_number}")
                            # 处理文书
                            process_result = self._process_document_entry(page, entry, credential_id)
                            
                            if process_result.success:
                                result.processed_count += 1
                                if process_result.case_log_id:
                                    result.case_log_ids.append(process_result.case_log_id)
                                logger.info(f"✅ 文书处理成功: {entry.case_number}")
                            else:
                                result.failed_count += 1
                                if process_result.error_message:
                                    result.errors.append(process_result.error_message)
                                logger.warning(f"❌ 文书处理失败: {entry.case_number}, 错误: {process_result.error_message}")
                            
                            # 如果文书时间晚于截止时间，需要继续翻页
                            if entry.send_time > cutoff_time:
                                should_continue = True
                        else:
                            result.skipped_count += 1
                            logger.info(f"⏭️ 跳过文书: {entry.case_number} - {entry.send_time}")
                            
                            # 如果文书时间早于或等于截止时间，停止翻页
                            if entry.send_time <= cutoff_time:
                                logger.info(f"文书时间 {entry.send_time} 早于截止时间 {cutoff_time}，停止翻页")
                                should_continue = False
                                break
                    
                    # 检查是否需要翻页
                    if not should_continue or not self._has_next_page(page):
                        break
                    
                    # 翻到下一页
                    self._go_to_next_page(page)
                    page_num += 1
                
            finally:
                # 调试模式下不关闭浏览器，方便调试
                if not debug_mode:
                    try:
                        page.close()
                    except Exception as e:
                        logger.warning(f"关闭页面失败: {str(e)}")
                else:
                    logger.info("🔍 调试模式：浏览器保持打开，请手动检查页面状态")
                
        except Exception as e:
            error_msg = f"查询文书失败: {str(e)}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            
            # 记录详细错误信息
            AutomationLogger.log_api_error_detail(
                api_name="playwright_document_query",
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc()
            )
        
        # 记录查询统计
        AutomationLogger.log_document_query_statistics(
            total_found=result.total_found,
            processed_count=result.processed_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count,
            query_method="playwright",
            credential_id=credential_id
        )
        
        return result
    
    def _navigate_to_delivery_page(self, page: Page, tab: str) -> None:
        """导航到文书送达页面"""
        logger.info(f"导航到文书送达页面: {self.DELIVERY_PAGE_URL}")
        
        # 访问文书送达页面
        page.goto(self.DELIVERY_PAGE_URL)
        page.wait_for_load_state("networkidle")
        
        # 等待页面完全加载
        page.wait_for_timeout(self.PAGE_LOAD_WAIT)
        
        # 切换标签页
        tab_selector = self.REVIEWED_TAB_SELECTOR if tab == "reviewed" else self.PENDING_TAB_SELECTOR
        tab_name = "已查阅" if tab == "reviewed" else "待查阅"
        
        logger.info(f"切换到{tab_name}标签页")
        try:
            tab_element = page.locator(tab_selector)
            tab_element.wait_for(state="visible", timeout=5000)
            tab_element.click()
            page.wait_for_timeout(self.PAGE_LOAD_WAIT)
            logger.info(f"成功点击{tab_name}标签页")
        except Exception as e:
            logger.warning(f"切换到{tab_name}标签页失败: {str(e)}")
    
    def _extract_document_entries(self, page: Page) -> List[DocumentDeliveryRecord]:
        """从页面提取文书条目 - 使用精确 XPath 遍历"""
        logger.info("开始提取文书条目")
        
        entries = []
        
        try:
            # 等待页面加载
            page.wait_for_timeout(2000)
            
            # 使用你提供的精确 XPath 获取所有案号
            case_number_elements = page.locator(self.CASE_NUMBER_SELECTOR).all()
            logger.info(f"找到 {len(case_number_elements)} 个案号元素")
            
            # 使用你提供的精确 XPath 获取所有发送时间
            send_time_elements = page.locator(self.SEND_TIME_SELECTOR).all()
            logger.info(f"找到 {len(send_time_elements)} 个时间元素")
            
            # 确保案号和时间数量一致
            if len(case_number_elements) != len(send_time_elements):
                logger.warning(f"案号数量({len(case_number_elements)})与时间数量({len(send_time_elements)})不匹配")
                # 取较小的数量
                count = min(len(case_number_elements), len(send_time_elements))
            else:
                count = len(case_number_elements)
            
            logger.info(f"将处理 {count} 个文书条目")
            
            # 遍历提取每个文书条目
            for index in range(count):
                try:
                    # 提取案号
                    case_number = None
                    if index < len(case_number_elements):
                        case_number_text = case_number_elements[index].inner_text()
                        case_number = case_number_text.strip() if case_number_text else None
                        logger.info(f"条目 {index} 案号: {case_number}")
                        
                        # 过滤掉标签文本
                        if case_number and case_number in ["案号", "案件编号"]:
                            case_number = None
                            logger.debug(f"条目 {index} 跳过案号标签文本")
                    
                    # 提取发送时间
                    send_time = None
                    send_time_str = None
                    if index < len(send_time_elements):
                        send_time_text = send_time_elements[index].inner_text()
                        send_time_str = send_time_text.strip() if send_time_text else None
                        logger.info(f"条目 {index} 时间文本: {send_time_str}")
                        
                        # 过滤掉标签文本，只处理实际的时间格式
                        if send_time_str and send_time_str != "发送时间":
                            # 检查是否符合时间格式 2025-12-16 10:58:52
                            import re
                            time_pattern = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$'
                            if re.match(time_pattern, send_time_str):
                                try:
                                    # 解析时间并添加时区信息
                                    naive_time = datetime.strptime(send_time_str, "%Y-%m-%d %H:%M:%S")
                                    from django.utils import timezone
                                    send_time = timezone.make_aware(naive_time)
                                    logger.info(f"条目 {index} 时间解析成功: {send_time_str} -> {send_time}")
                                except ValueError as e:
                                    logger.warning(f"条目 {index} 时间解析失败: {send_time_str}, 错误: {str(e)}")
                            else:
                                logger.debug(f"条目 {index} 时间格式不匹配: {send_time_str}")
                        else:
                            logger.debug(f"条目 {index} 跳过标签文本: {send_time_str}")
                    
                    # 创建文书记录
                    if case_number and send_time:
                        entry = DocumentDeliveryRecord(
                            case_number=case_number,
                            send_time=send_time,
                            element_index=index
                        )
                        entries.append(entry)
                        logger.info(f"✅ 提取文书条目: {entry.case_number} - {entry.send_time}")
                    else:
                        logger.debug(f"❌ 条目 {index} 数据不完整: 案号={case_number}, 时间={send_time_str}")
                    
                except Exception as e:
                    logger.warning(f"提取第 {index} 个文书条目失败: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"提取文书条目失败: {str(e)}")
        
        logger.info(f"成功提取 {len(entries)} 个文书条目")
        return entries
    
    def _parse_document_text(self, text: str) -> tuple:
        """
        从文书条目文本中解析案号和时间
        
        Args:
            text: 文书条目的文本内容
            
        Returns:
            (case_number, send_time) 元组
        """
        import re
        
        case_number = None
        send_time = None
        
        # 提取案号 - 匹配常见的案号格式
        # 例如: (2024)粤0106民初12345号
        case_patterns = [
            r'\(?\d{4}\)?[^\d\s]+\d+号',  # (2024)粤0106民初12345号
            r'[\(（]\d{4}[\)）][^\d\s]+\d+号',  # （2024）粤0106民初12345号
        ]
        
        for pattern in case_patterns:
            match = re.search(pattern, text)
            if match:
                case_number = match.group()
                break
        
        # 提取时间 - 匹配常见的时间格式
        time_patterns = [
            (r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', "%Y-%m-%d %H:%M:%S"),
            (r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', "%Y-%m-%d %H:%M"),
            (r'\d{4}-\d{2}-\d{2}', "%Y-%m-%d"),
            (r'\d{4}/\d{2}/\d{2}', "%Y/%m/%d"),
        ]
        
        for pattern, fmt in time_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    send_time = datetime.strptime(match.group(), fmt)
                    break
                except ValueError:
                    continue
        
        return case_number, send_time
    
    def _should_process(
        self, 
        record: DocumentDeliveryRecord, 
        cutoff_time: datetime,
        credential_id: int
    ) -> bool:
        """
        判断是否需要处理该文书
        
        注意：此方法在 Playwright 上下文中调用，ORM 操作需要在独立线程中执行
        """
        
        # 检查时间过滤
        if record.send_time <= cutoff_time:
            logger.info(f"⏰ 文书时间 {record.send_time} 早于截止时间 {cutoff_time}，跳过")
            return False
        
        # 在独立线程中检查是否已经处理过
        return self._check_not_processed_in_thread(credential_id, record)
    
    def _check_not_processed_in_thread(self, credential_id: int, record: DocumentDeliveryRecord) -> bool:
        """
        在独立线程中检查文书是否已成功处理完成，避免异步上下文问题
        
        检查逻辑：
        1. 如果有查询历史记录，检查对应的 CourtSMS 是否已成功完成
        2. 如果 CourtSMS 状态为 COMPLETED，则跳过
        3. 如果 CourtSMS 状态为其他（失败、待处理等），则重新处理
        """
        import threading
        import queue
        
        result_queue = queue.Queue()
        
        def do_check():
            try:
                from django.db import connection
                from apps.automation.models import CourtSMS, CourtSMSStatus
                
                # 确保数据库连接在新线程中可用
                connection.ensure_connection()
                
                # 检查是否有已成功完成的 CourtSMS 记录
                completed_sms = CourtSMS.objects.filter(
                    case_numbers__contains=[record.case_number],
                    status=CourtSMSStatus.COMPLETED
                ).first()
                
                if completed_sms:
                    logger.info(f"🔄 文书已成功处理完成: {record.case_number} - {record.send_time}, SMS ID={completed_sms.id}")
                    result_queue.put(False)
                else:
                    # 检查是否有未完成的记录，如果有则删除重新处理
                    existing_history = DocumentQueryHistory.objects.filter(
                        credential_id=credential_id,
                        case_number=record.case_number,
                        send_time=record.send_time
                    ).first()
                    
                    if existing_history:
                        # 有历史记录但没有成功完成的 SMS，删除历史记录重新处理
                        logger.info(f"🔄 文书有历史记录但未成功完成，重新处理: {record.case_number}")
                        existing_history.delete()
                    
                    logger.info(f"🆕 文书符合处理条件: {record.case_number} - {record.send_time}")
                    result_queue.put(True)
                    
            except Exception as e:
                logger.warning(f"检查文书处理历史失败: {str(e)}")
                # 出错时默认处理
                result_queue.put(True)
        
        # 在独立线程中执行 ORM 操作
        thread = threading.Thread(target=do_check)
        thread.start()
        thread.join(timeout=10)  # 最多等待10秒
        
        if not result_queue.empty():
            return result_queue.get()
        
        # 超时时默认处理
        logger.warning("检查文书处理历史超时，默认处理")
        return True
    
    def _process_document_entry(
        self,
        page: Page,
        entry: DocumentDeliveryRecord,
        credential_id: int
    ) -> DocumentProcessResult:
        """
        处理单个文书条目
        
        注意：此方法在 Playwright 上下文中调用，ORM 操作需要在独立线程中执行
        """
        logger.info(f"开始处理文书: {entry.case_number} - {entry.send_time}")
        
        result = DocumentProcessResult(
            success=False,
            case_id=None,
            case_log_id=None,
            renamed_path=None,
            notification_sent=False,
            error_message=None
        )
        
        try:
            # 下载文书（Playwright 操作）
            file_path = self._download_document(page, entry)
            if not file_path:
                result.error_message = "文书下载失败"
                return result
            
            # 处理下载的文书（纯文件操作，不涉及 ORM）
            process_result = self._process_downloaded_document(file_path, entry, credential_id)
            
            # 在独立线程中执行 ORM 操作，避免异步上下文问题
            self._record_query_history_in_thread(credential_id, entry)
            
            result.success = process_result.success
            result.case_id = process_result.case_id
            result.case_log_id = process_result.case_log_id
            result.renamed_path = process_result.renamed_path
            result.notification_sent = process_result.notification_sent
            result.error_message = process_result.error_message
            
        except Exception as e:
            error_msg = f"处理文书失败: {str(e)}"
            logger.error(error_msg)
            result.error_message = error_msg
        
        return result
    
    def _record_query_history_in_thread(self, credential_id: int, entry: DocumentDeliveryRecord) -> None:
        """在独立线程中记录查询历史，避免异步上下文问题"""
        import threading
        
        def do_record():
            try:
                from django.db import transaction, connection
                from django.utils import timezone
                
                # 确保数据库连接在新线程中可用
                connection.ensure_connection()
                
                with transaction.atomic():
                    DocumentQueryHistory.objects.get_or_create(
                        credential_id=credential_id,
                        case_number=entry.case_number,
                        send_time=entry.send_time,
                        defaults={
                            'queried_at': timezone.now()
                        }
                    )
                logger.debug(f"记录查询历史成功: {entry.case_number} - {entry.send_time}")
            except Exception as e:
                logger.warning(f"记录查询历史失败: {str(e)}")
        
        # 在独立线程中执行 ORM 操作
        thread = threading.Thread(target=do_record)
        thread.start()
        thread.join(timeout=10)  # 最多等待10秒
    
    def _download_document(self, page: Page, entry: DocumentDeliveryRecord) -> Optional[str]:
        """
        点击下载按钮下载文书 - 使用精确 XPath
        
        Returns:
            下载的文件路径
        """
        logger.info(f"开始下载文书: {entry.case_number}")
        
        try:
            # 使用你提供的精确 XPath 获取所有下载按钮
            download_buttons = page.locator(self.DOWNLOAD_BUTTON_SELECTOR).all()
            logger.info(f"找到 {len(download_buttons)} 个下载按钮")
            
            if entry.element_index >= len(download_buttons):
                logger.error(f"下载按钮索引超出范围: {entry.element_index} >= {len(download_buttons)}")
                return None
            
            # 获取对应的下载按钮
            download_button = download_buttons[entry.element_index]
            
            if not download_button.is_visible():
                logger.error(f"下载按钮不可见: {entry.case_number}")
                return None
            
            logger.info(f"点击第 {entry.element_index} 个下载按钮")
            
            # 设置下载监听
            with page.expect_download() as download_info:
                download_button.click()
            
            download = download_info.value
            
            # 保存文件
            import os
            import tempfile
            
            # 创建临时目录
            temp_dir = tempfile.mkdtemp(prefix="court_document_")
            file_path = os.path.join(temp_dir, download.suggested_filename or f"{entry.case_number}.pdf")
            
            download.save_as(file_path)
            
            logger.info(f"文书下载成功: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"下载文书失败: {str(e)}")
            return None
    
    def _process_downloaded_document(
        self,
        file_path: str,
        record: DocumentDeliveryRecord,
        credential_id: int
    ) -> DocumentProcessResult:
        """
        处理下载的文书 - 解压文件后在独立线程中执行后续处理
        
        注意：此方法在 Playwright 上下文中调用，ORM 操作需要在独立线程中执行
        """
        logger.info(f"开始处理下载的文书: {file_path}")
        
        result = DocumentProcessResult(
            success=False,
            case_id=None,
            case_log_id=None,
            renamed_path=None,
            notification_sent=False,
            error_message=None
        )
        
        try:
            # 处理 ZIP 压缩包（纯文件操作，不涉及 ORM）
            extracted_files = self._extract_zip_if_needed(file_path)
            
            logger.info(f"文书下载完成: 案号={record.case_number}, 文件={file_path}")
            if extracted_files:
                logger.info(f"ZIP 解压完成: {len(extracted_files)} 个文件")
                for i, extracted_file in enumerate(extracted_files):
                    logger.info(f"  文件 {i+1}: {extracted_file}")
            
            # 在独立线程中执行后续处理（创建 CourtSMS、案件匹配、通知等）
            process_result = self._process_sms_in_thread(
                record=record,
                file_path=file_path,
                extracted_files=extracted_files or [file_path],
                credential_id=credential_id
            )
            
            result.success = process_result.get('success', False)
            result.case_id = process_result.get('case_id')
            result.case_log_id = process_result.get('case_log_id')
            result.renamed_path = process_result.get('renamed_path', file_path)
            result.notification_sent = process_result.get('notification_sent', False)
            result.error_message = process_result.get('error_message')
            
        except Exception as e:
            error_msg = f"处理下载文书失败: {str(e)}"
            logger.error(error_msg)
            result.error_message = error_msg
        
        return result
    
    def _process_sms_in_thread(
        self,
        record: DocumentDeliveryRecord,
        file_path: str,
        extracted_files: List[str],
        credential_id: int
    ) -> dict:
        """
        在独立线程中执行 SMS 处理流程，避免异步上下文问题
        
        流程：创建 CourtSMS -> 案件匹配 -> 重命名文书 -> 发送通知
        """
        import threading
        import queue
        
        result_queue = queue.Queue()
        
        def do_process():
            try:
                from django.db import connection
                from django.utils import timezone
                from apps.automation.models import CourtSMS, CourtSMSStatus
                
                # 确保数据库连接在新线程中可用
                connection.ensure_connection()
                
                result = {
                    'success': False,
                    'case_id': None,
                    'case_log_id': None,
                    'renamed_path': file_path,
                    'notification_sent': False,
                    'error_message': None
                }
                
                # 1. 创建 CourtSMS 记录
                logger.info(f"创建 CourtSMS 记录: 案号={record.case_number}")
                sms = CourtSMS.objects.create(
                    content=f"文书送达自动下载: {record.case_number}",
                    received_at=record.send_time,
                    status=CourtSMSStatus.MATCHING,
                    case_numbers=[record.case_number],
                    sms_type='document_delivery'
                )
                logger.info(f"CourtSMS 创建成功: ID={sms.id}")
                
                # 2. 案件匹配 - 先通过案号，失败后从文书提取当事人匹配
                logger.info(f"开始案件匹配: SMS ID={sms.id}, 案号={record.case_number}")
                matched_case = self._match_case_by_number(record.case_number)
                
                # 如果案号匹配失败，尝试从文书中提取当事人进行匹配
                if not matched_case:
                    logger.info(f"案号匹配失败，尝试从文书中提取当事人进行匹配")
                    matched_case = self._match_case_by_document_parties(extracted_files)
                
                if matched_case:
                    # 直接设置外键 ID，避免跨模块 Model 导入
                    sms.case_id = matched_case.id
                    sms.status = CourtSMSStatus.RENAMING
                    sms.save()
                    result['case_id'] = matched_case.id
                    logger.info(f"案件匹配成功: SMS ID={sms.id}, Case ID={matched_case.id}")
                    
                    # 3. 将案号写入案件（如果案件还没有这个案号）
                    self._sync_case_number_to_case(matched_case.id, record.case_number)
                    
                    # 4. 重命名文书并添加到案件日志
                    renamed_files, case_log_id = self._rename_and_attach_documents(
                        sms=sms,
                        case=case,
                        extracted_files=extracted_files
                    )
                    
                    if renamed_files:
                        result['renamed_path'] = renamed_files[0] if renamed_files else file_path
                    if case_log_id:
                        result['case_log_id'] = case_log_id
                        sms.case_log_id = case_log_id
                    
                    sms.status = CourtSMSStatus.NOTIFYING
                    sms.save()
                    
                    # 5. 发送通知
                    notification_sent = self._send_notification(sms, renamed_files or extracted_files)
                    result['notification_sent'] = notification_sent
                    
                    if notification_sent:
                        sms.status = CourtSMSStatus.COMPLETED
                        sms.feishu_sent_at = timezone.now()
                        logger.info(f"通知发送成功: SMS ID={sms.id}")
                    else:
                        sms.status = CourtSMSStatus.FAILED
                        sms.error_message = "通知发送失败"
                        logger.warning(f"通知发送失败: SMS ID={sms.id}")
                    
                    sms.save()
                    result['success'] = True
                    
                else:
                    # 未匹配到案件，标记为待人工处理
                    sms.status = CourtSMSStatus.PENDING_MANUAL
                    sms.error_message = f"未能匹配到案件: {record.case_number}"
                    sms.save()
                    result['error_message'] = sms.error_message
                    result['success'] = True  # 下载成功，只是匹配失败
                    logger.warning(f"案件匹配失败，待人工处理: SMS ID={sms.id}")
                
                result_queue.put(result)
                
            except Exception as e:
                logger.error(f"SMS 处理失败: {str(e)}")
                result_queue.put({
                    'success': False,
                    'error_message': str(e)
                })
        
        # 在独立线程中执行
        thread = threading.Thread(target=do_process)
        thread.start()
        thread.join(timeout=60)  # 最多等待60秒
        
        if not result_queue.empty():
            return result_queue.get()
        
        return {'success': False, 'error_message': 'SMS 处理超时'}
    
    def _match_case_by_number(self, case_number: str):
        """
        通过案号匹配案件
        
        委托给 CaseMatcher 执行，统一案件匹配逻辑
        Requirements: 3.1
        """
        return self.case_matcher.match_by_case_number([case_number])
    
    def _rename_and_attach_documents(
        self,
        sms,
        case,
        extracted_files: List[str]
    ) -> tuple:
        """重命名文书并添加到案件日志"""
        from datetime import date
        
        renamed_files = []
        case_log_id = None
        
        try:
            # 使用 DocumentRenamer 重命名文书
            for file_path in extracted_files:
                try:
                    renamed_path = self.document_renamer.rename(
                        document_path=file_path,
                        case_name=case.name,
                        received_date=date.today()
                    )
                    if renamed_path:
                        renamed_files.append(renamed_path)
                        logger.info(f"文书重命名成功: {file_path} -> {renamed_path}")
                    else:
                        renamed_files.append(file_path)
                except Exception as e:
                    logger.warning(f"文书重命名失败: {file_path}, 错误: {str(e)}")
                    renamed_files.append(file_path)
            
            # 创建案件日志
            if renamed_files:
                case_log_service = ServiceLocator.get_caselog_service()
                file_names = [f.split('/')[-1] for f in renamed_files]
                case_log = case_log_service.create_log(
                    case_id=case.id,
                    content=f"文书送达自动下载: {', '.join(file_names)}",
                    user=None  # 系统自动操作
                )
                if case_log:
                    case_log_id = case_log.id
                    logger.info(f"案件日志创建成功: CaseLog ID={case_log_id}")
                    
                    # 添加附件 - 使用 Django 文件上传方式
                    from django.core.files.uploadedfile import SimpleUploadedFile
                    import os
                    
                    for file_path in renamed_files:
                        try:
                            if os.path.exists(file_path):
                                with open(file_path, 'rb') as f:
                                    file_content = f.read()
                                file_name = os.path.basename(file_path)
                                uploaded_file = SimpleUploadedFile(
                                    name=file_name,
                                    content=file_content,
                                    content_type='application/octet-stream'
                                )
                                case_log_service.upload_attachments(
                                    log_id=case_log.id,
                                    files=[uploaded_file],
                                    user=None,
                                    perm_open_access=True  # 系统操作，跳过权限检查
                                )
                                logger.info(f"附件上传成功: {file_name}")
                        except Exception as e:
                            logger.warning(f"添加附件失败: {file_path}, 错误: {str(e)}")
                    
        except Exception as e:
            logger.error(f"重命名和附件处理失败: {str(e)}")
        
        return renamed_files, case_log_id
    
    def _send_notification(self, sms, document_paths: List[str]) -> bool:
        """发送通知"""
        try:
            if not sms.case:
                logger.warning(f"SMS {sms.id} 未绑定案件，无法发送通知")
                return False
            
            return self.notification_service.send_case_chat_notification(sms, document_paths)
        except Exception as e:
            logger.error(f"发送通知失败: {str(e)}")
            return False
    
    def _extract_zip_if_needed(self, file_path: str) -> Optional[List[str]]:
        """
        如果是 ZIP 文件则解压，返回解压后的文件列表
        
        Args:
            file_path: 文件路径
            
        Returns:
            解压后的文件路径列表，如果不是 ZIP 文件则返回 None
        """
        import os
        import zipfile
        import tempfile
        
        if not file_path.lower().endswith('.zip'):
            return None
        
        try:
            # 创建解压目录
            extract_dir = tempfile.mkdtemp(prefix="extracted_documents_")
            
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # 获取解压后的所有文件
            extracted_files = []
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    file_full_path = os.path.join(root, file)
                    extracted_files.append(file_full_path)
            
            logger.info(f"ZIP 解压成功: {len(extracted_files)} 个文件")
            return extracted_files
            
        except Exception as e:
            logger.error(f"ZIP 解压失败: {str(e)}")
            return None
    

    
    def _has_next_page(self, page: Page) -> bool:
        """检查是否有下一页"""
        try:
            next_button = page.locator(self.NEXT_PAGE_SELECTOR)
            return next_button.is_visible() and next_button.is_enabled()
        except Exception as e:
            logger.warning(f"检查下一页失败: {str(e)}")
            return False
    
    def _go_to_next_page(self, page: Page) -> None:
        """翻到下一页"""
        try:
            next_button = page.locator(self.NEXT_PAGE_SELECTOR)
            if next_button.is_visible() and next_button.is_enabled():
                next_button.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(self.PAGE_LOAD_WAIT)
                logger.info("成功翻到下一页")
            else:
                logger.warning("下一页按钮不可用")
        except Exception as e:
            logger.error(f"翻页失败: {str(e)}")
    
    def _match_case_by_document_parties(self, document_paths: List[str]):
        """
        从文书中提取当事人进行案件匹配
        
        委托给 CaseMatcher 执行，统一案件匹配逻辑
        Requirements: 3.1
        """
        try:
            from apps.core.enums import CaseStatus
            
            for doc_path in document_paths:
                logger.info(f"尝试从文书中提取当事人: {doc_path}")
                
                # 使用 CaseMatcher 从文书中提取当事人
                extracted_parties = self.case_matcher.extract_parties_from_document(doc_path)
                
                if not extracted_parties:
                    logger.info(f"从文书 {doc_path} 中未能提取到当事人")
                    continue
                
                logger.info(f"从文书中提取到当事人: {extracted_parties}")
                
                # 使用 CaseMatcher 通过当事人匹配案件
                matched_case = self.case_matcher.match_by_party_names(extracted_parties)
                
                if matched_case:
                    # 检查案件状态
                    if matched_case.status == CaseStatus.ACTIVE:
                        logger.info(f"通过文书当事人匹配到在办案件: Case ID={matched_case.id}")
                        return matched_case
                    else:
                        logger.info(f"匹配到案件但状态为 {matched_case.status}，继续尝试")
                        continue
                else:
                    logger.info(f"当事人 {extracted_parties} 未匹配到案件")
            
            logger.info("所有文书都未能匹配到在办案件")
            return None
            
        except Exception as e:
            logger.warning(f"从文书提取当事人匹配失败: {str(e)}")
            return None
    
    def _sync_case_number_to_case(self, case_id: int, case_number: str) -> bool:
        """
        将案号同步到案件（如果案件还没有这个案号）
        
        Args:
            case_id: 案件 ID
            case_number: 案号
            
        Returns:
            是否成功同步
        """
        try:
            from apps.cases.services.case_number_service import CaseNumberService
            
            case_number_service = CaseNumberService()
            
            # 检查案件是否已有这个案号
            existing_numbers = case_number_service.list_numbers(case_id=case_id)
            
            for num in existing_numbers:
                if num.number == case_number:
                    logger.info(f"案件 {case_id} 已有案号 {case_number}，无需同步")
                    return True
            
            # 创建新案号
            case_number_service.create_number(
                case_id=case_id,
                number=case_number,
                remarks="文书送达自动下载同步"
            )
            
            logger.info(f"案号同步成功: Case ID={case_id}, 案号={case_number}")
            return True
            
        except Exception as e:
            logger.warning(f"案号同步失败: Case ID={case_id}, 案号={case_number}, 错误: {str(e)}")
            return False