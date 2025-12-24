"""
案件群聊服务适配器
实现跨模块接口，提供案件群聊服务的统一接口
"""
from typing import Optional, List
import logging

from apps.core.interfaces import ICaseChatService
from apps.core.exceptions import NotFoundError, BusinessException
from .case_chat_service import CaseChatService

logger = logging.getLogger(__name__)


class CaseChatServiceAdapter(ICaseChatService):
    """
    案件群聊服务适配器
    实现跨模块接口，将 CaseChatService 包装为标准接口
    """

    def __init__(self, service: Optional[CaseChatService] = None):
        """
        初始化适配器

        Args:
            service: CaseChatService 实例，如果为 None 则创建新实例
        """
        self.service = service or CaseChatService()

    def send_message_to_case_chat(
        self,
        case_id: int,
        message: str,
        files: Optional[List[str]] = None
    ) -> bool:
        """
        发送消息到案件群聊
        
        Args:
            case_id: 案件 ID
            message: 消息内容
            files: 附件文件路径列表（可选）
            
        Returns:
            是否发送成功
            
        Raises:
            NotFoundError: 案件不存在或未配置群聊
            BusinessException: 消息发送失败
        """
        try:
            result = self.service.send_document_notification(
                case_id=case_id,
                sms_content=message,
                document_paths=files or []
            )
            
            if result.success:
                logger.info(
                    f"发送消息到案件群聊成功",
                    extra={
                        "action": "send_message_to_case_chat",
                        "case_id": case_id,
                        "file_count": len(files) if files else 0
                    }
                )
                return True
            else:
                logger.error(
                    f"发送消息到案件群聊失败：{result.message}",
                    extra={
                        "action": "send_message_to_case_chat",
                        "case_id": case_id,
                        "error": result.message,
                        "error_code": result.error_code
                    }
                )
                raise BusinessException(
                    message=result.message or "消息发送失败",
                    code="MESSAGE_SEND_FAILED"
                )
                
        except NotFoundError:
            # 重新抛出 NotFoundError
            raise
        except BusinessException:
            # 重新抛出 BusinessException
            raise
        except Exception as e:
            logger.error(
                f"发送消息到案件群聊时发生未预期错误：{e}",
                extra={
                    "action": "send_message_to_case_chat",
                    "case_id": case_id,
                    "error": str(e)
                }
            )
            raise BusinessException(
                message="发送消息时发生系统错误",
                code="SYSTEM_ERROR"
            ) from e

    def get_case_chat_id(self, case_id: int) -> Optional[str]:
        """
        获取案件的群聊ID
        
        Args:
            case_id: 案件 ID
            
        Returns:
            群聊 ID，未配置时返回 None
        """
        try:
            from ..models import CaseChat
            
            case_chat = CaseChat.objects.filter(
                case_id=case_id,
                is_active=True
            ).first()
            
            if case_chat:
                logger.debug(
                    f"获取案件群聊ID成功",
                    extra={
                        "action": "get_case_chat_id",
                        "case_id": case_id,
                        "chat_id": case_chat.chat_id
                    }
                )
                return case_chat.chat_id
            else:
                logger.debug(
                    f"案件未配置群聊",
                    extra={
                        "action": "get_case_chat_id",
                        "case_id": case_id
                    }
                )
                return None
                
        except Exception as e:
            logger.error(
                f"获取案件群聊ID时发生错误：{e}",
                extra={
                    "action": "get_case_chat_id",
                    "case_id": case_id,
                    "error": str(e)
                }
            )
            return None