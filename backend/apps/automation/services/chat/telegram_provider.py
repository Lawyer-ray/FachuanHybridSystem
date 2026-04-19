"""Telegram 群聊提供者实现

本模块实现了 Telegram 平台的群聊操作，包括话题创建、消息发送、文件上传等功能。

设计说明：
  标准的 Telegram Bot API 无法主动创建群组。为兼容"一案一群"语义，
  采用**超级群组论坛(Topic)模式**：
  - 管理员预先创建一个 Telegram 超级群组并开启论坛功能
  - 每个案件在该群组中创建一个 Topic（论坛话题），等同于"一案一群"
  - create_chat → createForumTopic（创建话题）
  - 消息/文件发送时携带 message_thread_id 指向对应话题

  这种方案避免了需要 MTProto/userbot 的复杂性，且完全兼容现有的一案一群语义。

API文档参考：
- Telegram Bot API：https://core.telegram.org/bots/api
- createForumTopic：https://core.telegram.org/bots/api#createforumtopic
- sendMessage：https://core.telegram.org/bots/api#sendmessage
- getChat：https://core.telegram.org/bots/api#getchat

配置要求：
- TELEGRAM.BOT_TOKEN: Telegram Bot Token（从 @BotFather 获取）
- TELEGRAM.SUPERGROUP_ID: 预建的超级群组 ID（用作论坛容器）
- TELEGRAM.TIMEOUT: API请求超时时间（可选，默认30秒）
"""

import logging
from typing import Any

import httpx
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import (
    ChatCreationException,
    ChatProviderException,
    ConfigurationException,
    MessageSendException,
)
from apps.core.models.enums import ChatPlatform

from ._telegram_file_mixin import TelegramFileMixin
from ._telegram_token_mixin import TelegramTokenMixin
from .base import ChatProvider, ChatResult, MessageContent

logger = logging.getLogger(__name__)


