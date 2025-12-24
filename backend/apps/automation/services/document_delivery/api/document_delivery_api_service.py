"""
文书送达 API 查询服务

负责通过 API 查询文书列表和处理文书，从 DocumentDeliveryService 中提取。
"""
import logging
import math
import queue
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING

from django.utils import timezone

from apps.core.interfaces import ServiceLocator
from apps.automation.models import DocumentQueryHistory
from apps.automation.utils.logging import AutomationLogger
from ..data_classes import (
    DocumentRecord, DocumentDeliveryRecord, DocumentQueryResult, DocumentProcessResult
)
from ..court_document_api_client import CourtDocumentApiClient

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService

logger = logging.getLogger("apps.automation")


class DocumentDeliveryApiService:
    """
    文书送达 API 查询服务
    
    职责：
    1. 通过 API 查询文书列表
    2. 处理分页逻辑
    3. 处理单个文书（下载、匹配、通知）
    4. 检查文书是否需要处理
    
    Requirements: 1.1, 1.3, 5.1, 5.2, 5.5
    """
    
    def __init__(
        self,
        api_client: Optional[CourtDocumentApiClient] = None,
        case_matcher: Optional["CaseMatcher"] = None,
        document_renamer: Optional["DocumentRenamer"] = None,
        notification_service: Optional["SMSNotificationService"] = None,
    ):
        """
        初始化 API 查询服务
        
        Args:
            api_client: API 客户端实例（可选，用于依赖注入）
            case_matcher: 案件匹配服务实例（可选，用于依赖注入）
            document_renamer: 文书重命名服务实例（可选，用于依赖注入）
            notification_service: 通知服务实例（可选，用于依赖注入）
        """
        self._api_client = api_client
        self._case_matcher = case_matcher
        self._document_renamer = document_renamer
        self._notification_service = notification_service
        
        logger.debug("DocumentDeliveryApiService 初始化完成")
    
    @property
    def api_client(self) -> CourtDocumentApiClient:
        """延迟加载 API 客户端"""
        if self._api_client is None:
            self._api_client = CourtDocumentApiClient()
        return self._api_client
    
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

    def query_documents(
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
                if not self.should_process_document(record, cutoff_time, credential_id):
                    result.skipped_count += 1
                    logger.info(f"⏭️ 跳过文书: {record.ah}")
                    continue
                
                logger.info(f"✅ 开始处理文书: {record.ah}")
                
                # 处理文书
                process_result = self.process_document(
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

    def process_document(
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
                send_time = timezone.make_aware(send_time)
            else:
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

    def should_process_document(
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
        # 如果 cutoff_time 是 aware，将 send_time 也转为 aware
        if timezone.is_aware(cutoff_time):
            send_time = timezone.make_aware(send_time)
        
        if send_time <= cutoff_time:
            logger.info(f"⏰ 文书时间 {send_time} 早于截止时间 {cutoff_time}，跳过")
            return False
        
        # 3. 检查是否已经处理过（在独立线程中执行 ORM 操作）
        return self._check_document_not_processed(credential_id, record)
    
    def _check_document_not_processed(
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
        result_queue = queue.Queue()
        
        def do_process():
            try:
                from django.db import connection
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
                        case=matched_case,
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
            case_number_service = ServiceLocator.get_case_number_service()
            
            # 检查案件是否已有这个案号
            existing_numbers = case_number_service.list_numbers_internal(case_id=case_id)
            
            for num in existing_numbers:
                if num.number == case_number:
                    logger.info(f"案件 {case_id} 已有案号 {case_number}，无需同步")
                    return True
            
            # 创建新案号
            case_number_service.create_number_internal(
                case_id=case_id,
                number=case_number,
                remarks="文书送达自动下载同步"
            )
            
            logger.info(f"案号同步成功: Case ID={case_id}, 案号={case_number}")
            return True
            
        except Exception as e:
            logger.warning(f"案号同步失败: Case ID={case_id}, 案号={case_number}, 错误: {str(e)}")
            return False

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
    
    def _record_query_history_in_thread(
        self,
        credential_id: int,
        entry: DocumentDeliveryRecord
    ) -> None:
        """在独立线程中记录查询历史，避免异步上下文问题"""
        def do_record():
            try:
                from django.db import transaction, connection
                
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
