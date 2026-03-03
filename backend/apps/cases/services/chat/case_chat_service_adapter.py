"""
案件群聊服务适配器
实现跨模块接口,提供案件群聊服务的统一接口
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import BusinessException, NotFoundError
from apps.core.interfaces import ICaseChatService

from .case_chat_service import CaseChatService

logger = logging.getLogger(__name__)


class CaseChatServiceAdapter(ICaseChatService):
    """
    案件群聊服务适配器
    实现跨模块接口,将 CaseChatService 包装为标准接口
    """

    def __init__(self, service: CaseChatService | None = None) -> None:
        """
        初始化适配器

            service: CaseChatService 实例,如果为 None 则创建新实例
        """
        self.service = service or CaseChatService()

    def send_message_to_case_chat(self, case_id: int, message: str, files: list[str] | None = None) -> bool:
        """
        发送消息到案件群聊

            case_id: 案件 ID
            message: 消息内容
            files: 附件文件路径列表(可选)

            是否发送成功

            NotFoundError: 案件不存在或未配置群聊
            BusinessException: 消息发送失败
        """
        try:
            result = self.service.send_document_notification(
                case_id=case_id, sms_content=message, document_paths=files or []
            )

            if result.success:
                logger.info(
                    "发送消息到案件群聊成功",
                    extra={
                        "action": "send_message_to_case_chat",
                        "case_id": case_id,
                        "file_count": len(files) if files else 0,
                    },
                )
                return True
            else:
                logger.error(
                    "发送消息到案件群聊失败: %s",
                    result.message,
                    extra={
                        "action": "send_message_to_case_chat",
                        "case_id": case_id,
                        "error": result.message,
                        "error_code": result.error_code,
                    },
                )
                raise BusinessException(message=result.message or "消息发送失败", code="MESSAGE_SEND_FAILED")

        except NotFoundError:
            # 重新抛出 NotFoundError
            raise
        except BusinessException:
            # 重新抛出 BusinessException
            raise
        except Exception as e:
            logger.error(
                "发送消息到案件群聊时发生未预期错误: %s",
                e,
                extra={"action": "send_message_to_case_chat", "case_id": case_id, "error": str(e)},
            )
            raise BusinessException(message=_("发送消息时发生系统错误"), code="SYSTEM_ERROR") from e

    def get_case_chat_id(self, case_id: int) -> Any:
        """
        获取案件的群聊ID

            case_id: 案件 ID

            群聊 ID,未配置时返回 None
        """
        try:
            from apps.cases.models import CaseChat

            case_chat = CaseChat.objects.filter(case_id=case_id, is_active=True).first()

            if case_chat:
                logger.debug(
                    "获取案件群聊ID成功",
                    extra={"action": "get_case_chat_id", "case_id": case_id, "chat_id": case_chat.chat_id},
                )
                return case_chat.chat_id
            else:
                logger.debug("案件未配置群聊", extra={"action": "get_case_chat_id", "case_id": case_id})
                return None

        except Exception as e:
            logger.exception("get_case_chat_id_failed", extra={"action": "get_case_chat_id", "case_id": case_id})
            raise BusinessException(message=_("获取案件群聊ID时发生系统错误"), code="SYSTEM_ERROR") from e

    def get_or_create_chat(self, case_id: int, platform: Any = None) -> Any:
        """
        获取或创建案件群聊

            case_id: 案件 ID
            platform: 群聊平台（可选，默认飞书）

            群聊对象

            NotFoundError: 案件不存在
            BusinessException: 群聊创建失败
        """
        try:
            from apps.core.enums import ChatPlatform

            if platform is None:
                platform = ChatPlatform.FEISHU

            chat = self.service.get_or_create_chat(case_id=case_id, platform=platform, perm_open_access=True)

            logger.info(
                "获取或创建群聊成功",
                extra={
                    "action": "get_or_create_chat",
                    "case_id": case_id,
                    "chat_id": chat.chat_id if chat else None,
                },
            )
            return chat

        except NotFoundError:
            raise
        except Exception as e:
            logger.error(
                "获取或创建群聊失败: %s",
                e,
                extra={"action": "get_or_create_chat", "case_id": case_id, "error": str(e)},
            )
            raise BusinessException(message=_("获取或创建群聊时发生系统错误"), code="SYSTEM_ERROR") from e

    def send_document_notification(
        self,
        case_id: int,
        sms_content: str,
        document_paths: list[str] | None = None,
        platform: Any = None,
        title: str = "📋 法院文书通知",
    ) -> Any:
        """
        发送文书通知到案件群聊

            case_id: 案件 ID
            sms_content: 短信内容（作为消息正文）
            document_paths: 文书文件路径列表（可选）
            platform: 群聊平台（可选，默认飞书）
            title: 消息标题

            消息发送结果

            NotFoundError: 案件不存在或未配置群聊
            BusinessException: 消息发送失败
        """
        try:
            from apps.core.enums import ChatPlatform

            if platform is None:
                platform = ChatPlatform.FEISHU

            result = self.service.send_document_notification(
                case_id=case_id,
                sms_content=sms_content,
                document_paths=document_paths or [],
                platform=platform,
                title=title,
                perm_open_access=True,
            )

            if result.success:
                logger.info(
                    "发送文书通知成功",
                    extra={
                        "action": "send_document_notification",
                        "case_id": case_id,
                        "file_count": len(document_paths) if document_paths else 0,
                    },
                )
            else:
                logger.error(
                    "发送文书通知失败: %s",
                    result.message,
                    extra={
                        "action": "send_document_notification",
                        "case_id": case_id,
                        "error": result.message,
                        "error_code": result.error_code,
                    },
                )

            return result

        except NotFoundError:
            raise
        except Exception as e:
            logger.error(
                "发送文书通知时发生未预期错误: %s",
                e,
                extra={"action": "send_document_notification", "case_id": case_id, "error": str(e)},
            )
            raise BusinessException(message=_("发送文书通知时发生系统错误"), code="SYSTEM_ERROR") from e
