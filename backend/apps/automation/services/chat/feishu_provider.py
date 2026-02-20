"""
飞书群聊提供者实现

本模块实现了飞书平台的群聊操作，包括群聊创建、消息发送、文件上传等功能。
使用飞书开放平台API，支持企业内部群聊管理。

API文档参考：
- 飞书开放平台：https://open.feishu.cn/
- 群聊管理：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat
- 消息发送：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message

配置要求：
- FEISHU.APP_ID: 飞书应用ID
- FEISHU.APP_SECRET: 飞书应用密钥
- FEISHU.TIMEOUT: API请求超时时间（可选，默认30秒）
"""

from django.utils.translation import gettext_lazy as _
import json
import logging
from datetime import datetime
from typing import Any

import httpx

from apps.core.enums import ChatPlatform
from apps.core.exceptions import (
    ChatCreationException,
    ConfigurationException,
    MessageSendException,
    OwnerSettingException,
)

from ._feishu_file_mixin import FeishuFileMixin
from ._feishu_owner_mixin import FeishuOwnerMixin
from ._feishu_token_mixin import FeishuTokenMixin
from .base import ChatProvider, ChatResult, MessageContent
from .owner_config_manager import OwnerConfigManager

logger = logging.getLogger(__name__)


class FeishuChatProvider(FeishuTokenMixin, FeishuFileMixin, FeishuOwnerMixin, ChatProvider):
    """飞书群聊提供者

    实现飞书平台的群聊操作，包括：
    - 创建群聊
    - 发送文本消息
    - 发送文件消息
    - 获取群聊信息

    使用飞书开放平台API，需要配置应用ID和密钥。
    """

    BASE_URL = "https://open.feishu.cn/open-apis"

    ENDPOINTS: dict[str, str] = {
        "tenant_access_token": "/auth/v3/tenant_access_token/internal",
        "create_chat": "/im/v1/chats",
        "send_message": "/im/v1/messages",
        "upload_file": "/im/v1/files",
        "get_chat": "/im/v1/chats/{chat_id}",
    }

    def __init__(self) -> None:
        self.config = self._load_config()
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        self.owner_config = OwnerConfigManager()

        if not self.is_available():
            logger.warning("飞书群聊提供者配置不完整，某些功能可能不可用")

    @property
    def platform(self) -> ChatPlatform:
        return ChatPlatform.FEISHU

    def _build_owner_payload(self, effective_owner_id: str, payload: dict[str, Any]) -> None:
        """将群主 ID 写入请求体"""
        if self.owner_config.is_validation_enabled():
            try:
                self.owner_config.validate_owner_id_strict(effective_owner_id)
            except Exception as e:
                logger.warning(f"群主ID验证失败，继续使用: {effective_owner_id}, 错误: {e!s}")

        if effective_owner_id.startswith("on_"):
            open_id = self._convert_union_id_to_open_id(effective_owner_id)
            if open_id:
                payload["owner_id"] = open_id
                payload["user_id_list"] = [open_id]
                logger.debug(f"转换union_id为open_id: {effective_owner_id} -> {open_id}")
            else:
                logger.warning(f"无法转换union_id为open_id: {effective_owner_id}")
        else:
            payload["owner_id"] = effective_owner_id
            payload["user_id_list"] = [effective_owner_id]

    def _raise_feishu_api_error(
        self,
        data: dict[str, Any],
        chat_name: str,
        owner_id: str | None,
        effective_owner_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        """根据飞书 API 错误码抛出对应异常"""
        error_msg = data.get("msg", "未知错误")
        error_code = str(data.get("code"))
        logger.error(f"创建飞书群聊失败: {error_msg} (code: {error_code})")
        logger.error(f"完整响应: {data}")

        exc_or_class = self._classify_feishu_error(error_code, error_msg)
        errors = {
            "api_response": data,
            "chat_name": chat_name,
            "specified_owner_id": owner_id,
            "effective_owner_id": effective_owner_id,
            "request_payload": payload,
        }

        if isinstance(exc_or_class, OwnerSettingException):
            exc_or_class.platform = "feishu"
            exc_or_class.owner_id = effective_owner_id
            exc_or_class.errors = errors
            raise exc_or_class
        raise exc_or_class(
            message=f"创建群聊失败: {error_msg}",
            platform="feishu",
            error_code=error_code,
            errors=errors,
        )

    def create_chat(self, chat_name: str, owner_id: str | None = None) -> ChatResult:
        """创建群聊

        Requirements: 1.1, 1.4
        """
        if not self.is_available():
            raise ConfigurationException(
                message=_("飞书配置不完整，无法创建群聊"), platform="feishu", missing_config="APP_ID, APP_SECRET"
            )

        effective_owner_id: str | None = None
        try:
            effective_owner_id = self.owner_config.get_effective_owner_id(owner_id)
            logger.info(f"创建飞书群聊: {chat_name}, 指定群主: {owner_id}, 有效群主: {effective_owner_id}")

            access_token = self._get_tenant_access_token()
            url = f"{self.BASE_URL}{self.ENDPOINTS['create_chat']}"
            params = {"user_id_type": "open_id"}
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=utf-8"}

            payload: dict[str, Any] = {
                "name": chat_name,
                "chat_mode": "group",
                "chat_type": "private",
                "add_member_permission": "all_members",
                "share_card_permission": "allowed",
                "at_all_permission": "all_members",
                "group_message_type": "chat",
                "description": f"案件群聊: {chat_name}",
            }

            if effective_owner_id:
                self._build_owner_payload(effective_owner_id, payload)

            logger.debug(f"创建飞书群聊请求URL: {url}, 参数: {params}, 请求体: {payload}")

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, params=params, json=payload, headers=headers, timeout=timeout)
            logger.debug(f"飞书API响应状态码: {response.status_code}, 内容: {response.text}")
            response.raise_for_status()

            data = response.json()
            logger.debug(f"飞书API响应数据: {data}")

            if data.get("code") != 0:
                self._raise_feishu_api_error(data, chat_name, owner_id, effective_owner_id, payload)

            chat_data = data.get("data", {})
            chat_id = chat_data.get("chat_id")
            if not chat_id:
                raise ChatCreationException(
                    message=_("API响应中缺少群聊ID"), platform="feishu", errors={"api_response": data}
                )

            logger.info(f"成功创建飞书群聊: {chat_name} (ID: {chat_id}), 群主: {effective_owner_id}")

            result = ChatResult(
                success=True, chat_id=chat_id, chat_name=chat_name, message=str(_("群聊创建成功")), raw_response=data
            )
            if result.raw_response:
                result.raw_response["owner_info"] = {
                    "specified_owner_id": owner_id,
                    "effective_owner_id": effective_owner_id,
                    "owner_set": bool(effective_owner_id),
                }
            return result

        except ChatCreationException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"创建飞书群聊网络请求失败: {e!s}")
            from apps.core.exceptions import owner_network_error

            raise owner_network_error(
                message=f"网络请求失败: {e!s}",
                platform="feishu",
                owner_id=effective_owner_id,
                network_error=str(e),
                errors={"original_error": str(e), "chat_name": chat_name, "specified_owner_id": owner_id},
            ) from e
        except Exception as e:
            logger.error(f"创建飞书群聊时发生未知错误: {e!s}")
            raise ChatCreationException(
                message=f"创建群聊时发生未知错误: {e!s}",
                platform="feishu",
                errors={"original_error": str(e), "chat_name": chat_name, "specified_owner_id": owner_id},
            ) from e

    def send_message(self, chat_id: str, content: MessageContent) -> ChatResult:
        """发送消息到群聊"""
        if not self.is_available():
            raise ConfigurationException(
                message=_("飞书配置不完整，无法发送消息"), platform="feishu", missing_config="APP_ID, APP_SECRET"
            )

        try:
            access_token = self._get_tenant_access_token()
            url = f"{self.BASE_URL}{self.ENDPOINTS['send_message']}"
            params = {"receive_id_type": "chat_id"}
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

            message_text = self._build_simple_text_message(content)
            payload = {"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": message_text})}

            logger.debug(f"发送飞书消息请求URL: {url}")

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, params=params, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            if data.get("code") != 0:
                error_msg = data.get("msg", "未知错误")
                error_code = str(data.get("code"))
                logger.error(f"发送飞书消息失败: {error_msg} (code: {error_code})")
                raise MessageSendException(
                    message=f"发送消息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    chat_id=chat_id,
                    errors={"api_response": data, "content": content.__dict__, "request_payload": payload},
                )

            message_data = data.get("data", {})
            message_id = message_data.get("message_id")
            logger.info(f"成功发送飞书消息到群聊: {chat_id} (消息ID: {message_id})")

            return ChatResult(success=True, chat_id=chat_id, message=str(_("消息发送成功")), raw_response=data)

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"发送飞书消息网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"网络请求失败: {e!s}",
                platform="feishu",
                chat_id=chat_id,
                errors={"original_error": str(e), "content": content.__dict__},
            ) from e
        except Exception as e:
            logger.error(f"发送飞书消息时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"发送消息时发生未知错误: {e!s}",
                platform="feishu",
                chat_id=chat_id,
                errors={"original_error": str(e), "content": content.__dict__},
            ) from e

    def _build_simple_text_message(self, content: MessageContent) -> str:
        """构建简单文本消息"""
        message_parts = []
        if content.title:
            message_parts.append(f"📋 {content.title}")
        if content.text:
            message_parts.append(content.text)
        return "\n\n".join(message_parts) if message_parts else "空消息"

    def _build_rich_text_message(self, content: MessageContent) -> dict[str, Any]:
        """构建飞书富文本消息格式（保留用于未来需求）"""
        elements = []
        if content.title:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{content.title}**"}})
        if content.text:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content.text}})
        if content.title and content.text:
            elements.insert(1, {"tag": "hr"})
        return {"elements": elements}