class TelegramProvider(TelegramTokenMixin, TelegramFileMixin, ChatProvider):
    """Telegram 群聊提供者

    实现 Telegram 平台的群聊操作，包括：
    - 创建话题（createForumTopic，等同于一案一群）
    - 发送文本消息（带话题 thread_id）
    - 发送文件消息（带话题 thread_id）
    - 获取群聊/话题信息

    使用 Telegram Bot API，需要配置 Bot Token 和超级群组 ID。
    """

    def __init__(self) -> None:
        self.config = self._load_config()

        if not self.is_available():
            logger.warning("Telegram 群聊提供者配置不完整，某些功能可能不可用")

    @property
    def platform(self) -> ChatPlatform:
        return ChatPlatform.TELEGRAM

    def create_chat(self, chat_name: str, owner_id: str | None = None) -> ChatResult:
        """创建群聊（在超级群组中创建论坛话题）

        使用 createForumTopic API 在预建的超级群组中创建话题。
        每个话题等同于一个"案件群聊"。

        API: POST https://api.telegram.org/bot{token}/createForumTopic

        Args:
            chat_name: 话题名称（通常为案件名称）
            owner_id: 保留参数，Telegram 不支持指定群主

        Returns:
            ChatResult: chat_id 格式为 "{supergroup_id}:{thread_id}"，
                       便于后续消息发送时自动携带 message_thread_id
        """
        if not self.is_available():
            raise ConfigurationException(
                message=_("Telegram 配置不完整，无法创建话题"),
                platform="telegram",
                missing_config="BOT_TOKEN, SUPERGROUP_ID",
            )

        try:
            supergroup_id = self.config.get("SUPERGROUP_ID")
            logger.info(f"创建 Telegram 论坛话题: {chat_name}, 超级群组: {supergroup_id}")

            url = self._get_bot_api_url("createForumTopic")
            payload = {
                "chat_id": supergroup_id,
                "name": chat_name,
            }

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                error_msg = data.get("description", "未知错误")
                error_code = data.get("error_code", "unknown")
                logger.error(f"创建 Telegram 论坛话题失败: {error_msg} (error_code: {error_code})")
                raise ChatCreationException(
                    message=f"创建话题失败: {error_msg}",
                    platform="telegram",
                    error_code=str(error_code),
                    errors={
                        "api_response": data,
                        "chat_name": chat_name,
                        "supergroup_id": str(supergroup_id),
                    },
                )

            result_data = data.get("result", {})
            thread_id = result_data.get("message_thread_id")

            if not thread_id:
                raise ChatCreationException(
                    message=_("API 响应中缺少话题 ID"),
                    platform="telegram",
                    errors={"api_response": data},
                )

            # 组合 chat_id 格式: supergroup_id:thread_id
            # 后续消息发送时自动解析并携带 message_thread_id
            combined_chat_id = f"{supergroup_id}:{thread_id}"

            logger.info(f"成功创建 Telegram 论坛话题: {chat_name} (thread_id: {thread_id})")

            # 发送初始消息到话题
            self._send_initial_message(combined_chat_id, chat_name)

            result = ChatResult(
                success=True, chat_id=combined_chat_id, chat_name=chat_name, message=str(_("话题创建成功")), raw_response=data
            )
            if result.raw_response:
                result.raw_response["topic_info"] = {
                    "supergroup_id": str(supergroup_id),
                    "thread_id": thread_id,
                    "combined_chat_id": combined_chat_id,
                }
            return result

        except ChatCreationException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"创建 Telegram 论坛话题网络请求失败: {e!s}")
            raise ChatCreationException(
                message=f"网络请求失败: {e!s}",
                platform="telegram",
                errors={"original_error": str(e), "chat_name": chat_name},
            ) from e
        except Exception as e:
            logger.error(f"创建 Telegram 论坛话题时发生未知错误: {e!s}")
            raise ChatCreationException(
                message=f"创建话题时发生未知错误: {e!s}",
                platform="telegram",
                errors={"original_error": str(e), "chat_name": chat_name},
            ) from e

    def send_message(self, chat_id: str, content: MessageContent) -> ChatResult:
        """发送消息到群聊

        使用 sendMessage API 发送消息。
        如果 chat_id 包含 topic 标识（格式: chat_id:thread_id），
        则同时携带 message_thread_id 参数以发送到指定话题。

        API: POST https://api.telegram.org/bot{token}/sendMessage
        """
        if not self.is_available():
            raise ConfigurationException(
                message=_("Telegram 配置不完整，无法发送消息"),
                platform="telegram",
                missing_config="BOT_TOKEN",
            )

        try:
            url = self._get_bot_api_url("sendMessage")

            message_text = self._build_text_message(content)
            # 解析 chat_id 和 message_thread_id
            target_chat_id, message_thread_id = self._parse_chat_id(chat_id)

            payload: dict[str, Any] = {
                "chat_id": target_chat_id,
                "text": message_text,
            }
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                error_msg = data.get("description", "未知错误")
                error_code = data.get("error_code", "unknown")
                logger.error(f"发送 Telegram 消息失败: {error_msg} (error_code: {error_code})")
                raise MessageSendException(
                    message=f"发送消息失败: {error_msg}",
                    platform="telegram",
                    chat_id=chat_id,
                    error_code=str(error_code),
                    errors={"api_response": data},
                )

            message_data = data.get("result", {})
            message_id = message_data.get("message_id")
            logger.info(f"成功发送 Telegram 消息到群聊: {chat_id} (消息ID: {message_id})")

            return ChatResult(success=True, chat_id=chat_id, message=str(_("消息发送成功")), raw_response=data)

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"发送 Telegram 消息网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"网络请求失败: {e!s}",
                platform="telegram",
                chat_id=chat_id,
                errors={"original_error": str(e)},
            ) from e
        except Exception as e:
            logger.error(f"发送 Telegram 消息时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"发送消息时发生未知错误: {e!s}",
                platform="telegram",
                chat_id=chat_id,
                errors={"original_error": str(e)},
            ) from e

    def get_chat_info(self, chat_id: str) -> ChatResult:
        """获取群聊信息

        使用 getChat API 获取群组信息。
        对于话题模式，还会尝试获取话题信息。

        API: POST https://api.telegram.org/bot{token}/getChat
        """
        if not self.is_available():
            raise ConfigurationException(
                message=_("Telegram 配置不完整，无法获取群聊信息"),
                platform="telegram",
                missing_config="BOT_TOKEN",
            )

        try:
            # 解析 chat_id（只取群组 ID 部分）
            target_chat_id, message_thread_id = self._parse_chat_id(chat_id)

            url = self._get_bot_api_url("getChat")
            payload = {"chat_id": target_chat_id}

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                error_msg = data.get("description", "未知错误")
                error_code = data.get("error_code", "unknown")
                logger.error(f"获取 Telegram 群聊信息失败: {error_msg} (error_code: {error_code})")
                raise ChatProviderException(
                    message=f"获取群聊信息失败: {error_msg}",
                    platform="telegram",
                    error_code=str(error_code),
                    errors={"api_response": data, "chat_id": chat_id},
                )

            chat_data = data.get("result", {})
            chat_name = chat_data.get("title", "")

            # 如果有话题 ID，在 raw_response 中附加话题信息
            result_data = dict(data)
            if message_thread_id:
                result_data["topic_info"] = {
                    "message_thread_id": message_thread_id,
                    "is_topic": True,
                }

            logger.debug(f"成功获取 Telegram 群聊信息: {target_chat_id} (名称: {chat_name})")

            return ChatResult(
                success=True,
                chat_id=chat_id,
                chat_name=chat_name,
                message=str(_("获取群聊信息成功")),
                raw_response=result_data,
            )

        except ChatProviderException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"获取 Telegram 群聊信息网络请求失败: {e!s}")
            raise ChatProviderException(
                message=f"网络请求失败: {e!s}",
                platform="telegram",
                errors={"original_error": str(e), "chat_id": chat_id},
            ) from e
        except Exception as e:
            logger.error(f"获取 Telegram 群聊信息时发生未知错误: {e!s}")
            raise ChatProviderException(
                message=f"获取群聊信息时发生未知错误: {e!s}",
                platform="telegram",
                errors={"original_error": str(e), "chat_id": chat_id},
            ) from e

    def _build_text_message(self, content: MessageContent) -> str:
        """构建文本消息"""
        message_parts = []
        if content.title:
            message_parts.append(f"📋 {content.title}")
        if content.text:
            message_parts.append(content.text)
        return "\n\n".join(message_parts) if message_parts else "空消息"

    def _send_initial_message(self, chat_id: str, chat_name: str) -> None:
        """新话题创建后发送首条消息"""
        try:
            initial_content = MessageContent(
                title="话题已创建",
                text=f"案件论坛话题「{chat_name}」已创建，后续法院文书通知将在此话题推送。",
            )
            self.send_message(chat_id, initial_content)
            logger.debug(f"已发送 Telegram 初始消息: {chat_id}")
        except Exception as e:
            logger.warning(f"发送 Telegram 初始消息失败（不影响主流程）: {chat_id}, 错误: {e!s}")
