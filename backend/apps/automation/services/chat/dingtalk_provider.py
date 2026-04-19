"""钉钉群聊提供者实现

本模块实现了钉钉平台的群聊操作，包括群聊创建、消息发送、文件上传等功能。
使用钉钉开放平台API，支持企业内部群聊管理。

API文档参考：
- 钉钉开放平台：https://open.dingtalk.com/document/isvapp/api-overview
- 群聊会话2.0：https://open.dingtalk.com/document/orgapp/create-group-session
- 机器人发送群聊消息：https://open.dingtalk.com/document/isvapp/send-group-messages
- 查询群信息：https://open.dingtalk.com/document/orgapp/query-group-session

配置要求：
- DINGTALK.APP_KEY: 钉钉应用 App Key
- DINGTALK.APP_SECRET: 钉钉应用 App Secret
- DINGTALK.AGENT_ID: 钉钉应用 Agent ID（发送消息时需要）
- DINGTALK.DEFAULT_OWNER_ID: 默认群主 userid（建群必须）
- DINGTALK.TIMEOUT: API请求超时时间（可选，默认30秒）
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

from ._dingtalk_file_mixin import DingtalkFileMixin
from ._dingtalk_token_mixin import DingtalkTokenMixin
from .base import ChatProvider, ChatResult, MessageContent

logger = logging.getLogger(__name__)


class DingtalkProvider(DingtalkTokenMixin, DingtalkFileMixin, ChatProvider):
    """钉钉群聊提供者

    实现钉钉平台的群聊操作，包括：
    - 创建群聊（会话2.0 API）
    - 发送文本消息
    - 发送文件消息
    - 获取群聊信息

    使用钉钉开放平台API，需要配置 App Key、App Secret 和默认群主。
    """

    # 旧版 API（获取 access_token）
    OAPI_BASE_URL = "https://oapi.dingtalk.com"

    # 新版 API（群聊2.0、消息）
    API_BASE_URL = "https://api.dingtalk.com"

    def __init__(self) -> None:
        self.config = self._load_config()
        self._access_token: str | None = None
        self._token_expires_at: Any = None

        if not self.is_available():
            logger.warning("钉钉群聊提供者配置不完整，某些功能可能不可用")

    @property
    def platform(self) -> ChatPlatform:
        return ChatPlatform.DINGTALK

    def create_chat(self, chat_name: str, owner_id: str | None = None) -> ChatResult:
        """创建群聊

        使用钉钉会话2.0 API创建群聊。
        钉钉建群必须指定群主（owner），如未传入则使用默认群主配置。
        创建后会立即发送首条消息以确保新群在客户端可见。

        API: POST https://api.dingtalk.com/v1.0/chat/groups
        """
        if not self.is_available():
            raise ConfigurationException(
                message=_("钉钉配置不完整，无法创建群聊"),
                platform="dingtalk",
                missing_config="APP_KEY, APP_SECRET, DEFAULT_OWNER_ID",
            )

        effective_owner_id = owner_id or self.config.get("DEFAULT_OWNER_ID")
        if not effective_owner_id:
            raise ChatCreationException(
                message=_("钉钉建群必须指定群主（owner_id）"),
                platform="dingtalk",
                errors={"missing_config": "DEFAULT_OWNER_ID"},
            )

        try:
            logger.info(f"创建钉钉群聊: {chat_name}, 群主: {effective_owner_id}")

            access_token = self._get_access_token()
            url = f"{self.API_BASE_URL}/v1.0/chat/groups"
            headers = {
                "x-acs-dingtalk-access-token": access_token,
                "Content-Type": "application/json",
            }

            payload: dict[str, Any] = {
                "title": chat_name,
                "ownerUserId": effective_owner_id,
                "userIdlist": [effective_owner_id],
                "subadminIds": [],
                "icon": "",
                "searchable": 0,
                "showHistoryPublic": 1,
                "groupMode": 0,
                "mentionAllAuthority": 0,
                "chatBanned": 0,
                "validationRequired": 0,
            }

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            # 钉钉会话2.0 API 成功时直接返回群聊ID
            open_conversation_id = data.get("openConversationId")
            chat_id = data.get("chatId") or open_conversation_id

            if not chat_id:
                # 检查是否有错误码
                error_code = data.get("code")
                error_msg = data.get("message", "未知错误")
                if error_code:
                    raise ChatCreationException(
                        message=f"创建群聊失败: {error_msg}",
                        platform="dingtalk",
                        error_code=str(error_code),
                        errors={
                            "api_response": data,
                            "chat_name": chat_name,
                            "specified_owner_id": owner_id,
                            "effective_owner_id": effective_owner_id,
                        },
                    )
                raise ChatCreationException(
                    message=_("API 响应中缺少群聊ID"),
                    platform="dingtalk",
                    errors={"api_response": data},
                )

            logger.info(f"成功创建钉钉群聊: {chat_name} (ID: {chat_id}), 群主: {effective_owner_id}")

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
            logger.error(f"创建钉钉群聊网络请求失败: {e!s}")
            raise ChatCreationException(
                message=f"网络请求失败: {e!s}",
                platform="dingtalk",
                errors={"original_error": str(e), "chat_name": chat_name},
            ) from e
        except Exception as e:
            logger.error(f"创建钉钉群聊时发生未知错误: {e!s}")
            raise ChatCreationException(
                message=f"创建群聊时发生未知错误: {e!s}",
                platform="dingtalk",
                errors={"original_error": str(e), "chat_name": chat_name},
            ) from e

    def send_message(self, chat_id: str, content: MessageContent) -> ChatResult:
        """发送消息到群聊

        使用机器人发送群聊消息API。
        API: POST https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend
        或者使用旧版: POST https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2
        这里使用会话2.0的机器人消息接口
        """
        if not self.is_available():
            raise ConfigurationException(
                message=_("钉钉配置不完整，无法发送消息"),
                platform="dingtalk",
                missing_config="APP_KEY, APP_SECRET, AGENT_ID",
            )

        try:
            access_token = self._get_access_token()
            agent_id = self.config.get("AGENT_ID")
            if not agent_id:
                raise ConfigurationException(
                    message=_("钉钉 AGENT_ID 未配置，无法发送消息"),
                    platform="dingtalk",
                    missing_config="AGENT_ID",
                )

            url = f"{self.API_BASE_URL}/v1.0/robot/oToMessages/batchSend"
            headers = {
                "x-acs-dingtalk-access-token": access_token,
                "Content-Type": "application/json",
            }

            message_text = self._build_text_message(content)
            payload = {
                "robotCode": agent_id,
                "chatIds": [chat_id],
                "msgKey": "sampleText",
                "msgParam": f'{{"content":"{message_text}"}}',
            }

            logger.debug(f"发送钉钉消息请求: chat_id={chat_id}")

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            # 检查是否有错误
            error_code = data.get("code")
            if error_code and error_code != "OK":
                error_msg = data.get("message", "未知错误")
                logger.error(f"发送钉钉消息失败: {error_msg} (code: {error_code})")
                raise MessageSendException(
                    message=f"发送消息失败: {error_msg}",
                    platform="dingtalk",
                    chat_id=chat_id,
                    error_code=str(error_code),
                    errors={"api_response": data},
                )

            logger.info(f"成功发送钉钉消息到群聊: {chat_id}")

            return ChatResult(success=True, chat_id=chat_id, message=str(_("消息发送成功")), raw_response=data)

        except MessageSendException:
            raise
        except ConfigurationException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"发送钉钉消息网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"网络请求失败: {e!s}",
                platform="dingtalk",
                chat_id=chat_id,
                errors={"original_error": str(e)},
            ) from e
        except Exception as e:
            logger.error(f"发送钉钉消息时发生未知错误: {e!s}")
            raise MessageSendException(
                message=f"发送消息时发生未知错误: {e!s}",
                platform="dingtalk",
                chat_id=chat_id,
                errors={"original_error": str(e)},
            ) from e

    def get_chat_info(self, chat_id: str) -> ChatResult:
        """获取群聊信息

        API: GET https://api.dingtalk.com/v1.0/chat/groups/{chatId}
        """
        if not self.is_available():
            raise ConfigurationException(
                message=_("钉钉配置不完整，无法获取群聊信息"),
                platform="dingtalk",
                missing_config="APP_KEY, APP_SECRET",
            )

        try:
            access_token = self._get_access_token()
            url = f"{self.API_BASE_URL}/v1.0/chat/groups/{chat_id}"
            headers = {
                "x-acs-dingtalk-access-token": access_token,
                "Content-Type": "application/json",
            }

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            # 检查错误
            error_code = data.get("code")
            if error_code and error_code != "OK":
                error_msg = data.get("message", "未知错误")
                logger.error(f"获取钉钉群聊信息失败: {error_msg} (code: {error_code})")
                raise ChatProviderException(
                    message=f"获取群聊信息失败: {error_msg}",
                    platform="dingtalk",
                    error_code=str(error_code),
                    errors={"api_response": data, "chat_id": chat_id},
                )

            chat_name = data.get("title", "")
            logger.debug(f"成功获取钉钉群聊信息: {chat_id} (名称: {chat_name})")

            return ChatResult(
                success=True,
                chat_id=chat_id,
                chat_name=chat_name,
                message=str(_("获取群聊信息成功")),
                raw_response=data,
            )

        except ChatProviderException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"获取钉钉群聊信息网络请求失败: {e!s}")
            raise ChatProviderException(
                message=f"网络请求失败: {e!s}",
                platform="dingtalk",
                errors={"original_error": str(e), "chat_id": chat_id},
            ) from e
        except Exception as e:
            logger.error(f"获取钉钉群聊信息时发生未知错误: {e!s}")
            raise ChatProviderException(
                message=f"获取群聊信息时发生未知错误: {e!s}",
                platform="dingtalk",
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
        """新群创建后发送首条消息，确保群在客户端可见"""
        try:
            initial_content = MessageContent(
                title="群聊已创建",
                text=f"案件群聊「{chat_name}」已创建，后续法院文书通知将在此群推送。",
            )
            self.send_message(chat_id, initial_content)
            logger.debug(f"已发送钉钉群初始消息: {chat_id}")
        except Exception as e:
            logger.warning(f"发送钉钉群初始消息失败（不影响主流程）: {chat_id}, 错误: {e!s}")
