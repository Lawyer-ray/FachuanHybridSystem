"""
短信通知服务

本模块实现短信通知的业务逻辑，专门负责发送案件群聊通知。
从 CourtSMSService 中解耦出来，遵循单一职责原则。

设计原则：
- 单一职责：专注于通知发送逻辑
- 依赖注入：支持构造函数注入和延迟加载
- 错误处理：失败时返回 False，不抛出异常
- 日志记录：详细记录操作过程和错误信息

主要功能：
- 发送案件群聊通知
- 获取或创建群聊
- 处理通知失败场景
"""

import logging
from typing import TYPE_CHECKING

from apps.automation.models import CourtSMS
from apps.core.enums import ChatPlatform
from apps.core.interfaces import ICaseChatService, ServiceLocator

if TYPE_CHECKING:
    from apps.cases.models import CaseChat

logger = logging.getLogger(__name__)


class SMSNotificationService:
    """短信通知服务 - 发送案件群聊通知

    负责将短信内容和文书附件发送到案件群聊。
    支持依赖注入和延迟加载模式。

    主要职责：
    - 检查案件群聊是否存在，不存在则创建
    - 发送文书通知到群聊
    - 处理通知失败场景
    - 记录操作日志
    """

    def __init__(
        self,
        case_chat_service: ICaseChatService | None = None,
    ):
        """初始化短信通知服务

        Args:
            case_chat_service: 案件群聊服务实例（可选，支持依赖注入）
        """
        self._case_chat_service = case_chat_service
        logger.debug("SMSNotificationService 初始化完成")

    @property
    def case_chat_service(self) -> ICaseChatService:
        """延迟加载案件群聊服务

        如果构造函数中未注入服务实例，则通过 ServiceLocator 获取。

        Returns:
            ICaseChatService: 案件群聊服务实例
        """
        if self._case_chat_service is None:
            self._case_chat_service = ServiceLocator.get_case_chat_service()
        return self._case_chat_service

    def send_case_chat_notification(self, sms: CourtSMS, document_paths: list[str] | None = None) -> bool:
        """发送案件群聊通知

        根据 Requirements 3.2, 3.3, 3.4 实现：
        1. 检查案件是否存在指定平台的群聊
        2. 如果不存在则自动创建群聊
        3. 将文书内容和短信内容推送到群聊
        4. 处理错误并记录日志，失败时返回 False 而不抛出异常

        Args:
            sms: CourtSMS 实例（必须已绑定案件）
            document_paths: 文书文件路径列表（可选）

        Returns:
            bool: 是否发送成功

        Requirements: 3.2, 3.3, 3.4
        """
        if not sms.case:
            logger.warning(f"短信未绑定案件，无法发送群聊通知: SMS ID={sms.id}")
            return False

        try:
            # 获取案件群聊服务
            chat_service = self.case_chat_service

            # 默认使用飞书平台（可以从配置中读取）
            platform = ChatPlatform.FEISHU

            logger.info(f"开始发送案件群聊通知: SMS ID={sms.id}, Case ID={sms.case.id}, Platform={platform.value}")  # type: ignore[attr-defined]

            # Requirements 3.2: 检查群聊是否存在，不存在则自动创建
            try:
                chat = chat_service.get_or_create_chat(  # type: ignore[attr-defined]
                    case_id=sms.case.id,  # type: ignore[attr-defined]
                    platform=platform,
                )
                logger.info(f"获取或创建群聊成功: SMS ID={sms.id}, Chat ID={chat.chat_id}")

            except Exception as e:
                # Requirements 3.4: 自动创建群聊失败时记录错误日志，返回 False
                logger.error(f"获取或创建群聊失败: SMS ID={sms.id}, Case ID={sms.case.id}, 错误: {e!s}")  # type: ignore[attr-defined]
                return False

            # Requirements 3.3: 将文书内容和短信内容推送到群聊
            try:
                result = chat_service.send_document_notification(  # type: ignore[attr-defined]
                    case_id=sms.case.id,  # type: ignore[attr-defined]
                    sms_content=sms.content,
                    document_paths=document_paths or [],
                    platform=platform,
                    title="📋 法院文书通知",
                )

                if result.success:
                    logger.info(f"案件群聊通知发送成功: SMS ID={sms.id}, Chat ID={chat.chat_id}")
                    return True
                else:
                    logger.warning(
                        f"案件群聊通知发送失败: SMS ID={sms.id}, Chat ID={chat.chat_id}, 错误: {result.message}"
                    )
                    return False

            except Exception as e:
                # Requirements 3.4: 消息发送失败时记录错误日志，返回 False
                logger.error(f"发送案件群聊通知失败: SMS ID={sms.id}, Chat ID={chat.chat_id}, 错误: {e!s}")
                return False

        except ImportError as e:
            # Requirements 3.4: 导入错误时记录日志，返回 False
            logger.error(f"无法导入 CaseChatService: {e!s}")
            return False
        except Exception as e:
            # Requirements 3.4: 其他异常时记录日志，返回 False
            logger.error(f"案件群聊通知处理失败: SMS ID={sms.id}, 错误: {e!s}")
            return False

    def _get_or_create_chat(self, case_id: int, platform: ChatPlatform) -> "CaseChat":
        """获取或创建群聊

        内部辅助方法，用于获取或创建指定案件和平台的群聊。

        Args:
            case_id: 案件ID
            platform: 群聊平台

        Returns:
            CaseChat: 群聊实例

        Raises:
            Exception: 群聊创建失败时抛出异常
        """
        return self.case_chat_service.get_or_create_chat(  # type: ignore[attr-defined, no-any-return]
            case_id=case_id, platform=platform
        )
