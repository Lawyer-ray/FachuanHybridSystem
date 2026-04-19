"""钉钉 Token 与配置加载 Mixin

本模块负责钉钉配置加载和 access_token 获取。

API文档参考：
- 钉钉开放平台：https://open.dingtalk.com/document/isvapp/api-overview
- 获取access_token：https://open.dingtalk.com/document/isvapp/obtain-orgapp-token

配置要求：
- DINGTALK.APP_KEY: 钉钉应用 App Key
- DINGTALK.APP_SECRET: 钉钉应用 App Secret
- DINGTALK.DEFAULT_OWNER_ID: 默认群主 userid（建群必须）
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ChatProviderException, ConfigurationException

logger = logging.getLogger(__name__)


class DingtalkTokenMixin:
    """负责钉钉配置加载和 access_token 获取"""

    config: dict[str, Any]
    _access_token: str | None
    _token_expires_at: datetime | None

    def _load_config_from_db(self) -> dict[str, Any]:
        """从 SystemConfig 加载钉钉配置"""
        try:
            from apps.core.config.utils import get_dingtalk_category_configs

            db_configs = get_dingtalk_category_configs()
            if not db_configs:
                return {}
            key_mapping = {
                "DINGTALK_APP_KEY": "APP_KEY",
                "DINGTALK_APP_SECRET": "APP_SECRET",
                "DINGTALK_AGENT_ID": "AGENT_ID",
                "DINGTALK_DEFAULT_OWNER_ID": "DEFAULT_OWNER_ID",
            }
            config = {internal: db_configs[db] for db, internal in key_mapping.items() if db_configs.get(db)}
            logger.debug(f"从 SystemConfig 加载钉钉配置: {list(config.keys())}")
            return config
        except Exception as e:
            logger.debug(f"从 SystemConfig 加载配置失败，回退到 settings: {e!s}")
            return {}

    def _load_config(self) -> dict[str, Any]:
        """加载钉钉配置"""
        try:
            config = self._load_config_from_db()

            if not config.get("APP_KEY") or not config.get("APP_SECRET"):
                logger.warning(
                    "SystemConfig 中钉钉 APP_KEY/APP_SECRET 未配置，"
                    "请在系统配置中设置 DINGTALK_APP_KEY 和 DINGTALK_APP_SECRET"
                )

            config.setdefault("TIMEOUT", 30)
            try:
                config["TIMEOUT"] = int(config["TIMEOUT"])
            except (ValueError, TypeError):
                config["TIMEOUT"] = 30

            filtered_config = {k: v for k, v in config.items() if v is not None and v != ""}
            logger.debug(f"最终钉钉配置: {list(filtered_config.keys())}")
            return filtered_config

        except Exception as e:
            logger.error(f"加载钉钉配置失败: {e!s}")
            raise ConfigurationException(
                message=f"无法加载钉钉配置: {e!s}", platform="dingtalk", errors={"original_error": str(e)}
            ) from e

    def is_available(self) -> bool:
        """检查平台是否可用（至少需要 app_key + app_secret + default_owner_id）"""
        for config_key in ["APP_KEY", "APP_SECRET"]:
            if not self.config.get(config_key):
                logger.debug(f"钉钉配置缺失: {config_key}")
                return False
        if not self.config.get("DEFAULT_OWNER_ID"):
            logger.debug("钉钉配置缺失: DEFAULT_OWNER_ID（建群必须指定群主）")
            return False
        return True

    def _get_access_token(self) -> str:
        """获取钉钉 access_token，支持缓存和自动刷新

        钉钉获取企业内部应用 access_token：
        POST https://oapi.dingtalk.com/gettoken?appkey=xxx&appsecret=xxx
        """
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now() < self._token_expires_at - timedelta(minutes=5)
        ):
            return self._access_token

        app_key = self.config.get("APP_KEY")
        app_secret = self.config.get("APP_SECRET")

        if not app_key or not app_secret:
            raise ConfigurationException(
                message=_("钉钉 APP_KEY 或 APP_SECRET 未配置"),
                platform="dingtalk",
                missing_config="APP_KEY, APP_SECRET",
            )

        url = f"https://oapi.dingtalk.com/gettoken?appkey={app_key}&appsecret={app_secret}"

        try:
            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.post(url, timeout=timeout, headers={"Content-Type": "application/json"})
            response.raise_for_status()

            data = response.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                error_msg = data.get("errmsg", "未知错误")
                raise ChatProviderException(
                    message=f"获取钉钉 access_token 失败: {error_msg}",
                    platform="dingtalk",
                    error_code=str(errcode),
                    errors={"api_response": data},
                )

            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 7200)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            logger.debug("已获取钉钉 access_token")
            if self._access_token is None:
                raise ChatProviderException("钉钉 access_token 为空")
            return self._access_token

        except ChatProviderException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"请求钉钉 access_token 失败: {e!s}")
            raise ChatProviderException(
                message=f"网络请求失败: {e!s}", platform="dingtalk", errors={"original_error": str(e)}
            ) from e
        except (KeyError, ValueError) as e:
            logger.error(f"解析钉钉 API 响应失败: {e!s}")
            raise ChatProviderException(
                message=f"API 响应格式错误: {e!s}", platform="dingtalk", errors={"original_error": str(e)}
            ) from e
