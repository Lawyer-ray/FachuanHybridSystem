"""飞书文件上传与发送 Mixin"""

import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ConfigurationException, MessageSendException

from .base import ChatResult

logger = logging.getLogger(__name__)


class FeishuFileMixin:
    """负责飞书文件上传和文件消息发送"""

    BASE_URL: str
    ENDPOINTS: dict[str, str]
    config: dict[str, Any]

    def is_available(self) -> bool:  # 由 FeishuTokenMixin 提供
        raise NotImplementedError

    def _get_tenant_access_token(self) -> str:  # 由 FeishuTokenMixin 提供
        raise NotImplementedError

    def send_file(self, chat_id: str, file_path: str) -> ChatResult:
        """发送文件到群聊"""
        if not self.is_available():
            raise ConfigurationException(
                message=_("飞书配置不完整，无法发送文件"), platform="feishu", missing_config="APP_ID, APP_SECRET"
            )

        if not Path(file_path).exists():
            raise MessageSendException(
                message=f"文件不存在: {file_path}", platform="feishu", chat_id=chat_id, errors={"file_path": file_path}
            )

        try:
            file_key = self._upload_file(file_path)
            return self._send_file_message(chat_id, file_key, file_path)
        except MessageSendException:
            raise
        except Exception as e:
            logger.error(f"发送飞书文件时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"发送文件时发生未知错误: {e!s}",
                platform="feishu",
                chat_id=chat_id,
                errors={"original_error": str(e), "file_path": file_path},
            ) from e

    def _upload_file(self, file_path: str) -> str:
        """上传文件到飞书并获取 file_key"""
        try:
            access_token = self._get_tenant_access_token()
            url = f"{self.BASE_URL}{self.ENDPOINTS['upload_file']}"
            headers = {"Authorization": f"Bearer {access_token}"}

            file_name = Path(file_path).name
            file_type = self._get_file_type(file_path)

            with open(file_path, "rb") as file:
                files = {"file": (file_name, file, self._get_mime_type(file_path))}
                data: dict[str, str] = {"file_type": file_type, "file_name": file_name}

                timeout = self.config.get("TIMEOUT", 30)
                response = httpx.post(url, headers=headers, files=files, data=data, timeout=timeout)

                if response.status_code >= 400:
                    error_body = response.text
                    logger.error(f"上传飞书文件HTTP错误: status={response.status_code}, 响应体={error_body}, 文件={file_name}")
                    response.raise_for_status()

            resp_data = response.json()

            if resp_data.get("code") != 0:
                error_msg = resp_data.get("msg", "未知错误")
                error_code = str(resp_data.get("code"))
                logger.error(f"上传飞书文件失败: {error_msg} (code: {error_code})")
                raise MessageSendException(
                    message=f"文件上传失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    errors={"api_response": resp_data, "file_path": file_path},
                )

            file_data = resp_data.get("data", {})
            file_key: str | None = file_data.get("file_key")

            if not file_key:
                raise MessageSendException(
                    message=_("API响应中缺少文件key"), platform="feishu", errors={"api_response": resp_data}
                )

            logger.debug(f"成功上传文件到飞书: {file_name} (key: {file_key})")
            return file_key

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"上传飞书文件网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"文件上传网络请求失败: {e!s}",
                platform="feishu",
                errors={"original_error": str(e), "file_path": file_path},
            ) from e
        except Exception as e:
            logger.error(f"上传飞书文件时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"文件上传时发生未知错误: {e!s}",
                platform="feishu",
                errors={"original_error": str(e), "file_path": file_path},
            ) from e

    def _send_file_message(self, chat_id: str, file_key: str, file_path: str) -> ChatResult:
        """发送文件消息"""
        try:
            access_token = self._get_tenant_access_token()
            url = f"{self.BASE_URL}{self.ENDPOINTS['send_message']}"
            params = {"receive_id_type": "chat_id"}
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=utf-8"}

            file_name = Path(file_path).name
            content = {"file_key": file_key}
            payload = {"receive_id": chat_id, "msg_type": "file", "content": json.dumps(content, ensure_ascii=False)}

            logger.debug(f"发送飞书文件消息请求URL: {url}")

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, params=params, json=payload, headers=headers, timeout=timeout)

            if response.status_code >= 400:
                error_body = response.text
                logger.error(f"发送飞书文件消息HTTP错误: status={response.status_code}, 响应体={error_body}, chat_id={chat_id}")
                response.raise_for_status()

            data = response.json()

            if data.get("code") != 0:
                error_msg = data.get("msg", "未知错误")
                error_code = str(data.get("code"))
                logger.error(f"发送飞书文件消息失败: {error_msg} (code: {error_code})")
                raise MessageSendException(
                    message=f"发送文件消息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    chat_id=chat_id,
                    errors={
                        "api_response": data,
                        "file_key": file_key,
                        "file_path": file_path,
                        "request_payload": payload,
                    },
                )

            message_data = data.get("data", {})
            message_id = message_data.get("message_id")
            logger.info(f"成功发送飞书文件到群聊: {chat_id} (文件: {file_name}, 消息ID: {message_id})")

            return ChatResult(success=True, chat_id=chat_id, message=f"文件发送成功: {file_name}", raw_response=data)

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"发送飞书文件消息网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"发送文件消息网络请求失败: {e!s}",
                platform="feishu",
                chat_id=chat_id,
                errors={"original_error": str(e), "file_key": file_key, "file_path": file_path},
            ) from e

    def _get_file_type(self, file_path: str) -> str:
        """根据文件扩展名确定飞书文件类型

        飞书 im/v1/files API 支持的 file_type:
        stream, opus, mp4, pdf, doc, docx, xls, xlsx, ppt, pptx
        其他类型统一使用 stream（二进制流）
        """
        ext = Path(file_path).suffix.lower()
        file_type_mapping = {
            ".pdf": "pdf",
            ".doc": "doc",
            ".docx": "docx",
            ".xls": "xls",
            ".xlsx": "xlsx",
            ".ppt": "ppt",
            ".pptx": "pptx",
            ".mp4": "mp4",
            ".opus": "opus",
        }
        return file_type_mapping.get(ext, "stream")

    def _get_mime_type(self, file_path: str) -> str:
        """根据文件扩展名确定 MIME 类型"""
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"
