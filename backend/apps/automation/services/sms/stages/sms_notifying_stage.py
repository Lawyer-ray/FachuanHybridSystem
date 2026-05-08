"""
SMS 通知阶段处理器

负责发送案件群聊通知，包括：
- 获取待发送的文书路径
- 多平台群聊通知扇出
- 更新通知状态

Requirements: 2.1, 2.2, 5.1, 5.2, 5.5
"""

import logging
from typing import TYPE_CHECKING, Optional

from django.utils.translation import gettext_lazy as _

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.core.dto.chat import MultiPlatformNotificationResult

from .base import BaseSMSStage

if TYPE_CHECKING:
    from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService

logger = logging.getLogger("apps.automation")


class SMSNotifyingStage(BaseSMSStage):
    """
    SMS 通知阶段处理器

    负责发送案件群聊通知，将文书内容和短信内容推送到群聊。
    支持多平台扇出，任一平台成功即为整体成功。

    Requirements: 2.1, 2.2, 5.1, 5.2, 5.5
    """

    def __init__(
        self,
        notification_service: Optional["SMSNotificationService"] = None,
        document_attachment_service: Optional["DocumentAttachmentService"] = None,
    ):
        self._notification_service = notification_service
        self._document_attachment_service = document_attachment_service

    @property
    def notification_service(self) -> "SMSNotificationService":
        """延迟加载短信通知服务"""
        if self._notification_service is None:
            from apps.automation.services.sms.sms_notification_service import SMSNotificationService

            self._notification_service = SMSNotificationService()
        return self._notification_service

    @property
    def document_attachment_service(self) -> "DocumentAttachmentService":
        """延迟加载文书附件服务"""
        if self._document_attachment_service is None:
            from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService

            self._document_attachment_service = DocumentAttachmentService()
        return self._document_attachment_service

    @property
    def stage_name(self) -> str:
        """阶段名称"""
        return "通知"

    def can_process(self, sms: CourtSMS) -> bool:
        return bool(sms.status == CourtSMSStatus.NOTIFYING)

    def process(self, sms: CourtSMS) -> CourtSMS:
        self._log_start(sms)

        try:
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()

            # 获取待发送通知的文书路径
            document_paths = self.document_attachment_service.get_paths_for_notification(sms)
            logger.info(f"准备发送 {len(document_paths)} 个文件到群聊: SMS ID={sms.id}")

            # 发送案件群聊通知（多平台扇出）
            result = self._send_case_chat_notification(sms, document_paths)

            # 持久化通知结果并更新状态
            self._update_notification_status(sms, result)

            sms.save()
            self._log_complete(sms)
            return sms

        except Exception as e:
            self._log_error(sms, e)
            self._handle_notification_error(sms, e)
            return sms

    def _send_case_chat_notification(self, sms: CourtSMS, document_paths: list[str]) -> MultiPlatformNotificationResult:
        """发送案件群聊通知（多平台扇出）"""
        if not sms.case:
            logger.warning(f"短信未绑定案件，无法发送群聊通知: SMS ID={sms.id}")
            from apps.core.dto.chat import PlatformNotificationResult

            return MultiPlatformNotificationResult(
                attempts=[
                    PlatformNotificationResult(
                        platform="none",
                        success=False,
                        error="短信未绑定案件，无法发送群聊通知",
                    )
                ]
            )

        return self.notification_service.send_case_chat_notification(sms, document_paths)

    def _update_notification_status(self, sms: CourtSMS, result: MultiPlatformNotificationResult) -> None:
        """根据通知结果更新 SMS 状态"""
        # 持久化多平台通知结果
        sms.notification_results = result.to_notification_results()

        if result.any_success:
            sms.status = CourtSMSStatus.COMPLETED
            logger.info(f"案件群聊通知发送成功，短信处理完成: SMS ID={sms.id}")
        else:
            sms.status = CourtSMSStatus.FAILED
            error_detail = "; ".join(f"{r.platform}: {r.error}" for r in result.attempts if not r.success)
            sms.error_message = f"案件群聊通知发送失败: {error_detail}" if error_detail else str(_("案件群聊通知发送失败"))
            logger.error(f"案件群聊通知发送失败，短信标记为失败: SMS ID={sms.id}")

    def _handle_notification_error(self, sms: CourtSMS, error: Exception) -> None:
        error_msg = str(error)
        sms.notification_results = sms.notification_results or {}
        sms.notification_results["_exception"] = {"success": False, "error": error_msg}
        sms.status = CourtSMSStatus.FAILED
        sms.error_message = f"案件群聊通知发送失败: {error_msg}"
        sms.save()
        logger.error(f"案件群聊通知发送失败: SMS ID={sms.id}, 错误: {error_msg}")


def create_sms_notifying_stage(
    notification_service: Optional["SMSNotificationService"] = None,
    document_attachment_service: Optional["DocumentAttachmentService"] = None,
) -> SMSNotifyingStage:
    return SMSNotifyingStage(
        notification_service=notification_service,
        document_attachment_service=document_attachment_service,
    )
