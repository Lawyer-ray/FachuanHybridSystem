"""飞书群主相关操作 Mixin"""

import logging
from typing import Any, cast

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

logger = logging.getLogger(__name__)


class FeishuOwnerMixin:
    """负责飞书群主验证、查询和重试逻辑"""

    BASE_URL: str
    ENDPOINTS: dict[str, str]
    config: dict[str, Any]

    def is_available(self) -> bool: ...  # 由 FeishuTokenMixin 提供

    def _get_tenant_access_token(self) -> str: ...  # 由 FeishuTokenMixin 提供

    def get_chat_info(self, chat_id: str) -> ChatResult:
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
                logger.error(f"获取飞书群聊信息失败: {error_msg} (code: {error_code})")
                raise ChatProviderException(
                    message=f"获取群聊信息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    errors={"api_response": data, "chat_id": chat_id},
                )

            chat_data = data.get("data", {})
            chat_name = chat_data.get("name", "")
            logger.debug(f"成功获取飞书群聊信息: {chat_id} (名称: {chat_name})")

            return ChatResult(
                success=True, chat_id=chat_id, chat_name=chat_name, message="获取群聊信息成功", raw_response=data
            )

        except ChatProviderException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"获取飞书群聊信息网络请求失败: {e!s}")
            raise ChatProviderException(
                message=f"网络请求失败: {e!s}",
                platform="feishu",
                errors={"original_error": str(e), "chat_id": chat_id},
            ) from e
        except Exception as e:
            logger.error(f"获取飞书群聊信息时发生未知错误: {e!s}")
            raise ChatProviderException(
                message=f"获取群聊信息时发生未知错误: {e!s}",
                platform="feishu",
                errors={"original_error": str(e), "chat_id": chat_id},
            ) from e

    def verify_owner_setting(self, chat_id: str, expected_owner_id: str) -> bool:
        """验证群主设置是否正确"""
        try:
            chat_info = self.get_chat_owner_info(chat_id)

            if not chat_info:
                logger.warning(f"无法获取群聊信息进行群主验证: {chat_id}")
                return False

            actual_owner_id = chat_info.get("owner_id")

            if not actual_owner_id:
                logger.warning(f"群聊信息中缺少群主ID: {chat_id}")
                return False

            is_match = actual_owner_id == expected_owner_id

            if is_match:
                logger.info(f"群主设置验证成功: {chat_id}, 群主: {actual_owner_id}")
            else:
                logger.warning(f"群主设置验证失败: {chat_id}, 期望: {expected_owner_id}, 实际: {actual_owner_id}")

            return cast(bool, is_match)

        except Exception as e:
            logger.error(f"验证群主设置时发生错误: {chat_id}, 错误: {e!s}")
            return False

    def get_chat_owner_info(self, chat_id: str) -> dict[str, Any]:
        """获取群聊群主信息"""
        if not self.is_available():
            raise ConfigurationException(
                message="飞书配置不完整，无法获取群聊群主信息", platform="feishu", missing_config="APP_ID, APP_SECRET"
            )

        try:
            access_token = self._get_tenant_access_token()
            url = f"{self.BASE_URL}{self.ENDPOINTS['get_chat'].format(chat_id=chat_id)}"
            params = {"user_id_type": "open_id"}
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            if data.get("code") != 0:
                error_msg = data.get("msg", "未知错误")
                error_code = str(data.get("code"))
                logger.error(f"获取飞书群聊群主信息失败: {error_msg} (code: {error_code})")
                raise ChatProviderException(
                    message=f"获取群聊群主信息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    errors={"api_response": data, "chat_id": chat_id},
                )

            chat_data = data.get("data", {})
            owner_info = {
                "chat_id": chat_id,
                "owner_id": chat_data.get("owner_id"),
                "owner_id_type": chat_data.get("owner_id_type", "open_id"),
                "chat_name": chat_data.get("name"),
                "chat_mode": chat_data.get("chat_mode"),
                "chat_type": chat_data.get("chat_type"),
                "member_count": len(chat_data.get("members", [])),
                "raw_data": chat_data,
            }

            logger.debug(f"成功获取群聊群主信息: {chat_id}, 群主: {owner_info.get('owner_id')}")
            return owner_info

        except ChatProviderException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"获取飞书群聊群主信息网络请求失败: {e!s}")
            raise ChatProviderException(
                message=f"网络请求失败: {e!s}",
                platform="feishu",
                errors={"original_error": str(e), "chat_id": chat_id},
            ) from e
        except Exception as e:
            logger.error(f"获取飞书群聊群主信息时发生未知错误: {e!s}")
            raise ChatProviderException(
                message=f"获取群聊群主信息时发生未知错误: {e!s}",
                platform="feishu",
                errors={"original_error": str(e), "chat_id": chat_id},
            ) from e

    def retry_owner_setting(self, chat_id: str, owner_id: str, max_retries: int = 3) -> bool:
        """重试群主设置"""
        from .retry_config import RetryManager

        if not self.owner_config.is_retry_enabled():  # type: ignore[attr-defined]
            logger.info(f"重试机制已禁用，跳过群主设置重试: {chat_id}")
            return False

        retry_manager = RetryManager()

        def verify_operation() -> None:
            if not self.verify_owner_setting(chat_id, owner_id):
                raise owner_validation_error(
                    message=f"群主设置验证失败: 期望群主 {owner_id}",
                    owner_id=owner_id,
                    chat_id=chat_id,
                    validation_type="owner_verification",
                )
            return True  # type: ignore[return-value]

        try:
            retry_manager.execute_with_retry(
                operation=verify_operation,
                operation_name=f"verify_owner_setting_{chat_id}",
                context={"chat_id": chat_id, "owner_id": owner_id, "max_retries": max_retries},
            )
            summary = retry_manager.get_retry_summary()
            logger.info(f"群主设置重试成功: {chat_id}, 摘要: {summary}")
            return True

        except Exception as e:
            summary = retry_manager.get_retry_summary()
            logger.error(f"群主设置重试最终失败: {chat_id}, 摘要: {summary}, 错误: {e!s}")
            return False

    def _classify_feishu_error(
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

    def _convert_union_id_to_open_id(self, union_id: str) -> str | None:
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
                    logger.info(f"成功转换union_id为open_id: {union_id} -> {open_id}")
                    return open_id  # type: ignore[no-any-return]
                else:
                    logger.warning(f"API响应中缺少open_id: {union_id}")
                    return None
            else:
                error_msg = data.get("msg", "未知错误")
                logger.warning(f"转换union_id失败: {union_id}, 错误: {error_msg}")
                return None

        except Exception as e:
            logger.error(f"转换union_id时发生错误: {union_id}, 错误: {e!s}")
            return None
