"""
法院短信处理核心服务

负责协调整个短信处理流程，包括短信提交、异步处理、状态管理等。
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_q.tasks import async_task

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.core.exceptions import NotFoundError, ValidationException

from ._sms_case_binding_mixin import SMSCaseBindingMixin
from ._sms_document_mixin import SMSDocumentMixin
from ._sms_download_mixin import SMSDownloadMixin
from .case_matcher import CaseMatcher
from .sms_parser_service import SMSParserService

if TYPE_CHECKING:
    from apps.automation.services.sms.case_folder_archive_service import CaseFolderArchiveService
    from apps.automation.services.sms.matching.case_number_extractor_service import CaseNumberExtractorService
    from apps.automation.services.sms.matching.document_attachment_service import DocumentAttachmentService
    from apps.automation.services.sms.matching.sms_notification_service import SMSNotificationService
    from apps.core.interfaces import ICaseChatService, ICaseService, IClientService, ILawyerService

logger = logging.getLogger("apps.automation")


class CourtSMSService(SMSCaseBindingMixin, SMSDocumentMixin, SMSDownloadMixin):
    """法院短信处理服务"""

    def __init__(
        self,
        parser: SMSParserService | None = None,
        matcher: CaseMatcher | None = None,
        case_number_extractor: "CaseNumberExtractorService | None" = None,
        document_attachment: "DocumentAttachmentService | None" = None,
        notification: "SMSNotificationService | None" = None,
        case_service: "ICaseService | None" = None,
        client_service: "IClientService | None" = None,
        lawyer_service: "ILawyerService | None" = None,
        case_chat_service: "ICaseChatService | None" = None,
        case_folder_archive: "CaseFolderArchiveService | None" = None,
        document_processing_service: Any | None = None,
        case_number_service: Any | None = None,
    ):
        self.parser = parser or SMSParserService()
        self._matcher = matcher or CaseMatcher()
        self._case_number_extractor = case_number_extractor
        self._document_attachment = document_attachment
        self._notification = notification
        self._case_service = case_service
        self._client_service = client_service
        self._lawyer_service = lawyer_service
        self._case_chat_service = case_chat_service
        self._case_folder_archive = case_folder_archive
        self._document_processing_service = document_processing_service
        self._case_number_service = case_number_service

    @property
    def matcher(self) -> "CaseMatcher":
        return self._matcher

    @property
    def case_service(self) -> "ICaseService":
        if self._case_service is None:
            from apps.core.dependencies.automation_sms_wiring import build_sms_case_service

            self._case_service = build_sms_case_service()
        return self._case_service

    @property
    def client_service(self) -> "IClientService":
        if self._client_service is None:
            from apps.core.dependencies.automation_sms_wiring import build_sms_client_service

            self._client_service = build_sms_client_service()
        return self._client_service

    @property
    def lawyer_service(self) -> "ILawyerService":
        if self._lawyer_service is None:
            from apps.core.dependencies.automation_sms_wiring import build_sms_lawyer_service

            self._lawyer_service = build_sms_lawyer_service()
        return self._lawyer_service

    @property
    def case_chat_service(self) -> "ICaseChatService":
        if self._case_chat_service is None:
            from apps.core.dependencies.automation_sms_wiring import build_sms_case_chat_service

            self._case_chat_service = build_sms_case_chat_service()
        return self._case_chat_service

    @property
    def case_folder_archive(self) -> "CaseFolderArchiveService":
        if self._case_folder_archive is None:
            from .case_folder_archive_service import CaseFolderArchiveService

            self._case_folder_archive = CaseFolderArchiveService()
        return self._case_folder_archive

    @property
    def case_number_extractor(self) -> "CaseNumberExtractorService":
        if self._case_number_extractor is None:
            from .case_number_extractor_service import CaseNumberExtractorService

            self._case_number_extractor = CaseNumberExtractorService()
        return self._case_number_extractor

    @property
    def document_attachment(self) -> "DocumentAttachmentService":
        if self._document_attachment is None:
            from .document_attachment_service import DocumentAttachmentService

            self._document_attachment = DocumentAttachmentService()
        return self._document_attachment

    @property
    def notification(self) -> "SMSNotificationService":
        if self._notification is None:
            from .sms_notification_service import SMSNotificationService

            self._notification = SMSNotificationService()
        return self._notification

    def list_sms(
        self,
        *,
        status: str | None = None,
        sms_type: str | None = None,
        has_case: bool | None = None,
        date_from: Any = None,
        date_to: Any = None,
    ) -> Any:
        """查询短信列表"""
        qs = CourtSMS.objects.all().order_by("-received_at")
        if status:
            qs = qs.filter(status=status)
        if sms_type:
            qs = qs.filter(sms_type=sms_type)
        if has_case is True:
            qs = qs.filter(case__isnull=False)
        elif has_case is False:
            qs = qs.filter(case__isnull=True)
        if date_from:
            qs = qs.filter(received_at__gte=date_from)
        if date_to:
            qs = qs.filter(received_at__lte=date_to)
        return qs

    def submit_sms(self, content: str, received_at: datetime | None = None) -> CourtSMS:
        """提交短信，创建记录并触发异步处理"""
        if not content or not content.strip():
            raise ValidationException(
                message=_("短信内容不能为空"), code="EMPTY_SMS_CONTENT", errors={"content": "短信内容不能为空"}
            )

        if received_at is None:
            received_at = timezone.now()

        try:
            sms = CourtSMS.objects.create(
                content=content.strip(),
                received_at=received_at,
                status=CourtSMSStatus.PENDING,
                document_file_paths=[],
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
            logger.error(f"提交短信处理失败: {e!s}")
            raise ValidationException(
                message=f"提交短信处理失败: {e!s}", code="SMS_SUBMIT_FAILED", errors={"error": str(e)}
            ) from e

    @transaction.atomic
    def assign_case(self, sms_id: int, case_id: int) -> CourtSMS:
        """手动指定案件"""
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist as e:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}") from e

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
                sms.error_message = str(_("创建案件绑定失败"))
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
            logger.error(f"手动指定案件失败: SMS ID={sms_id}, Case ID={case_id}, 错误: {e!s}")
            raise ValidationException(
                message=f"手动指定案件失败: {e!s}", code="CASE_ASSIGNMENT_FAILED", errors={"error": str(e)}
            ) from e

    def retry_processing(self, sms_id: int) -> CourtSMS:
        """重新处理短信"""
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist as e:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}") from e

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
            logger.error(f"重新处理短信失败: SMS ID={sms_id}, 错误: {e!s}")
            raise ValidationException(
                message=f"重新处理短信失败: {e!s}", code="SMS_RETRY_FAILED", errors={"error": str(e)}
            ) from e

    def process_sms(self, sms_id: int, process_options: dict[str, Any] | None = None) -> CourtSMS:
        """处理短信（异步任务入口）"""
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist as e:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}") from e

        logger.info(f"开始处理短信: ID={sms_id}, 状态={sms.status}")

        try:
            if sms.status == CourtSMSStatus.PENDING:
                sms = self._process_parsing(sms)

            if sms.status == CourtSMSStatus.PARSING:
                sms = self._process_downloading_or_matching(sms, process_options=process_options)

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
            logger.error(f"处理短信失败: ID={sms_id}, 错误: {e!s}")
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = str(e)
            sms.save()
            raise ValidationException(
                message=f"处理短信失败: {e!s}",
                code="SMS_PROCESSING_FAILED",
                errors={"sms_id": sms_id, "error": str(e)},
            ) from e

    def _process_from_matching(self, sms_id: int) -> CourtSMS:
        """从匹配阶段开始处理"""
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist as e:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}") from e

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
            logger.error(f"从匹配阶段处理短信失败: ID={sms_id}, 错误: {e!s}")
            raise

    def _process_from_renaming(self, sms_id: int) -> CourtSMS:
        """从重命名阶段开始处理"""
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist as e:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}") from e

        logger.info(f"从重命名阶段开始处理短信: ID={sms_id}")

        try:
            if sms.status == CourtSMSStatus.RENAMING:
                sms = self._process_renaming(sms)
            if sms.status == CourtSMSStatus.NOTIFYING:
                sms = self._process_notifying(sms)
            logger.info(f"手动关联案件处理完成: ID={sms_id}, 最终状态={sms.status}")
            return sms
        except Exception as e:
            logger.error(f"从重命名阶段处理短信失败: ID={sms_id}, 错误: {e!s}")
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = str(e)
            sms.save()
            raise

    def _process_parsing(self, sms: CourtSMS) -> CourtSMS:
        """处理解析阶段"""
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
            logger.error(f"短信解析失败: ID={sms.id}, 错误: {e!s}")
            raise

    def _process_matching(self, sms: CourtSMS) -> CourtSMS:
        """处理案件匹配阶段"""
        logger.info(f"开始匹配案件: SMS ID={sms.id}")

        try:
            sms.status = CourtSMSStatus.MATCHING
            sms.save()

            if sms.case:
                logger.info(f"短信 {sms.id} 已手动指定案件: {sms.case.id}")
                success = self._create_case_binding(sms)
                if success:
                    sms.status = CourtSMSStatus.RENAMING
                else:
                    sms.status = CourtSMSStatus.FAILED
                    sms.error_message = str(_("创建案件绑定失败"))
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
                    sms.error_message = str(_("创建案件绑定失败"))
                    sms.save()
                    logger.error(f"案件绑定失败: SMS ID={sms.id}")
            else:
                logger.info(f"案件匹配失败，标记为待人工处理: SMS ID={sms.id}")
                sms.status = CourtSMSStatus.PENDING_MANUAL
                sms.error_message = str(_("未能匹配到唯一的在办案件，需要人工处理"))
                sms.save()

            return sms

        except Exception as e:
            logger.error(f"案件匹配失败: SMS ID={sms.id}, 错误: {e!s}")
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = f"案件匹配过程中发生错误: {e!s}"
            sms.save()
            raise

    def _process_notifying(self, sms: CourtSMS) -> CourtSMS:
        """处理通知阶段"""
        logger.info(f"开始发送案件群聊通知: SMS ID={sms.id}")

        try:
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()

            document_paths = self.document_attachment.get_paths_for_notification(sms)
            logger.info(f"准备发送 {len(document_paths)} 个文件到群聊: SMS ID={sms.id}")

            case_chat_success = False
            error_detail = None

            if sms.case:
                case_chat_success, error_detail = self.notification.send_case_chat_notification(sms, document_paths)

                if case_chat_success:
                    sms.feishu_sent_at = timezone.now()
                    sms.feishu_error = None
                    logger.info(f"案件群聊通知成功: SMS ID={sms.id}")
                else:
                    sms.feishu_error = error_detail or "案件群聊通知失败"
                    logger.error(f"案件群聊通知失败: SMS ID={sms.id}, 原因: {error_detail}")
            else:
                error_detail = "短信未绑定案件，无法发送群聊通知"
                logger.warning(f"{error_detail}: SMS ID={sms.id}")
                sms.feishu_error = error_detail

            if case_chat_success:
                sms.status = CourtSMSStatus.COMPLETED
                logger.info(f"案件群聊通知发送成功，短信处理完成: SMS ID={sms.id}")
            else:
                sms.status = CourtSMSStatus.FAILED
                sms.error_message = f"案件群聊通知发送失败: {error_detail or '未知错误'}"
                logger.error(f"案件群聊通知发送失败，短信标记为失败: SMS ID={sms.id}")

            sms.save()
            return sms

        except Exception as e:
            logger.error(f"案件群聊通知发送失败: SMS ID={sms.id}, 错误: {e!s}")
            sms.feishu_error = str(e)
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = f"案件群聊通知发送失败: {e!s}"
            sms.save()
            return sms


def process_sms_async(sms_id: int, process_options: dict[str, Any] | None = None) -> Any:
    """异步处理短信的入口函数"""
    from apps.automation.workers import court_sms_tasks

    return court_sms_tasks.process_sms(sms_id, process_options=process_options)


def process_sms_from_matching(sms_id: int) -> Any:
    """从匹配阶段开始处理短信"""
    from apps.automation.workers import court_sms_tasks

    return court_sms_tasks.process_sms_from_matching(sms_id)


def process_sms_from_renaming(sms_id: int) -> Any:
    """从重命名阶段开始处理短信"""
    from apps.automation.workers import court_sms_tasks

    return court_sms_tasks.process_sms_from_renaming(sms_id)


def retry_download_task(sms_id: Any, **kwargs: Any) -> Any:
    """重试下载任务"""
    from apps.automation.workers import court_sms_tasks

    return court_sms_tasks.retry_download_task(sms_id, **kwargs)
