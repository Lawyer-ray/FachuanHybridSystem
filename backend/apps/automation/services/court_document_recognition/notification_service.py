"""
文书识别通知服务

本模块实现文书识别绑定成功后的飞书群通知功能。
参考 SMSNotificationService 的设计模式，复用 CaseChatService 实现通知发送。

设计原则：
- 单一职责：专注于文书识别后的通知发送逻辑
- 依赖注入：支持构造函数注入和延迟加载
- 错误处理：失败时返回 NotificationResult，不抛出异常
- 日志记录：详细记录操作过程和错误信息

主要功能：
- 发送文书识别绑定成功通知
- 构建包含文书关键信息的通知消息
- 推送文书文件到群聊
- 处理通知失败场景

Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3
"""

import logging
from datetime import datetime

from apps.core.enums import ChatPlatform
from apps.core.interfaces import ICaseChatService, ServiceLocator

from .data_classes import NotificationResult

logger = logging.getLogger(__name__)


class DocumentRecognitionNotificationService:
    """文书识别通知服务 - 发送绑定成功后的飞书群通知

    负责在文书识别绑定案件成功后，向对应案件的飞书群发送通知消息和文书文件。
    支持依赖注入和延迟加载模式。

    主要职责：
    - 构建包含文书关键信息的通知消息
    - 获取或创建案件群聊
    - 发送通知消息和文书文件
    - 处理通知失败场景并记录日志

    Requirements: 4.1, 4.2
    """

    def __init__(
        self,
        case_chat_service: ICaseChatService | None = None,
    ):
        """初始化文书识别通知服务

        Args:
            case_chat_service: 案件群聊服务实例（可选，支持依赖注入）

        Requirements: 4.1, 4.2
        """
        self._case_chat_service = case_chat_service
        logger.debug("DocumentRecognitionNotificationService 初始化完成")

    @property
    def case_chat_service(self) -> ICaseChatService:
        """延迟加载案件群聊服务

        如果构造函数中未注入服务实例，则通过 ServiceLocator 获取。

        Returns:
            ICaseChatService: 案件群聊服务实例

        Requirements: 4.1, 4.2
        """
        if self._case_chat_service is None:
            self._case_chat_service = ServiceLocator.get_case_chat_service()
        return self._case_chat_service

    def build_notification_message(
        self,
        document_type: str,
        case_number: str | None,
        key_time: datetime | None,
        case_name: str,
    ) -> str:
        """构建通知消息内容

        根据文书类型和关键信息构建格式化的通知消息。

        Args:
            document_type: 文书类型（如 "summons", "execution"）
            case_number: 案号（可选）
            key_time: 关键时间（开庭时间等，可选）
            case_name: 案件名称

        Returns:
            str: 格式化的通知消息

        Requirements: 2.1, 2.2, 2.3, 2.4
        """
        # 文书类型映射
        type_display_map = {
            "summons": "传票",
            "execution": "执行裁定书",
            "other": "法院文书",
        }
        type_display = type_display_map.get(document_type, "法院文书")

        # 构建消息内容
        lines = [
            f"📋 【{type_display}】识别通知",
            "",
            f"案件：{case_name}",
        ]

        # Requirements 2.2: 包含案号
        if case_number:
            lines.append(f"案号：{case_number}")

        # Requirements 2.3: 传票包含开庭时间
        if key_time:
            if document_type == "summons":
                lines.append(f"开庭时间：{key_time.strftime('%Y年%m月%d日 %H:%M')}")
            else:
                lines.append(f"关键时间：{key_time.strftime('%Y年%m月%d日 %H:%M')}")

        # Requirements 2.4: 包含处理时间
        lines.append(f"处理时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")

        return "\n".join(lines)

    def send_notification(
        self,
        case_id: int,
        document_type: str,
        case_number: str | None,
        key_time: datetime | None,
        file_path: str,
        case_name: str,
    ) -> NotificationResult:
        """发送文书识别通知

        获取或创建案件群聊，发送通知消息和文书文件。

        Args:
            case_id: 案件 ID
            document_type: 文书类型
            case_number: 案号（可选）
            key_time: 关键时间（开庭时间等，可选）
            file_path: 文书文件路径
            case_name: 案件名称

        Returns:
            NotificationResult: 通知发送结果

        Requirements: 1.1, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3
        """
        logger.info(
            "开始发送文书识别通知",
            extra={
                "action": "send_notification",
                "case_id": case_id,
                "document_type": document_type,
                "case_number": case_number,
            },
        )

        # 默认使用飞书平台
        platform = ChatPlatform.FEISHU

        try:
            # Requirements 4.1, 4.2: 获取或创建群聊
            chat_service = self.case_chat_service

            try:
                chat = chat_service.get_or_create_chat(case_id=case_id, platform=platform) # type: ignore
                logger.info(
                    "获取或创建群聊成功",
                    extra={
                        "action": "get_or_create_chat",
                        "case_id": case_id,
                        "chat_id": chat.chat_id,
                    },
                )
            except Exception as e:
                # Requirements 4.3: 群聊创建失败时记录错误并返回失败结果
                logger.error(
                    "获取或创建群聊失败",
                    extra={
                        "action": "get_or_create_chat",
                        "case_id": case_id,
                        "error": str(e),
                        "error_code": "CHAT_CREATION_FAILED",
                    },
                )
                return NotificationResult.failure_result(
                    message=f"获取或创建群聊失败: {e!s}",
                    error_code="CHAT_CREATION_FAILED",
                )

            # 构建通知消息
            message_content = self.build_notification_message(
                document_type=document_type,
                case_number=case_number,
                key_time=key_time,
                case_name=case_name,
            )

            # Requirements 3.1, 3.3: 发送消息和文件
            try:
                result = chat_service.send_document_notification( # type: ignore
                    case_id=case_id,
                    sms_content=message_content,
                    document_paths=[file_path] if file_path else [],
                    platform=platform,
                    title="📋 文书识别通知",
                )

                if result.success:
                    from django.utils import timezone as tz
                    sent_at = tz.now()
                    # 判断文件是否发送成功（根据消息内容判断）
                    file_sent = file_path and "文件发送成功" in (result.message or "")

                    logger.info(
                        "文书识别通知发送成功",
                        extra={
                            "action": "send_notification",
                            "case_id": case_id,
                            "chat_id": chat.chat_id,
                            "file_sent": file_sent,
                        },
                    )

                    return NotificationResult.success_result(
                        sent_at=sent_at,
                        file_sent=file_sent, # type: ignore
                    )
                else:
                    # Requirements 3.2: 消息发送失败
                    logger.warning(
                        "文书识别通知发送失败",
                        extra={
                            "action": "send_notification",
                            "case_id": case_id,
                            "chat_id": chat.chat_id,
                            "error": result.message,
                        },
                    )
                    return NotificationResult.failure_result(
                        message=result.message or "消息发送失败",
                        error_code="MESSAGE_SEND_FAILED",
                    )

            except Exception as e:
                logger.error(
                    "发送通知消息失败",
                    extra={
                        "action": "send_notification",
                        "case_id": case_id,
                        "chat_id": chat.chat_id,
                        "error": str(e),
                        "error_code": "MESSAGE_SEND_ERROR",
                    },
                )
                return NotificationResult.failure_result(
                    message=f"发送通知消息失败: {e!s}",
                    error_code="MESSAGE_SEND_ERROR",
                )

        except ImportError as e:
            logger.error(
                "无法导入 CaseChatService",
                extra={
                    "action": "send_notification",
                    "case_id": case_id,
                    "error": str(e),
                    "error_code": "IMPORT_ERROR",
                },
            )
            return NotificationResult.failure_result(
                message=f"无法导入 CaseChatService: {e!s}",
                error_code="IMPORT_ERROR",
            )
        except Exception as e:
            logger.error(
                "文书识别通知处理失败",
                extra={
                    "action": "send_notification",
                    "case_id": case_id,
                    "error": str(e),
                    "error_code": "NOTIFICATION_ERROR",
                },
            )
            return NotificationResult.failure_result(
                message=f"通知处理失败: {e!s}",
                error_code="NOTIFICATION_ERROR",
            )
