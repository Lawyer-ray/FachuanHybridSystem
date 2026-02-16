"""
法院短信处理核心服务

负责协调整个短信处理流程，包括短信提交、异步处理、状态管理等。
"""

import logging
from datetime import datetime
from typing import List, Optional

from django.db import transaction
from django.utils import timezone
from django_q.tasks import async_task

from apps.automation.models import CourtSMS, CourtSMSStatus, ScraperTask, ScraperTaskStatus, ScraperTaskType
from apps.core.enums import ChatPlatform
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.interfaces import ServiceLocator

from .case_matcher import CaseMatcher
from .document_renamer import DocumentRenamer
from .sms_parser_service import SMSParserService

logger = logging.getLogger("apps.automation")


class CourtSMSService:
    """法院短信处理服务"""

    def __init__(
        self,
        parser: SMSParserService = None,
        matcher: CaseMatcher = None,
        case_number_extractor: Optional["CaseNumberExtractorService"] = None,
        document_attachment: Optional["DocumentAttachmentService"] = None,
        notification: Optional["SMSNotificationService"] = None,
        case_service: Optional["ICaseService"] = None,
        client_service: Optional["IClientService"] = None,
        lawyer_service: Optional["ILawyerService"] = None,
        case_chat_service: Optional["ICaseChatService"] = None,
    ):
        """
        初始化服务，支持依赖注入

        Args:
            parser: 短信解析服务
            matcher: 案件匹配服务
            case_number_extractor: 案号提取服务（可选）
            document_attachment: 文书附件服务（可选）
            notification: 短信通知服务（可选）
            case_service: 案件服务（可选）
            client_service: 客户服务（可选）
            lawyer_service: 律师服务（可选）
            case_chat_service: 案件群聊服务（可选）
        """
        self.parser = parser or SMSParserService()
        self.matcher = matcher or CaseMatcher()
        self._case_number_extractor = case_number_extractor
        self._document_attachment = document_attachment
        self._notification = notification
        self._case_service = case_service
        self._client_service = client_service
        self._lawyer_service = lawyer_service
        self._case_chat_service = case_chat_service

    @property
    def case_service(self) -> "ICaseService":
        """延迟加载案件服务"""
        if self._case_service is None:
            from apps.core.interfaces import ServiceLocator

            self._case_service = ServiceLocator.get_case_service()
        return self._case_service

    @property
    def client_service(self) -> "IClientService":
        """延迟加载客户服务"""
        if self._client_service is None:
            from apps.core.interfaces import ServiceLocator

            self._client_service = ServiceLocator.get_client_service()
        return self._client_service

    @property
    def lawyer_service(self) -> "ILawyerService":
        """延迟加载律师服务"""
        if self._lawyer_service is None:
            from apps.core.interfaces import ServiceLocator

            self._lawyer_service = ServiceLocator.get_lawyer_service()
        return self._lawyer_service

    @property
    def case_chat_service(self) -> "ICaseChatService":
        """延迟加载案件群聊服务"""
        if self._case_chat_service is None:
            from apps.core.interfaces import ServiceLocator

            self._case_chat_service = ServiceLocator.get_case_chat_service()
        return self._case_chat_service

    @property
    def case_number_extractor(self) -> "CaseNumberExtractorService":
        """延迟加载案号提取服务"""
        if self._case_number_extractor is None:
            from .case_number_extractor_service import CaseNumberExtractorService

            self._case_number_extractor = CaseNumberExtractorService()
        return self._case_number_extractor

    @property
    def document_attachment(self) -> "DocumentAttachmentService":
        """延迟加载文书附件服务"""
        if self._document_attachment is None:
            from .document_attachment_service import DocumentAttachmentService

            self._document_attachment = DocumentAttachmentService()
        return self._document_attachment

    @property
    def notification(self) -> "SMSNotificationService":
        """延迟加载短信通知服务"""
        if self._notification is None:
            from .sms_notification_service import SMSNotificationService

            self._notification = SMSNotificationService()
        return self._notification

    def submit_sms(self, content: str, received_at: datetime = None) -> CourtSMS:
        """
        提交短信，创建记录并触发异步处理

        Args:
            content: 短信内容
            received_at: 收到时间，默认为当前时间

        Returns:
            CourtSMS: 创建的短信记录

        Raises:
            ValidationException: 参数验证失败
        """
        if not content or not content.strip():
            raise ValidationException(
                message="短信内容不能为空", code="EMPTY_SMS_CONTENT", errors={"content": "短信内容不能为空"}
            )
        if received_at is None:
            received_at = timezone.now()
        try:
            sms = CourtSMS.objects.create(
                content=content.strip(), received_at=received_at, status=CourtSMSStatus.PENDING
            )
            logger.info(f"创建短信记录成功: ID={sms.id}, 长度={len(content)}")
            task_id = async_task(
                "apps.automation.services.sms.court_sms_service.process_sms_async",
                sms.id,
                task_name=f"court_sms_processing_{sms.id}",
            )
            logger.info(f"提交异步处理任务: SMS ID={sms.id}, Task ID={task_id}")
            return sms
        except Exception as e:
            logger.error(f"提交短信处理失败: {str(e)}")
            raise ValidationException(
                message=f"提交短信处理失败: {str(e)}", code="SMS_SUBMIT_FAILED", errors={"error": str(e)}
            )

    @transaction.atomic
    def assign_case(self, sms_id: int, case_id: int) -> CourtSMS:
        """
        手动指定案件

        手动指定后直接创建案件绑定，跳过匹配阶段，进入重命名和通知流程。

        Args:
            sms_id: 短信记录ID
            case_id: 案件ID

        Returns:
            CourtSMS: 更新后的短信记录

        Raises:
            NotFoundError: 记录不存在
            ValidationException: 操作失败
        """
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}")
        case_dto = self.case_service.get_case_by_id_internal(case_id)
        if not case_dto:
            raise NotFoundError(f"案件不存在: ID={case_id}")
        try:
            sms.case_id = case_id
            sms.error_message = None
            sms.save()
            logger.info(f"手动指定案件成功: SMS ID={sms_id}, Case ID={case_id}")
            success = self._create_case_binding(sms)
            if success:
                sms.status = CourtSMSStatus.RENAMING
                sms.save()
                logger.info(f"案件绑定创建成功，进入重命名阶段: SMS ID={sms_id}")
            else:
                sms.status = CourtSMSStatus.FAILED
                sms.error_message = "创建案件绑定失败"
                sms.save()
                logger.error(f"案件绑定创建失败: SMS ID={sms_id}")
                return sms
            task_id = async_task(
                "apps.automation.services.sms.court_sms_service.process_sms_from_renaming",
                sms.id,
                task_name=f"court_sms_continue_{sms.id}",
            )
            logger.info(f"触发后续处理任务: SMS ID={sms.id}, Task ID={task_id}")
            return sms
        except Exception as e:
            logger.error(f"手动指定案件失败: SMS ID={sms_id}, Case ID={case_id}, 错误: {str(e)}")
            raise ValidationException(
                message=f"手动指定案件失败: {str(e)}", code="CASE_ASSIGNMENT_FAILED", errors={"error": str(e)}
            )

    def retry_processing(self, sms_id: int) -> CourtSMS:
        """
        重新处理短信

        Args:
            sms_id: 短信记录ID

        Returns:
            CourtSMS: 更新后的短信记录

        Raises:
            NotFoundError: 记录不存在
            ValidationException: 操作失败
        """
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}")
        try:
            sms.status = CourtSMSStatus.PENDING
            sms.error_message = None
            sms.retry_count += 1
            sms.scraper_task = None
            sms.case = None
            sms.case_log = None
            sms.feishu_sent_at = None
            sms.feishu_error = None
            sms.save()
            logger.info(f"重置短信状态成功: SMS ID={sms_id}, 重试次数={sms.retry_count}")
            task_id = async_task(
                "apps.automation.services.sms.court_sms_service.process_sms_async",
                sms.id,
                task_name=f"court_sms_retry_{sms.id}_{sms.retry_count}",
            )
            logger.info(f"重新提交处理任务: SMS ID={sms.id}, Task ID={task_id}")
            return sms
        except Exception as e:
            logger.error(f"重新处理短信失败: SMS ID={sms_id}, 错误: {str(e)}")
            raise ValidationException(
                message=f"重新处理短信失败: {str(e)}", code="SMS_RETRY_FAILED", errors={"error": str(e)}
            )

    def process_sms(self, sms_id: int) -> CourtSMS:
        """
        处理短信（异步任务入口）

        Args:
            sms_id: 短信记录ID

        Returns:
            CourtSMS: 处理后的短信记录

        Raises:
            NotFoundError: 记录不存在
            ValidationException: 处理失败
        """
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}")
        logger.info(f"开始处理短信: ID={sms_id}, 状态={sms.status}")
        try:
            if sms.status == CourtSMSStatus.PENDING:
                sms = self._process_parsing(sms)
            if sms.status == CourtSMSStatus.PARSING:
                sms = self._process_downloading_or_matching(sms)
            if sms.status == CourtSMSStatus.DOWNLOADING:
                logger.info(f"短信 {sms_id} 进入下载阶段，等待下载完成")
                return sms
            if sms.status == CourtSMSStatus.MATCHING:
                sms = self._process_matching(sms)
            if sms.status == CourtSMSStatus.RENAMING:
                sms = self._process_renaming(sms)
            if sms.status == CourtSMSStatus.NOTIFYING:
                sms = self._process_notifying(sms)
            logger.info(f"短信处理完成: ID={sms_id}, 最终状态={sms.status}")
            return sms
        except Exception as e:
            logger.error(f"处理短信失败: ID={sms_id}, 错误: {str(e)}")
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = str(e)
            sms.save()
            raise ValidationException(
                message=f"处理短信失败: {str(e)}",
                code="SMS_PROCESSING_FAILED",
                errors={"sms_id": sms_id, "error": str(e)},
            )

    def _process_from_matching(self, sms_id: int) -> CourtSMS:
        """
        从匹配阶段开始处理（用于手动指定案件后）

        Args:
            sms_id: 短信记录ID

        Returns:
            CourtSMS: 处理后的短信记录
        """
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}")
        logger.info(f"从匹配阶段开始处理短信: ID={sms_id}")
        try:
            if sms.status == CourtSMSStatus.MATCHING:
                sms = self._process_matching(sms)
            if sms.status == CourtSMSStatus.RENAMING:
                sms = self._process_renaming(sms)
            if sms.status == CourtSMSStatus.NOTIFYING:
                sms = self._process_notifying(sms)
            return sms
        except Exception as e:
            logger.error(f"从匹配阶段处理短信失败: ID={sms_id}, 错误: {str(e)}")
            raise

    def _process_from_renaming(self, sms_id: int) -> CourtSMS:
        """
        从重命名阶段开始处理（用于手动指定案件后）

        Args:
            sms_id: 短信记录ID

        Returns:
            CourtSMS: 处理后的短信记录
        """
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}")
        logger.info(f"从重命名阶段开始处理短信: ID={sms_id}")
        try:
            if sms.status == CourtSMSStatus.RENAMING:
                sms = self._process_renaming(sms)
            if sms.status == CourtSMSStatus.NOTIFYING:
                sms = self._process_notifying(sms)
            logger.info(f"手动关联案件处理完成: ID={sms_id}, 最终状态={sms.status}")
            return sms
        except Exception as e:
            logger.error(f"从重命名阶段处理短信失败: ID={sms_id}, 错误: {str(e)}")
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = str(e)
            sms.save()
            raise

    def _process_parsing(self, sms: CourtSMS) -> CourtSMS:
        """
        处理解析阶段
        """
        logger.info(f"开始解析短信: ID={sms.id}")
        try:
            sms.status = CourtSMSStatus.PARSING
            sms.save()
            parse_result = self.parser.parse(sms.content)
            sms.sms_type = parse_result.sms_type
            sms.download_links = parse_result.download_links
            sms.case_numbers = parse_result.case_numbers
            sms.party_names = parse_result.party_names
            sms.save()
            logger.info(f"短信解析完成: ID={sms.id}, 类型={parse_result.sms_type}")
            return sms
        except Exception as e:
            logger.error(f"短信解析失败: ID={sms.id}, 错误: {str(e)}")
            raise

    def _process_downloading_or_matching(self, sms: CourtSMS) -> CourtSMS:
        """
        根据是否有下载链接决定进入下载或匹配阶段
        """
        if sms.download_links:
            logger.info(f"短信 {sms.id} 有下载链接，创建下载任务")
            scraper_task = self._create_download_task(sms)
            if scraper_task:
                sms.scraper_task = scraper_task
                sms.status = CourtSMSStatus.DOWNLOADING
                sms.save()
                logger.info(f"下载任务创建成功: SMS ID={sms.id}, Task ID={scraper_task.id}")
            else:
                logger.warning(f"下载任务创建失败，直接进入匹配: SMS ID={sms.id}")
                sms.status = CourtSMSStatus.MATCHING
                sms.save()
        else:
            logger.info(f"短信 {sms.id} 无下载链接，直接进入匹配")
            sms.status = CourtSMSStatus.MATCHING
            sms.save()
        return sms

    def _process_matching(self, sms: CourtSMS) -> CourtSMS:
        """
        处理案件匹配阶段

        Requirements 1.1, 1.5, 1.6:
        - 确保在文书下载完成后再进行匹配
        - 匹配到唯一案件时自动绑定
        - 匹配失败或多个匹配时标记为待人工处理
        - 从文书中提取的案号和当事人回写到 CourtSMS 记录
        """
        logger.info(f"开始匹配案件: SMS ID={sms.id}")
        try:
            sms.status = CourtSMSStatus.MATCHING
            sms.save()
            if sms.case:
                logger.info(f"短信 {sms.id} 已手动指定案件: {sms.case.id}")
                success = self._create_case_binding(sms)
                if success:
                    sms.status = CourtSMSStatus.RENAMING
                    sms.save()
                    return sms
                else:
                    sms.status = CourtSMSStatus.FAILED
                    sms.error_message = "创建案件绑定失败"
                    sms.save()
                    return sms
            should_wait = self._should_wait_for_document_download(sms)
            logger.info(f"短信 {sms.id} 下载等待检查结果: {should_wait}")
            if should_wait:
                logger.info(f"短信 {sms.id} 需要等待文书下载完成后再进行匹配，保持 MATCHING 状态")
                return sms
            self._extract_and_update_sms_from_documents(sms)
            logger.info(f"开始自动匹配案件: SMS ID={sms.id}, 只匹配状态为'在办'的案件")
            matched_case_dto = self.matcher.match(sms)
            if matched_case_dto:
                sms.case_id = matched_case_dto.id
                sms.save()
                logger.info(f"案件匹配成功: SMS ID={sms.id}, Case ID={matched_case_dto.id}")
                success = self._create_case_binding(sms)
                if success:
                    sms.status = CourtSMSStatus.RENAMING
                    sms.save()
                    logger.info(f"案件自动绑定成功: SMS ID={sms.id}")
                else:
                    sms.status = CourtSMSStatus.FAILED
                    sms.error_message = "创建案件绑定失败"
                    sms.save()
                    logger.error(f"案件绑定失败: SMS ID={sms.id}")
            else:
                logger.info(f"案件匹配失败，标记为待人工处理: SMS ID={sms.id}")
                sms.status = CourtSMSStatus.PENDING_MANUAL
                sms.error_message = "未能匹配到唯一的在办案件，需要人工处理"
                sms.save()
            return sms
        except Exception as e:
            logger.error(f"案件匹配失败: SMS ID={sms.id}, 错误: {str(e)}")
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = f"案件匹配过程中发生错误: {str(e)}"
            sms.save()
            raise

    def _extract_and_update_sms_from_documents(self, sms: CourtSMS) -> None:
        """
        从文书中提取案号和当事人，并回写到 CourtSMS 记录

        这样即使短信中没有提取到案号和当事人，也能在 Admin 列表中显示从文书中提取的信息。

        Args:
            sms: CourtSMS 实例
        """
        if not sms.scraper_task:
            logger.info(f"短信 {sms.id} 没有下载任务，跳过文书信息提取")
            return
        document_paths = self._get_document_paths_for_extraction(sms)
        if not document_paths:
            logger.info(f"短信 {sms.id} 没有已下载的文书，跳过文书信息提取")
            return
        logger.info(f"开始从 {len(document_paths)} 个文书中提取案号和当事人: SMS ID={sms.id}")
        extracted_case_numbers = list(sms.case_numbers) if sms.case_numbers else []
        extracted_party_names = list(sms.party_names) if sms.party_names else []
        has_updates = False
        for doc_path in document_paths:
            try:
                if not extracted_case_numbers:
                    case_numbers = self.case_number_extractor.extract_from_document(doc_path)
                    if case_numbers:
                        extracted_case_numbers.extend(case_numbers)
                        logger.info(f"从文书 {doc_path} 提取到案号: {case_numbers}")
                        has_updates = True
                if not extracted_party_names:
                    party_names = self.matcher.extract_parties_from_document(doc_path)
                    if party_names:
                        extracted_party_names.extend(party_names)
                        logger.info(f"从文书 {doc_path} 提取到当事人: {party_names}")
                        has_updates = True
                if extracted_case_numbers and extracted_party_names:
                    break
            except Exception as e:
                logger.warning(f"从文书提取信息失败: {doc_path}, 错误: {str(e)}")
                continue
        if has_updates:
            unique_case_numbers = list(dict.fromkeys(extracted_case_numbers))
            unique_party_names = list(dict.fromkeys(extracted_party_names))
            sms.case_numbers = unique_case_numbers
            sms.party_names = unique_party_names
            sms.save()
            logger.info(
                f"已更新短信记录的案号和当事人: SMS ID={sms.id}, 案号={unique_case_numbers}, 当事人={unique_party_names}"
            )

    def _get_document_paths_for_extraction(self, sms: CourtSMS) -> list:
        """
        获取用于提取信息的文书路径列表

        Args:
            sms: CourtSMS 实例

        Returns:
            文书路径列表
        """
        import os

        document_paths = []
        try:
            if sms.scraper_task and hasattr(sms.scraper_task, "documents"):
                documents = sms.scraper_task.documents.filter(download_status="success")
                for doc in documents:
                    if doc.local_file_path and os.path.exists(doc.local_file_path):
                        document_paths.append(doc.local_file_path)
            if not document_paths and sms.scraper_task:
                result = sms.scraper_task.result
                if result and isinstance(result, dict):
                    files = result.get("files", [])
                    for file_path in files:
                        if file_path and os.path.exists(file_path):
                            document_paths.append(file_path)
        except Exception as e:
            logger.warning(f"获取文书路径失败: SMS ID={sms.id}, 错误: {str(e)}")
        return document_paths

    def _process_renaming(self, sms: CourtSMS) -> CourtSMS:
        """
        处理文书重命名阶段

        委托给 DocumentAttachmentService 处理文书重命名和附件添加
        """
        logger.info(f"开始重命名文书: SMS ID={sms.id}")
        try:
            sms.status = CourtSMSStatus.RENAMING
            sms.save()
            if not sms.scraper_task:
                logger.info(f"短信 {sms.id} 无下载任务，跳过重命名")
                sms.status = CourtSMSStatus.NOTIFYING
                sms.save()
                return sms
            document_paths = self.document_attachment.get_paths_for_renaming(sms)
            if not document_paths:
                logger.info(f"短信 {sms.id} 无可重命名的文书，跳过重命名")
                sms.status = CourtSMSStatus.NOTIFYING
                sms.save()
                return sms
            logger.info(f"短信 {sms.id} 找到 {len(document_paths)} 个文书待重命名")
            renamed_paths = self.document_attachment.rename_documents(sms, document_paths)
            if renamed_paths and sms.scraper_task:
                result = sms.scraper_task.result or {}
                if not isinstance(result, dict):
                    result = {}
                result["renamed_files"] = renamed_paths
                sms.scraper_task.result = result
                sms.scraper_task.save()
                logger.info(f"保存重命名后的文件路径到任务结果: {len(renamed_paths)} 个文件")
            if renamed_paths:
                if sms.case_log:
                    self.document_attachment.add_to_case_log(sms, renamed_paths)
                elif sms.case:
                    logger.info(f"短信 {sms.id} 没有案件日志，先创建案件日志")
                    success = self._create_case_binding(sms)
                    if success and sms.case_log:
                        self.document_attachment.add_to_case_log(sms, renamed_paths)
                    else:
                        logger.warning(f"短信 {sms.id} 创建案件日志失败，无法添加文书附件")
            if sms.case and renamed_paths:
                logger.info(f"开始从文书中提取案号: SMS ID={sms.id}")
                case_numbers_to_sync = list(sms.case_numbers) if sms.case_numbers else []
                extracted_from_document = False
                if not case_numbers_to_sync:
                    for file_path in renamed_paths:
                        try:
                            extracted_numbers = self.case_number_extractor.extract_from_document(file_path)
                            if extracted_numbers:
                                case_numbers_to_sync.extend(extracted_numbers)
                                extracted_from_document = True
                                logger.info(f"从文书 {file_path} 提取到案号: {extracted_numbers}")
                                break
                        except Exception as e:
                            logger.warning(f"从文书提取案号失败: {file_path}, 错误: {str(e)}")
                            continue
                if extracted_from_document and case_numbers_to_sync:
                    sms.case_numbers = list(dict.fromkeys(case_numbers_to_sync))
                    sms.save()
                    logger.info(f"已将提取的案号回写到短信记录: SMS ID={sms.id}, 案号={sms.case_numbers}")
                if case_numbers_to_sync:
                    success_count = self.case_number_extractor.sync_to_case(
                        case_id=sms.case.id, case_numbers=case_numbers_to_sync, sms_id=sms.id
                    )
                    logger.info(f"案号同步完成: SMS ID={sms.id}, 写入 {success_count} 个新案号")
            if renamed_paths and (not sms.party_names):
                logger.info(f"开始从文书中提取当事人: SMS ID={sms.id}")
                for file_path in renamed_paths:
                    try:
                        extracted_parties = self.matcher.extract_parties_from_document(file_path)
                        if extracted_parties:
                            sms.party_names = list(dict.fromkeys(extracted_parties))
                            sms.save()
                            logger.info(f"已将提取的当事人回写到短信记录: SMS ID={sms.id}, 当事人={sms.party_names}")
                            break
                    except Exception as e:
                        logger.warning(f"从文书提取当事人失败: {file_path}, 错误: {str(e)}")
                        continue
            logger.info(f"文书重命名阶段完成: SMS ID={sms.id}, 成功重命名 {len(renamed_paths)} 个文书")
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            return sms
        except Exception as e:
            logger.error(f"文书重命名阶段失败: SMS ID={sms.id}, 错误: {str(e)}")
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            return sms

    def _process_notifying(self, sms: CourtSMS) -> CourtSMS:
        """
        处理通知阶段

        委托给 SMSNotificationService 和 DocumentAttachmentService 处理通知发送
        """
        logger.info(f"开始发送案件群聊通知: SMS ID={sms.id}")
        try:
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            document_paths = self.document_attachment.get_paths_for_notification(sms)
            logger.info(f"准备发送 {len(document_paths)} 个文件到群聊: SMS ID={sms.id}")
            case_chat_success = False
            if sms.case:
                case_chat_success = self.notification.send_case_chat_notification(sms, document_paths)
                if case_chat_success:
                    sms.feishu_sent_at = timezone.now()
                    sms.feishu_error = None
                    logger.info(f"案件群聊通知成功: SMS ID={sms.id}")
                else:
                    sms.feishu_error = "案件群聊通知失败"
                    logger.error(f"案件群聊通知失败: SMS ID={sms.id}")
            else:
                logger.warning(f"短信未绑定案件，无法发送群聊通知: SMS ID={sms.id}")
                sms.feishu_error = "短信未绑定案件，无法发送群聊通知"
                case_chat_success = False
            if case_chat_success:
                sms.status = CourtSMSStatus.COMPLETED
                logger.info(f"案件群聊通知发送成功，短信处理完成: SMS ID={sms.id}")
            else:
                sms.status = CourtSMSStatus.FAILED
                sms.error_message = "案件群聊通知发送失败"
                logger.error(f"案件群聊通知发送失败，短信标记为失败: SMS ID={sms.id}")
            sms.save()
            return sms
        except Exception as e:
            logger.error(f"案件群聊通知发送失败: SMS ID={sms.id}, 错误: {str(e)}")
            sms.feishu_error = str(e)
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = f"案件群聊通知发送失败: {str(e)}"
            sms.save()
            return sms

    def _create_download_task(self, sms: CourtSMS) -> Optional[ScraperTask]:
        """
        创建下载任务并关联到短信记录，然后提交到 Django Q 队列执行
        """
        if not sms.download_links:
            return None
        try:
            download_url = sms.download_links[0]
            task = ScraperTask.objects.create(
                task_type=ScraperTaskType.COURT_DOCUMENT,
                url=download_url,
                case=sms.case,
                config={"court_sms_id": sms.id, "auto_download": True, "source": "court_sms"},
            )
            logger.info(f"创建下载任务成功: Task ID={task.id}, URL={download_url}")
            queue_task_id = async_task(
                "apps.automation.tasks.execute_scraper_task", task.id, task_name=f"court_document_download_{task.id}"
            )
            logger.info(f"提交下载任务到队列: Task ID={task.id}, Queue Task ID={queue_task_id}")
            return task
        except Exception as e:
            logger.error(f"创建下载任务失败: SMS ID={sms.id}, 错误: {str(e)}")
            return None

    def _should_wait_for_document_download(self, sms: CourtSMS) -> bool:
        """
        检查是否需要等待文书下载完成后再进行匹配

        Requirements 1.1: 当短信没有当事人信息但有下载链接时，需要等待文书下载完成

        Args:
            sms: CourtSMS 实例

        Returns:
            bool: 是否需要等待下载完成
        """
        try:
            if sms.party_names:
                logger.info(f"短信 {sms.id} 有当事人信息，无需等待文书下载")
                return False
            if not sms.download_links:
                logger.info(f"短信 {sms.id} 没有下载链接，无需等待文书下载")
                return False
            if not sms.scraper_task:
                logger.info(f"短信 {sms.id} 没有下载任务，无需等待文书下载")
                return False
            try:
                from apps.automation.models import ScraperTask

                fresh_task = ScraperTask.objects.get(id=sms.scraper_task.id)
                sms.scraper_task = fresh_task
                logger.info(f"短信 {sms.id} 刷新下载任务状态: {fresh_task.status}")
            except ScraperTask.DoesNotExist:
                logger.warning(f"短信 {sms.id} 的下载任务不存在，无需等待")
                return False
            if sms.scraper_task.status in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
                logger.info(f"短信 {sms.id} 的下载任务已完成（状态: {sms.scraper_task.status}），不再等待")
                if sms.scraper_task.result and isinstance(sms.scraper_task.result, dict):
                    files = sms.scraper_task.result.get("files", [])
                    if files:
                        logger.info(f"短信 {sms.id} 从任务结果中发现 {len(files)} 个已下载文件")
                return False
            if not hasattr(sms.scraper_task, "documents"):
                if sms.scraper_task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]:
                    logger.info(f"短信 {sms.id} 的下载任务进行中但没有文书记录，需要等待下载")
                    return True
                else:
                    logger.info(f"短信 {sms.id} 的下载任务没有文书记录且已结束，不再等待")
                    return False
            all_documents = sms.scraper_task.documents.all()
            if not all_documents.exists():
                if sms.scraper_task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]:
                    logger.info(f"短信 {sms.id} 的下载任务进行中但没有文书记录，需要等待下载")
                    return True
                else:
                    logger.info(f"短信 {sms.id} 的下载任务没有文书记录且已结束，不再等待")
                    return False
            successful_documents = all_documents.filter(download_status="success")
            failed_documents = all_documents.filter(download_status="failed")
            pending_documents = all_documents.filter(download_status="pending")
            downloading_documents = all_documents.filter(download_status="downloading")
            logger.info(
                f"短信 {sms.id} 文书状态统计: 总数={all_documents.count()}, 成功={successful_documents.count()}, 失败={failed_documents.count()}, 待下载={pending_documents.count()}, 下载中={downloading_documents.count()}"
            )
            logger.info(f"短信 {sms.id} 的下载任务状态: {sms.scraper_task.status}")
            if successful_documents.exists():
                logger.info(f"短信 {sms.id} 已有下载成功的文书，可以进行匹配")
                return False
            if sms.scraper_task.status in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
                logger.info(f"短信 {sms.id} 的下载任务已完成（状态: {sms.scraper_task.status}），不再等待")
                return False
            if (
                sms.scraper_task.status == ScraperTaskStatus.RUNNING
                and all_documents.count() > 0
                and (successful_documents.count() == 0)
                and (pending_documents.count() == 0)
                and (downloading_documents.count() == 0)
            ):
                logger.info(f"短信 {sms.id} 的下载任务运行中但所有文书都已失败，不再等待")
                return False
            if (
                pending_documents.exists()
                or downloading_documents.exists()
                or sms.scraper_task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]
            ):
                logger.info(f"短信 {sms.id} 还有文书在下载中或任务进行中，需要等待下载完成")
                return True
            logger.info(f"短信 {sms.id} 下载状态检查完成，无需等待")
            return False
        except Exception as e:
            logger.error(f"检查下载状态失败: SMS ID={sms.id}, 错误: {str(e)}")
            return False

    def _create_case_binding(self, sms: CourtSMS) -> bool:
        """
        创建案件绑定和日志

        注意：
        1. 此方法只创建案件日志，不添加附件。附件会在 _process_renaming 阶段完成重命名后添加。
        2. 如果短信提取到案号，但案件中还没有该案号，则自动写入案件的 case_numbers 字段。
        """
        if not sms.case:
            return False
        try:
            from apps.core.interfaces import ServiceLocator

            case_log_service = ServiceLocator.get_caselog_service()
            admin_lawyer_dto = self.lawyer_service.get_admin_lawyer_internal()
            if not admin_lawyer_dto:
                logger.error("未找到管理员用户，无法创建案件日志")
                return False
            system_user = self.lawyer_service.get_lawyer_internal(admin_lawyer_dto.id)
            if sms.case_numbers:
                self._add_case_numbers_to_case(sms)
            case_log = case_log_service.create_log(
                case_id=sms.case.id, content=f"收到法院短信：{sms.content}", user=system_user
            )
            sms.case_log = case_log
            sms.save()
            logger.info(f"案件绑定创建成功: SMS ID={sms.id}, CaseLog ID={case_log.id}")
            return True
        except Exception as e:
            logger.error(f"创建案件绑定失败: SMS ID={sms.id}, 错误: {str(e)}")
            return False

    def _add_case_numbers_to_case(self, sms: CourtSMS) -> None:
        """
        将短信中提取的案号写入案件（如果不存在）

        Args:
            sms: CourtSMS 实例（必须已绑定案件）
        """
        if not sms.case or not sms.case_numbers:
            return
        try:
            valid_case_numbers = []
            for num in sms.case_numbers:
                if "年" in num and "月" in num and ("日" in num):
                    continue
                if "年" in num and "月" in num and num.endswith("号"):
                    import re

                    if re.match("^\\d{4}年\\d{1,2}月\\d{1,2}号?$", num):
                        continue
                valid_case_numbers.append(num)
            if not valid_case_numbers:
                logger.info(f"短信 {sms.id} 没有有效的案号需要写入")
                return
            admin_lawyer_dto = self.lawyer_service.get_admin_lawyer_internal()
            user_id = admin_lawyer_dto.id if admin_lawyer_dto else None
            added_count = 0
            for case_number in valid_case_numbers:
                success = self.case_service.add_case_number_internal(
                    case_id=sms.case.id, case_number=case_number, user_id=user_id
                )
                if success:
                    added_count += 1
            if added_count > 0:
                logger.info(f"为案件 {sms.case.id} 添加了 {added_count} 个案号: {valid_case_numbers}")
        except Exception as e:
            logger.warning(f"写入案号失败: SMS ID={sms.id}, 错误: {str(e)}")


def process_sms_async(sms_id: int) -> Any:
    """
    异步处理短信的入口函数

    Args:
        sms_id: 短信记录ID
    """
    service = CourtSMSService()
    return service.process_sms(sms_id)


def process_sms_from_matching(sms_id: int) -> Any:
    """
    从匹配阶段开始处理短信（用于手动指定案件后的处理）

    Args:
        sms_id: 短信记录ID
    """
    service = CourtSMSService()
    return service._process_from_matching(sms_id)


def process_sms_from_renaming(sms_id: int) -> Any:
    """
    从重命名阶段开始处理短信（用于手动指定案件后的处理）

    Args:
        sms_id: 短信记录ID
    """
    service = CourtSMSService()
    return service._process_from_renaming(sms_id)


def retry_download_task(sms_id: Any, **kwargs) -> Any:
    """
    重试下载任务

    Args:
        sms_id: 短信记录ID（可能是字符串或整数）
        **kwargs: 忽略额外的参数（Django Q Schedule 可能传递额外参数）
    """
    sms_id = int(sms_id)
    service = CourtSMSService()
    return service.retry_processing(sms_id)
