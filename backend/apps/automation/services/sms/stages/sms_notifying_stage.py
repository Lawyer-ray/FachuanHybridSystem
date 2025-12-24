"""
SMS 通知阶段处理器

负责发送案件群聊通知，包括：
- 获取待发送的文书路径
- 发送案件群聊通知
- 更新通知状态

Requirements: 2.1, 2.2, 5.1, 5.2, 5.5
"""
import logging
from typing import Optional, List, TYPE_CHECKING

from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.core.interfaces import ServiceLocator
from .base import BaseSMSStage

if TYPE_CHECKING:
    from apps.automation.services.sms.sms_notification_service import (
        SMSNotificationService,
    )
    from apps.automation.services.sms.document_attachment_service import (
        DocumentAttachmentService,
    )

logger = logging.getLogger("apps.automation")


class SMSNotifyingStage(BaseSMSStage):
    """
    SMS 通知阶段处理器
    
    负责发送案件群聊通知，将文书内容和短信内容推送到群聊。
    
    Requirements: 2.1, 2.2, 5.1, 5.2, 5.5
    """
    
    def __init__(
        self,
        notification_service: Optional["SMSNotificationService"] = None,
        document_attachment_service: Optional["DocumentAttachmentService"] = None,
    ):
        """
        初始化通知阶段处理器
        
        Args:
            notification_service: 短信通知服务（可选，支持依赖注入）
            document_attachment_service: 文书附件服务（可选，支持依赖注入）
        """
        self._notification_service = notification_service
        self._document_attachment_service = document_attachment_service
    
    @property
    def notification_service(self) -> "SMSNotificationService":
        """延迟加载短信通知服务"""
        if self._notification_service is None:
            from apps.automation.services.sms.sms_notification_service import (
                SMSNotificationService,
            )
            self._notification_service = SMSNotificationService()
        return self._notification_service
    
    @property
    def document_attachment_service(self) -> "DocumentAttachmentService":
        """延迟加载文书附件服务"""
        if self._document_attachment_service is None:
            from apps.automation.services.sms.document_attachment_service import (
                DocumentAttachmentService,
            )
            self._document_attachment_service = DocumentAttachmentService()
        return self._document_attachment_service
    
    @property
    def stage_name(self) -> str:
        """阶段名称"""
        return "通知"
    
    def can_process(self, sms: CourtSMS) -> bool:
        """
        检查是否可以处理通知阶段
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            bool: 是否可以处理
        """
        return sms.status == CourtSMSStatus.NOTIFYING
    
    def process(self, sms: CourtSMS) -> CourtSMS:
        """
        处理通知阶段
        
        委托给 SMSNotificationService 和 DocumentAttachmentService 处理通知发送
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            CourtSMS: 处理后的 SMS 实例
        """
        self._log_start(sms)
        
        try:
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            
            # 获取待发送通知的文书路径
            document_paths = self.document_attachment_service.get_paths_for_notification(sms)
            logger.info(f"准备发送 {len(document_paths)} 个文件到群聊: SMS ID={sms.id}")
            
            # 发送案件群聊通知
            case_chat_success = self._send_case_chat_notification(sms, document_paths)
            
            # 根据通知结果更新状态
            self._update_notification_status(sms, case_chat_success)
            
            sms.save()
            self._log_complete(sms)
            return sms
            
        except Exception as e:
            self._log_error(sms, e)
            self._handle_notification_error(sms, e)
            return sms
    
    def _send_case_chat_notification(
        self, 
        sms: CourtSMS, 
        document_paths: List[str]
    ) -> bool:
        """
        发送案件群聊通知
        
        Args:
            sms: CourtSMS 实例
            document_paths: 文书文件路径列表
            
        Returns:
            bool: 是否发送成功
        """
        if not sms.case:
            logger.warning(f"短信未绑定案件，无法发送群聊通知: SMS ID={sms.id}")
            sms.feishu_error = "短信未绑定案件，无法发送群聊通知"
            return False
        
        # 委托给 SMSNotificationService 发送通知
        success = self.notification_service.send_case_chat_notification(
            sms, document_paths
        )
        
        return success
    
    def _update_notification_status(self, sms: CourtSMS, success: bool) -> None:
        """
        根据通知结果更新 SMS 状态
        
        Args:
            sms: CourtSMS 实例
            success: 通知是否成功
        """
        if success:
            sms.feishu_sent_at = timezone.now()
            sms.feishu_error = None
            sms.status = CourtSMSStatus.COMPLETED
            logger.info(f"案件群聊通知发送成功，短信处理完成: SMS ID={sms.id}")
        else:
            sms.status = CourtSMSStatus.FAILED
            if not sms.feishu_error:
                sms.feishu_error = "案件群聊通知发送失败"
            sms.error_message = "案件群聊通知发送失败"
            logger.error(f"案件群聊通知发送失败，短信标记为失败: SMS ID={sms.id}")
    
    def _handle_notification_error(self, sms: CourtSMS, error: Exception) -> None:
        """
        处理通知阶段错误
        
        Args:
            sms: CourtSMS 实例
            error: 异常对象
        """
        error_msg = str(error)
        sms.feishu_error = error_msg
        sms.status = CourtSMSStatus.FAILED
        sms.error_message = f"案件群聊通知发送失败: {error_msg}"
        sms.save()
        logger.error(f"案件群聊通知发送失败: SMS ID={sms.id}, 错误: {error_msg}")


def create_sms_notifying_stage(
    notification_service: Optional["SMSNotificationService"] = None,
    document_attachment_service: Optional["DocumentAttachmentService"] = None,
) -> SMSNotifyingStage:
    """
    工厂函数：创建 SMS 通知阶段处理器
    
    Args:
        notification_service: 短信通知服务（可选）
        document_attachment_service: 文书附件服务（可选）
        
    Returns:
        SMSNotifyingStage: 通知阶段处理器实例
    """
    return SMSNotifyingStage(
        notification_service=notification_service,
        document_attachment_service=document_attachment_service,
    )
