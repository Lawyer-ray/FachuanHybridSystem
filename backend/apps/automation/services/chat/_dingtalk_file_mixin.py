"""钉钉文件上传与发送 Mixin

本模块负责钉钉文件上传和文件消息发送。

API文档参考：
- 上传媒体文件：https://open.dingtalk.com/document/isvapp/upload-media-files
- 发送文件到指定会话：https://open.dingtalk.com/document/isvapp/send-file-to-the-specified-conversation
"""

import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ConfigurationException, MessageSendException

from .base import ChatResult

logger = logging.getLogger(__name__)


class DingtalkFileMixin:
    """负责钉钉文件上传和文件消息发送"""

    config: dict[str, Any]

    def is_available(self) -> bool:  # 由 DingtalkTokenMixin 提供
        raise NotImplementedError

    def _get_access_token(self) -> str:  # 由 DingtalkTokenMixin 提供
        raise NotImplementedError

    def send_file(self, chat_id: str, file_path: str) -> ChatResult:
        """发送文件到群聊（上传媒体文件 -> 发送文件到指定会话）"""
        if not self.is_available():
            raise ConfigurationException(
                message=_("钉钉配置不完整，无法发送文件"),
                platform="dingtalk",
                missing_config="APP_KEY, APP_SECRET",
            )

        if not Path(file_path).exists():
            raise MessageSendException(
                message=f"文件不存在: {file_path}", platform="dingtalk", chat_id=chat_id, errors={"file_path": file_path}
            )

        try:
            media_id = self._upload_media(file_path)
            return self._send_file_message(chat_id, media_id, file_path)
        except MessageSendException:
            raise
        except Exception as e:
            logger.error(f"发送钉钉文件时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"发送文件时发生未知错误: {e!s}",
                platform="dingtalk",
                chat_id=chat_id,
                errors={"original_error": str(e), "file_path": file_path},
            ) from e

    def _upload_media(self, file_path: str) -> str:
        """上传媒体文件到钉钉并获取 media_id

        POST https://oapi.dingtalk.com/media/upload?access_token=xxx&type=file
        """
        try:
            access_token = self._get_access_token()
            url = f"https://oapi.dingtalk.com/media/upload?access_token={access_token}&type=file"

            file_name = Path(file_path).name

            with open(file_path, "rb") as file:
                files = {"media": (file_name, file, self._get_mime_type(file_path))}
                timeout = self.config.get("TIMEOUT", 30)
                response = httpx.post(url, files=files, timeout=timeout)
                response.raise_for_status()

            resp_data = response.json()

            errcode = resp_data.get("errcode", 0)
            if errcode != 0:
                error_msg = resp_data.get("errmsg", "未知错误")
                logger.error(f"上传钉钉媒体文件失败: {error_msg} (errcode: {errcode})")
                raise MessageSendException(
                    message=f"文件上传失败: {error_msg}",
                    platform="dingtalk",
                    errors={"api_response": resp_data, "file_path": file_path},
                )

            media_id: str | None = resp_data.get("media_id")

            if not media_id:
                raise MessageSendException(
                    message=_("API 响应中缺少 media_id"),
                    platform="dingtalk",
                    errors={"api_response": resp_data},
                )

            logger.debug(f"成功上传媒体文件到钉钉: {file_name} (media_id: {media_id})")
            return media_id

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"上传钉钉媒体文件网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"文件上传网络请求失败: {e!s}",
                platform="dingtalk",
                errors={"original_error": str(e), "file_path": file_path},
            ) from e
        except Exception as e:
            logger.error(f"上传钉钉媒体文件时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"文件上传时发生未知错误: {e!s}",
                platform="dingtalk",
                errors={"original_error": str(e), "file_path": file_path},
            ) from e

    def _send_file_message(self, chat_id: str, media_id: str, file_path: str) -> ChatResult:
        """发送文件消息到指定会话

        POST https://api.dingtalk.com/v1.0/chat/fileMessages
        使用新版 API，请求头 x-acs-dingtalk-access-token
        """
        try:
            access_token = self._get_access_token()
            url = "https://api.dingtalk.com/v1.0/chat/fileMessages"
            headers = {
                "x-acs-dingtalk-access-token": access_token,
                "Content-Type": "application/json",
            }

            file_name = Path(file_path).name
            payload = {
                "chatId": chat_id,
                "mediaId": media_id,
                "fileName": file_name,
            }

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            logger.info(f"成功发送钉钉文件到群聊: {chat_id} (文件: {file_name})")

            return ChatResult(success=True, chat_id=chat_id, message=f"文件发送成功: {file_name}", raw_response=data)

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"发送钉钉文件消息网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"发送文件消息网络请求失败: {e!s}",
                platform="dingtalk",
                chat_id=chat_id,
                errors={"original_error": str(e), "media_id": media_id, "file_path": file_path},
            ) from e

    def _get_mime_type(self, file_path: str) -> str:
        """根据文件扩展名确定 MIME 类型"""
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"
