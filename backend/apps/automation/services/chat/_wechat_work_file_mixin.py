"""企业微信文件上传与发送 Mixin"""

import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ConfigurationException, MessageSendException

from .base import ChatResult

logger = logging.getLogger(__name__)


class WeChatWorkFileMixin:
    """负责企业微信文件上传和文件消息发送"""

    config: dict[str, Any]

    def is_available(self) -> bool:  # 由 WeChatWorkTokenMixin 提供
        raise NotImplementedError

    def _get_access_token(self) -> str:  # 由 WeChatWorkTokenMixin 提供
        raise NotImplementedError

    def send_file(self, chat_id: str, file_path: str) -> ChatResult:
        """发送文件到群聊（上传临时素材 -> 发送文件消息）"""
        if not self.is_available():
            raise ConfigurationException(
                message=_("企业微信配置不完整，无法发送文件"),
                platform="wechat_work",
                missing_config="CORP_ID, AGENT_ID, SECRET",
            )

        if not Path(file_path).exists():
            raise MessageSendException(
                message=f"文件不存在: {file_path}", platform="wechat_work", chat_id=chat_id, errors={"file_path": file_path}
            )

        try:
            media_id = self._upload_temp_material(file_path)
            return self._send_file_message(chat_id, media_id, file_path)
        except MessageSendException:
            raise
        except Exception as e:
            logger.error(f"发送企业微信文件时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"发送文件时发生未知错误: {e!s}",
                platform="wechat_work",
                chat_id=chat_id,
                errors={"original_error": str(e), "file_path": file_path},
            ) from e

    def _upload_temp_material(self, file_path: str) -> str:
        """上传临时素材到企业微信并获取 media_id"""
        try:
            access_token = self._get_access_token()
            url = f"https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={access_token}&type=file"
            headers = {"Authorization": f"Bearer {access_token}"}

            file_name = Path(file_path).name

            with open(file_path, "rb") as file:
                files = {"media": (file_name, file, self._get_mime_type(file_path))}
                timeout = self.config.get("TIMEOUT", 30)
                response = httpx.post(url, headers=headers, files=files, timeout=timeout)
                response.raise_for_status()

            resp_data = response.json()

            errcode = resp_data.get("errcode", 0)
            if errcode != 0:
                error_msg = resp_data.get("errmsg", "未知错误")
                logger.error(f"上传企业微信临时素材失败: {error_msg} (errcode: {errcode})")
                raise MessageSendException(
                    message=f"文件上传失败: {error_msg}",
                    platform="wechat_work",
                    errors={"api_response": resp_data, "file_path": file_path},
                )

            media_data = resp_data.get("data", resp_data)
            media_id: str | None = media_data.get("media_id")

            if not media_id:
                raise MessageSendException(
                    message=_("API 响应中缺少 media_id"),
                    platform="wechat_work",
                    errors={"api_response": resp_data},
                )

            logger.debug(f"成功上传临时素材到企业微信: {file_name} (media_id: {media_id})")
            return media_id

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"上传企业微信临时素材网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"文件上传网络请求失败: {e!s}",
                platform="wechat_work",
                errors={"original_error": str(e), "file_path": file_path},
            ) from e
        except Exception as e:
            logger.error(f"上传企业微信临时素材时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"文件上传时发生未知错误: {e!s}",
                platform="wechat_work",
                errors={"original_error": str(e), "file_path": file_path},
            ) from e

    def _send_file_message(self, chat_id: str, media_id: str, file_path: str) -> ChatResult:
        """发送文件消息到群聊"""
        try:
            access_token = self._get_access_token()
            url = f"https://qyapi.weixin.qq.com/cgi-bin/appchat/send?access_token={access_token}"
            headers = {"Content-Type": "application/json"}

            file_name = Path(file_path).name
            payload = {
                "chatid": chat_id,
                "msgtype": "file",
                "file": {"media_id": media_id},
            }

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                error_msg = data.get("errmsg", "未知错误")
                logger.error(f"发送企业微信文件消息失败: {error_msg} (errcode: {errcode})")
                raise MessageSendException(
                    message=f"发送文件消息失败: {error_msg}",
                    platform="wechat_work",
                    chat_id=chat_id,
                    errors={"api_response": data, "media_id": media_id, "file_path": file_path},
                )

            logger.info(f"成功发送企业微信文件到群聊: {chat_id} (文件: {file_name})")

            return ChatResult(success=True, chat_id=chat_id, message=f"文件发送成功: {file_name}", raw_response=data)

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"发送企业微信文件消息网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"发送文件消息网络请求失败: {e!s}",
                platform="wechat_work",
                chat_id=chat_id,
                errors={"original_error": str(e), "media_id": media_id, "file_path": file_path},
            ) from e

    def _get_mime_type(self, file_path: str) -> str:
        """根据文件扩展名确定 MIME 类型"""
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"
