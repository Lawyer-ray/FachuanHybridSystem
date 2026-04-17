"""
短信通知服务

本模块实现短信通知的业务逻辑，专门负责发送案件群聊通知。
从 CourtSMSService 中解耦出来，遵循单一职责原则。

设计原则：
- 单一职责：专注于通知发送逻辑
- 依赖注入：支持构造函数注入和延迟加载
- 多平台扇出：发现所有可用平台，逐个发送，聚合结果
- 错误处理：任一平台成功即为成功，全部失败才返回失败
- 日志记录：详细记录操作过程和错误信息

主要功能：
- 多平台群聊通知扇出
- 获取或创建群聊
- 处理通知失败场景
- 聚合多平台通知结果
"""

import logging
from datetime import datetime
from typing import Any

from apps.automation.models import CourtSMS
from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult
from apps.core.interfaces import ICaseChatService, ServiceLocator
from apps.core.models.enums import ChatPlatform

logger = logging.getLogger(__name__)


class SMSNotificationService:
    """短信通知服务 - 多平台群聊通知扇出

    负责将短信内容和文书附件发送到案件群聊。
    支持依赖注入和延迟加载模式。
    自动发现所有可用平台，逐个发送通知，聚合结果。

    主要职责：
    - 发现所有可用的群聊平台
    - 对每个平台：获取或创建群聊 → 发送文本 → 发送文件
    - 聚合多平台通知结果
    - 任一平台成功即为整体成功
    """

    def __init__(
        self,
        case_chat_service: ICaseChatService | None = None,
    ):
        self._case_chat_service = case_chat_service
        logger.debug("SMSNotificationService 初始化完成")

    @property
    def case_chat_service(self) -> ICaseChatService:
        if self._case_chat_service is None:
            self._case_chat_service = ServiceLocator.get_case_chat_service()
        return self._case_chat_service

    def send_case_chat_notification(
        self, sms: CourtSMS, document_paths: list[str] | None = None
    ) -> MultiPlatformNotificationResult:
        """发送案件群聊通知（多平台扇出）

        自动发现所有可用平台，逐个发送通知，聚合结果。
        任一平台成功即为整体成功；全部失败才为失败。

        Args:
            sms: CourtSMS 实例（必须已绑定案件）
            document_paths: 文书文件路径列表（可选）

        Returns:
            MultiPlatformNotificationResult: 多平台通知聚合结果
        """
        if not sms.case:
            error_msg = "短信未绑定案件，无法发送群聊通知"
            logger.warning(f"{error_msg}: SMS ID={sms.id}")
            return MultiPlatformNotificationResult(
                attempts=[
                    PlatformNotificationResult(
                        platform="none",
                        success=False,
                        error=error_msg,
                    )
                ]
            )

        # 发现可用平台
        available_platforms = self._get_available_platforms()
        if not available_platforms:
            error_msg = "没有可用的群聊平台"
            logger.warning(f"{error_msg}: SMS ID={sms.id}")
            return MultiPlatformNotificationResult(
                attempts=[
                    PlatformNotificationResult(
                        platform="none",
                        success=False,
                        error=error_msg,
                    )
                ]
            )

        logger.info(
            f"开始多平台群聊通知: SMS ID={sms.id}, "
            f"Case ID={sms.case.id}, "
            f"可用平台={[p.value for p in available_platforms]}"
        )

        # 顺序扇出
        result = MultiPlatformNotificationResult()
        for platform in available_platforms:
            platform_result = self._notify_single_platform(
                sms=sms,
                platform=platform,
                document_paths=document_paths or [],
            )
            result.attempts.append(platform_result)

            if platform_result.success:
                logger.info(
                    f"平台 {platform.value} 通知成功: SMS ID={sms.id}, Chat ID={platform_result.chat_id}"
                )
            else:
                logger.warning(
                    f"平台 {platform.value} 通知失败: SMS ID={sms.id}, 错误={platform_result.error}"
                )

        # 汇总日志
        if result.any_success:
            logger.info(
                f"多平台通知完成（有成功）: SMS ID={sms.id}, "
                f"成功平台={result.successful_platforms}, "
                f"失败平台={result.failed_platforms}"
            )
        else:
            logger.error(
                f"多平台通知全部失败: SMS ID={sms.id}, "
                f"失败平台={result.failed_platforms}"
            )

        return result

    def _notify_single_platform(
        self,
        sms: CourtSMS,
        platform: ChatPlatform,
        document_paths: list[str],
    ) -> PlatformNotificationResult:
        """对单个平台执行通知流程：获取或创建群聊 → 发送文本 → 发送文件

        Args:
            sms: CourtSMS 实例
            platform: 目标平台
            document_paths: 文书文件路径列表

        Returns:
            PlatformNotificationResult: 单平台通知结果
        """
        chat_id: str | None = None
        try:
            chat_service = self.case_chat_service

            # 1. 获取或创建群聊
            try:
                chat = chat_service.get_or_create_chat(
                    case_id=sms.case.id,
                    platform=platform,
                )
                chat_id = getattr(chat, "chat_id", None)
                logger.info(f"获取或创建群聊成功: SMS ID={sms.id}, Platform={platform.value}, Chat ID={chat_id}")
            except Exception as e:
                error_msg = f"获取或创建群聊失败: {e!s}"
                logger.error(f"{error_msg}: SMS ID={sms.id}, Platform={platform.value}")
                return PlatformNotificationResult(
                    platform=platform.value,
                    success=False,
                    chat_id=chat_id,
                    error=error_msg,
                )

            # 2. 发送文书通知
            try:
                send_result = chat_service.send_document_notification(
                    case_id=sms.case.id,
                    sms_content=sms.content,
                    document_paths=document_paths,
                    platform=platform,
                    title="📋 法院文书通知",
                )

                if send_result.success:
                    now = datetime.now().isoformat()
                    return PlatformNotificationResult(
                        platform=platform.value,
                        success=True,
                        chat_id=chat_id,
                        sent_at=now,
                        file_count=len(document_paths),
                        sent_file_count=len(document_paths),
                    )
                else:
                    error_msg = f"消息发送失败: {getattr(send_result, 'message', '未知错误')}"
                    return PlatformNotificationResult(
                        platform=platform.value,
                        success=False,
                        chat_id=chat_id,
                        file_count=len(document_paths),
                        error=error_msg,
                    )

            except Exception as e:
                error_msg = f"发送通知异常: {e!s}"
                logger.error(f"{error_msg}: SMS ID={sms.id}, Platform={platform.value}, Chat ID={chat_id}")
                return PlatformNotificationResult(
                    platform=platform.value,
                    success=False,
                    chat_id=chat_id,
                    file_count=len(document_paths),
                    error=error_msg,
                )

        except Exception as e:
            error_msg = f"平台通知处理失败: {e!s}"
            logger.error(f"{error_msg}: SMS ID={sms.id}, Platform={platform.value}")
            return PlatformNotificationResult(
                platform=platform.value,
                success=False,
                chat_id=chat_id,
                error=error_msg,
            )

    def _get_available_platforms(self) -> list[ChatPlatform]:
        """获取所有可用的群聊平台"""
        try:
            from apps.automation.services.chat.factory import ChatProviderFactory

            return list(ChatProviderFactory.get_available_platforms())
        except Exception as e:
            logger.warning(f"获取可用平台失败，回退到飞书: {e!s}")
            return [ChatPlatform.FEISHU]
