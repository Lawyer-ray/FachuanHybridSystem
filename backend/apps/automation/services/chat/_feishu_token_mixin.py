"""飞书 Token 与配置加载 Mixin"""

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx
from django.conf import settings

from apps.core.exceptions import ChatProviderException, ConfigurationException

logger = logging.getLogger(__name__)


class FeishuTokenMixin:
    """负责飞书配置加载和 tenant_access_token 获取"""

    BASE_URL: str
    config: dict[str, Any]
    ENDPOINTS: dict[str, str]
    _access_token: str | None
    _token_expires_at: datetime | None

    def _load_config_from_db(self) -> dict[str, Any]:
        """从 SystemConfig 加载飞书配置"""
        try:
            from apps.core.config.utils import get_feishu_category_configs

            db_configs = get_feishu_category_configs()
            if not db_configs:
                return {}
            key_mapping = {
                "FEISHU_APP_ID": "APP_ID",
                "FEISHU_APP_SECRET": "APP_SECRET",
                "FEISHU_WEBHOOK_URL": "WEBHOOK_URL",
                "FEISHU_TIMEOUT": "TIMEOUT",
                "FEISHU_DEFAULT_OWNER_ID": "DEFAULT_OWNER_ID",
            }
            config = {internal: db_configs[db] for db, internal in key_mapping.items() if db_configs.get(db)}
            logger.debug(f"从 SystemConfig 加载飞书配置: {list(config.keys())}")
            return config
        except Exception as e:
            logger.debug(f"从 SystemConfig 加载配置失败，回退到 settings: {e!s}")
            return {}

    def _load_config(self) -> dict[str, Any]:
        """加载飞书配置"""
        try:
            config = self._load_config_from_db()

            if not config.get("APP_ID") or not config.get("APP_SECRET"):
                settings_config = getattr(settings, "FEISHU", {})
                if isinstance(settings_config, dict):
                    for key, value in settings_config.items():
                        if key not in config and value is not None and value != "":
                            config[key] = value
                    logger.debug(f"从 settings 补充飞书配置: {list(config.keys())}")

            config.setdefault("TIMEOUT", 30)
            try:
                config["TIMEOUT"] = int(config["TIMEOUT"])
            except (ValueError, TypeError):
                config["TIMEOUT"] = 30

            filtered_config = {k: v for k, v in config.items() if v is not None and v != ""}
            logger.debug(f"最终飞书配置: {list(filtered_config.keys())}")
            return filtered_config

        except Exception as e:
            logger.error(f"加载飞书配置失败: {e!s}")
            raise ConfigurationException(
                message=f"无法加载飞书配置: {e!s}", platform="feishu", errors={"original_error": str(e)}
            ) from e

    def is_available(self) -> bool:
        """检查平台是否可用"""
        for config_key in ["APP_ID", "APP_SECRET"]:
            if not self.config.get(config_key):
                logger.debug(f"飞书配置缺失: {config_key}")
                return False
        return True

    def _get_tenant_access_token(self) -> str:
        """获取租户访问令牌，支持缓存和自动刷新"""
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now() < self._token_expires_at - timedelta(minutes=5)
        ):
            return self._access_token

        app_id = self.config.get("APP_ID")
        app_secret = self.config.get("APP_SECRET")

        if not app_id or not app_secret:
            raise ConfigurationException(
                message="飞书APP_ID或APP_SECRET未配置", platform="feishu", missing_config="APP_ID, APP_SECRET"
            )

        url = f"{self.BASE_URL}{self.ENDPOINTS['tenant_access_token']}"
        payload = {"app_id": app_id, "app_secret": app_secret}

        try:
            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, json=payload, timeout=timeout, headers={"Content-Type": "application/json"})
            response.raise_for_status()

            data = response.json()

            if data.get("code") != 0:
                error_msg = data.get("msg", "未知错误")
                raise ChatProviderException(
                    message=f"获取飞书访问令牌失败: {error_msg}",
                    platform="feishu",
                    error_code=str(data.get("code")),
                    errors={"api_response": data},
                )

            self._access_token = data["tenant_access_token"]
            expires_in = data.get("expire", 7200)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            logger.debug("已获取飞书访问令牌")
            if self._access_token is None:
                raise ChatProviderException("飞书访问令牌为空")
            return self._access_token

        except httpx.HTTPError as e:
            logger.error(f"请求飞书访问令牌失败: {e!s}")
            raise ChatProviderException(
                message=f"网络请求失败: {e!s}", platform="feishu", errors={"original_error": str(e)}
            ) from e
        except (KeyError, ValueError) as e:
            logger.error(f"解析飞书API响应失败: {e!s}")
            raise ChatProviderException(
                message=f"API响应格式错误: {e!s}", platform="feishu", errors={"original_error": str(e)}
            ) from e
