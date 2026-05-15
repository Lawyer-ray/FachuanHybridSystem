"""Telegram 文件发送 Mixin

本模块负责 Telegram 文件上传和发送。

API文档参考：
- sendDocument：https://core.telegram.org/bots/api#senddocument
- inputFile：https://core.telegram.org/bots/api#inputfile
"""

import logging
from pathlib import Path
from typing import Any

import httpx
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ConfigurationException, MessageSendException

from .base import ChatResult

logger = logging.getLogger(__name__)


class TelegramFileMixin:
    """负责 Telegram 文件上传和发送"""

    config: dict[str, Any]

    def is_available(self) -> bool:  # 由 TelegramTokenMixin 提供
        raise NotImplementedError

    def _get_bot_api_url(self, method: str) -> str:  # 由 TelegramTokenMixin 提供
        raise NotImplementedError

    def send_file(self, chat_id: str, file_path: str) -> ChatResult:
        """发送文件到群聊

        Telegram 使用 sendDocument API 直接发送文件。
        如果 chat_id 包含 topic 标识（格式: chat_id:thread_id），
        则同时携带 message_thread_id 参数以发送到指定话题。
        """
        if not self.is_available():
            raise ConfigurationException(
                message=_("Telegram 配置不完整，无法发送文件"),
                platform="telegram",
                missing_config="BOT_TOKEN",
            )

        if not Path(file_path).exists():
            raise MessageSendException(
                message=f"文件不存在: {file_path}", platform="telegram", chat_id=chat_id, errors={"file_path": file_path}
            )

        try:
            return self._send_document(chat_id, file_path)
        except MessageSendException:
            raise
        except Exception as e:
            logger.error(f"发送 Telegram 文件时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"发送文件时发生未知错误: {e!s}",
                platform="telegram",
                chat_id=chat_id,
                errors={"original_error": str(e), "file_path": file_path},
            ) from e

    def _send_document(self, chat_id: str, file_path: str) -> ChatResult:
        """使用 sendDocument API 发送文件

        POST https://api.telegram.org/bot{token}/sendDocument
        """
        try:
            url = self._get_bot_api_url("sendDocument")

            file_name = Path(file_path).name
            # 解析 chat_id 和 message_thread_id
            target_chat_id, message_thread_id = self._parse_chat_id(chat_id)

            with open(file_path, "rb") as file:
                files = {"document": (file_name, file)}
                data: dict[str, Any] = {"chat_id": target_chat_id}
                if message_thread_id:
                    data["message_thread_id"] = message_thread_id

                timeout = self.config.get("TIMEOUT", 30)
                response = httpx.post(url, data=data, files=files, timeout=timeout)
                response.raise_for_status()

            resp_data = response.json()

            if not resp_data.get("ok"):
                error_msg = resp_data.get("description", "未知错误")
                error_code = resp_data.get("error_code", "unknown")
                logger.error(f"发送 Telegram 文件失败: {error_msg} (error_code: {error_code})")
                raise MessageSendException(
                    message=f"文件发送失败: {error_msg}",
                    platform="telegram",
                    chat_id=chat_id,
                    error_code=str(error_code),
                    errors={"api_response": resp_data, "file_path": file_path},
                )

            logger.info(f"成功发送 Telegram 文件到群聊: {chat_id} (文件: {file_name})")

            return ChatResult(success=True, chat_id=chat_id, message=f"文件发送成功: {file_name}", raw_response=resp_data)

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"发送 Telegram 文件网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"文件发送网络请求失败: {e!s}",
                platform="telegram",
                chat_id=chat_id,
                errors={"original_error": str(e), "file_path": file_path},
            ) from e

    def _parse_chat_id(self, chat_id: str) -> tuple[str, int | None]:
        """解析 chat_id，支持 topic 格式

        Telegram 一案一群通过 Topic 实现，chat_id 格式可能为:
        - 纯群组 ID: "123456789"
        - 带话题的格式: "123456789:42" (群组ID:话题ID)

        Returns:
            (target_chat_id, message_thread_id) 元组
        """
        if ":" in chat_id:
            parts = chat_id.split(":", 1)
            try:
                return parts[0], int(parts[1])
            except ValueError:
                logger.warning(f"无法解析 Telegram 话题 ID: {chat_id}")
                return chat_id, None
        return chat_id, None
