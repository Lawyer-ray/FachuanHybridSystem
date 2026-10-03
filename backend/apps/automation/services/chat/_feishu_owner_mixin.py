"""飞书群主相关操作 Mixin"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from apps.core.exceptions import (
    ChatCreationException,
    ChatProviderException,
    ConfigurationException,
    OwnerSettingException,
    owner_network_error,
    owner_not_found_error,
    owner_permission_error,
    owner_timeout_error,
    owner_validation_error,
)

from .base import ChatResult

if TYPE_CHECKING:
    from .owner_config_manager import OwnerConfigManager

logger = logging.getLogger(__name__)


class FeishuOwnerMixin:  # pragma: no cover
    """负责飞书群主验证、查询和重试逻辑"""

    BASE_URL: str
    ENDPOINTS: dict[str, str]
    config: dict[str, Any]
    owner_config: OwnerConfigManager

    def is_available(self) -> bool:  # 由 FeishuTokenMixin 提供  # pragma: no cover
        raise NotImplementedError

    def _get_tenant_access_token(self) -> str:  # 由 FeishuTokenMixin 提供  # pragma: no cover
        raise NotImplementedError

    def get_chat_info(self, chat_id: str) -> ChatResult:  # pragma: no cover
        """获取群聊详细信息"""
        if not self.is_available():
            raise ConfigurationException(
                message="飞书配置不完整，无法获取群聊信息", platform="feishu", missing_config="APP_ID, APP_SECRET"
            )

        try:
            access_token = self._get_tenant_access_token()
            url = f"{self.BASE_URL}{self.ENDPOINTS['get_chat'].format(chat_id=chat_id)}"
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            if data.get("code") != 0:
                error_msg = data.get("msg", "未知错误")
                error_code = str(data.get("code"))
                logger.error("获取飞书群聊信息失败: %s (code: %s)", error_msg, error_code)
                raise ChatProviderException(
                    message=f"获取群聊信息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    errors={"api_response": data, "chat_id": chat_id},
                )

            chat_data = data.get("data", {})
            chat_name = chat_data.get("name", "")
            logger.debug("成功获取飞书群聊信息: %s (名称: %s)", chat_id, chat_name)

            return ChatResult(
                success=True,
                chat_id=chat_id,
                chat_name=chat_name,
                message="获取群聊信息成功",
                raw_response=data,
            )

        except ChatProviderException:
            raise
        except httpx.HTTPError as e:
            logger.error("获取飞书群聊信息网络请求失败: %s", e)
            raise ChatProviderException(
                message=f"网络请求失败: {e!s}",
                platform="feishu",
                errors={"original_error": str(e), "chat_id": chat_id},
            ) from e
        except Exception as e:
            logger.error("获取飞书群聊信息时发生未知错误: %s", e)
            raise ChatProviderException(
                message=f"获取群聊信息时发生未知错误: {e!s}",
                platform="feishu",
                errors={"original_error": str(e), "chat_id": chat_id},
            ) from e

    def _classify_feishu_error(  # pragma: no cover
        self, error_code: str, error_msg: str
    ) -> OwnerSettingException | type[ChatCreationException]:
        """分类飞书API错误"""
        error_msg_lower = error_msg.lower()

        if (
            error_code in ["99991663", "99991664", "99991665"]
            or "permission" in error_msg_lower
            or "forbidden" in error_msg_lower
            or "access denied" in error_msg_lower
        ):
            return owner_permission_error()

        if (
            error_code in ["99991400", "99991401"]
            or "user not found" in error_msg_lower
            or "invalid user" in error_msg_lower
            or "user does not exist" in error_msg_lower
        ):
            return owner_not_found_error()

        if (
            error_code in ["99991400", "1400"]
            or "invalid parameter" in error_msg_lower
            or "parameter error" in error_msg_lower
            or "validation failed" in error_msg_lower
        ):
            return owner_validation_error()

        if "timeout" in error_msg_lower or "timed out" in error_msg_lower:
            return owner_timeout_error()

        if "network" in error_msg_lower or "connection" in error_msg_lower or "request failed" in error_msg_lower:
            return owner_network_error()

        return ChatCreationException

    def _convert_union_id_to_open_id(self, union_id: str) -> str | None:  # pragma: no cover
        """转换 union_id 为 open_id"""
        try:
            access_token = self._get_tenant_access_token()
            url = f"{self.BASE_URL}/contact/v3/users/{union_id}"
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            params = {"user_id_type": "union_id", "department_id_type": "department_id"}

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            if data.get("code") == 0:
                user_data = data.get("data", {}).get("user", {})
                open_id = user_data.get("open_id")
                if open_id:
                    logger.info("成功转换union_id为open_id: %s -> %s", union_id, open_id)
                    return str(open_id)
                else:
                    logger.warning("API响应中缺少open_id: %s", union_id)
                    return None
            else:
                error_msg = data.get("msg", "未知错误")
                logger.warning("转换union_id失败: %s, 错误: %s", union_id, error_msg)
                return None

        except Exception as e:
            logger.error("转换union_id时发生错误: %s, 错误: %s", union_id, e)
            return None
