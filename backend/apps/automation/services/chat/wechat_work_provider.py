"""
企业微信群聊提供者实现

本模块实现了企业微信平台的群聊操作，包括群聊创建、消息发送、文件上传等功能。
使用企业微信开放API，支持企业内部群聊管理。

API文档参考：
- 企业微信开放平台：https://developer.work.weixin.qq.com/document/
- 群聊管理：https://developer.work.weixin.qq.com/document/path/99846
- 消息发送：https://developer.work.weixin.qq.com/document/path/99848

配置要求：
- WECHAT_WORK.CORP_ID: 企业微信企业ID
- WECHAT_WORK.AGENT_ID: 应用AgentId
- WECHAT_WORK.SECRET: 应用Secret
- WECHAT_WORK.DEFAULT_OWNER_ID: 默认群主userid（建群必须）
"""

import json
import logging
from typing import Any

import httpx
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import (
    ChatCreationException,
    ConfigurationException,
    MessageSendException,
)
from apps.core.models.enums import ChatPlatform

from ._wechat_work_file_mixin import WeChatWorkFileMixin
from ._wechat_work_token_mixin import WeChatWorkTokenMixin
from .base import ChatProvider, ChatResult, MessageContent

logger = logging.getLogger(__name__)


class WeChatWorkProvider(WeChatWorkTokenMixin, WeChatWorkFileMixin, ChatProvider):
    """企业微信群聊提供者

    实现企业微信平台的群聊操作，包括：
    - 创建群聊
    - 发送文本消息
    - 发送文件消息
    - 获取群聊信息

    使用企业微信开放平台API，需要配置企业ID、应用密钥和默认群主。
    """

    def __init__(self) -> None:
        self.config = self._load_config()
        self._access_token: str | None = None
        self._token_expires_at: Any = None

        if not self.is_available():
            logger.warning("企业微信群聊提供者配置不完整，某些功能可能不可用")

    @property
    def platform(self) -> ChatPlatform:
        return ChatPlatform.WECHAT_WORK

    def create_chat(self, chat_name: str, owner_id: str | None = None) -> ChatResult:
        """创建群聊

        企业微信创建群聊必须指定群主（owner），如未传入则使用默认群主配置。
        创建后会立即发送首条消息以确保新群在客户端可见。
        """
        if not self.is_available():
            raise ConfigurationException(
                message=_("企业微信配置不完整，无法创建群聊"),
                platform="wechat_work",
                missing_config="CORP_ID, AGENT_ID, SECRET, DEFAULT_OWNER_ID",
            )

        effective_owner_id = owner_id or self.config.get("DEFAULT_OWNER_ID")
        if not effective_owner_id:
            raise ChatCreationException(
                message=_("企业微信建群必须指定群主（owner_id）"),
                platform="wechat_work",
                errors={"missing_config": "DEFAULT_OWNER_ID"},
            )

        try:
            logger.info(f"创建企业微信群聊: {chat_name}, 群主: {effective_owner_id}")

            access_token = self._get_access_token()
            url = f"https://qyapi.weixin.qq.com/cgi-bin/appchat/create?access_token={access_token}"
            headers = {"Content-Type": "application/json"}

            payload: dict[str, Any] = {
                "name": chat_name,
                "owner": effective_owner_id,
                "userlist": [effective_owner_id],
                "chatid": f"case_{chat_name[:50]}",
            }

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                error_msg = data.get("errmsg", "未知错误")
                logger.error(f"创建企业微信群聊失败: {error_msg} (errcode: {errcode})")
                raise ChatCreationException(
                    message=f"创建群聊失败: {error_msg}",
                    platform="wechat_work",
                    error_code=str(errcode),
                    errors={
                        "api_response": data,
                        "chat_name": chat_name,
                        "specified_owner_id": owner_id,
                        "effective_owner_id": effective_owner_id,
                    },
                )

            chat_id = data.get("chatid")
            if not chat_id:
                raise ChatCreationException(
                    message=_("API 响应中缺少群聊ID"),
                    platform="wechat_work",
                    errors={"api_response": data},
                )

            logger.info(f"成功创建企业微信群聊: {chat_name} (ID: {chat_id}), 群主: {effective_owner_id}")

            # 新群创建后立即发送首条消息，确保群在客户端可见
            self._send_initial_message(chat_id, chat_name)

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
            logger.error(f"创建企业微信群聊网络请求失败: {e!s}")
            raise ChatCreationException(
                message=f"网络请求失败: {e!s}",
                platform="wechat_work",
                errors={"original_error": str(e), "chat_name": chat_name},
            ) from e
        except Exception as e:
            logger.error(f"创建企业微信群聊时发生未知错误: {e!s}")
            raise ChatCreationException(
                message=f"创建群聊时发生未知错误: {e!s}",
                platform="wechat_work",
                errors={"original_error": str(e), "chat_name": chat_name},
            ) from e

    def send_message(self, chat_id: str, content: MessageContent) -> ChatResult:
        """发送消息到群聊"""
        if not self.is_available():
            raise ConfigurationException(
                message=_("企业微信配置不完整，无法发送消息"),
                platform="wechat_work",
                missing_config="CORP_ID, AGENT_ID, SECRET",
            )

        try:
            access_token = self._get_access_token()
            url = f"https://qyapi.weixin.qq.com/cgi-bin/appchat/send?access_token={access_token}"
            headers = {"Content-Type": "application/json"}

            message_text = self._build_text_message(content)
            payload = {
                "chatid": chat_id,
                "msgtype": "text",
                "text": {"content": message_text},
            }

            logger.debug(f"发送企业微信消息请求: chat_id={chat_id}")

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                error_msg = data.get("errmsg", "未知错误")
                logger.error(f"发送企业微信消息失败: {error_msg} (errcode: {errcode})")
                raise MessageSendException(
                    message=f"发送消息失败: {error_msg}",
                    platform="wechat_work",
                    chat_id=chat_id,
                    error_code=str(errcode),
                    errors={"api_response": data},
                )

            msg_id = data.get("msgid", "")
            logger.info(f"成功发送企业微信消息到群聊: {chat_id} (消息ID: {msg_id})")

            return ChatResult(success=True, chat_id=chat_id, message=str(_("消息发送成功")), raw_response=data)

        except MessageSendException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"发送企业微信消息网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"网络请求失败: {e!s}",
                platform="wechat_work",
                chat_id=chat_id,
                errors={"original_error": str(e)},
            ) from e
        except Exception as e:
            logger.error(f"发送企业微信消息时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"发送消息时发生未知错误: {e!s}",
                platform="wechat_work",
                chat_id=chat_id,
                errors={"original_error": str(e)},
            ) from e

    def get_chat_info(self, chat_id: str) -> ChatResult:
        """获取群聊信息"""
        if not self.is_available():
            raise ConfigurationException(
                message=_("企业微信配置不完整，无法获取群聊信息"),
                platform="wechat_work",
                missing_config="CORP_ID, AGENT_ID, SECRET",
            )

        try:
            access_token = self._get_access_token()
            url = f"https://qyapi.weixin.qq.com/cgi-bin/appchat/get?access_token={access_token}&chatid={chat_id}"
            headers = {"Content-Type": "application/json"}

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                error_msg = data.get("errmsg", "未知错误")
                logger.error(f"获取企业微信群聊信息失败: {error_msg} (errcode: {errcode})")
                return ChatResult(
                    success=False,
                    chat_id=chat_id,
                    message=f"获取群聊信息失败: {error_msg}",
                    error_code=str(errcode),
                    raw_response=data,
                )

            chat_info = data.get("chat_info", {})
            chat_name = chat_info.get("name", "")

            return ChatResult(
                success=True,
                chat_id=chat_id,
                chat_name=chat_name,
                message=str(_("获取群聊信息成功")),
                raw_response=data,
            )

        except Exception as e:
            logger.error(f"获取企业微信群聊信息失败: {e!s}")
            return ChatResult(
                success=False,
                chat_id=chat_id,
                message=f"获取群聊信息失败: {e!s}",
                raw_response={"error": str(e)},
            )

    def _build_text_message(self, content: MessageContent) -> str:
        """构建文本消息"""
        message_parts = []
        if content.title:
            message_parts.append(f"📋 {content.title}")
        if content.text:
            message_parts.append(content.text)
        return "\n\n".join(message_parts) if message_parts else "空消息"

    def _send_initial_message(self, chat_id: str, chat_name: str) -> None:
        """新群创建后发送首条消息，确保群在客户端可见"""
        try:
            initial_content = MessageContent(
                title="群聊已创建",
                text=f"案件群聊「{chat_name}」已创建，后续法院文书通知将在此群推送。",
            )
            self.send_message(chat_id, initial_content)
            logger.debug(f"已发送企业微信群初始消息: {chat_id}")
        except Exception as e:
            logger.warning(f"发送企业微信群初始消息失败（不影响主流程）: {chat_id}, 错误: {e!s}")
