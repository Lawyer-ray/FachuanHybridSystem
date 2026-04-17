"""企业微信 Token 与配置加载 Mixin"""

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ChatProviderException, ConfigurationException

logger = logging.getLogger(__name__)


class WeChatWorkTokenMixin:
    """负责企业微信配置加载和 access_token 获取"""

    BASE_URL: str
    config: dict[str, Any]
    _access_token: str | None
    _token_expires_at: datetime | None

    def _load_config_from_db(self) -> dict[str, Any]:
        """从 SystemConfig 加载企业微信配置"""
        try:
            from apps.core.config.utils import get_wechat_work_category_configs

            db_configs = get_wechat_work_category_configs()
            if not db_configs:
                return {}
            key_mapping = {
                "WECHAT_WORK_CORP_ID": "CORP_ID",
                "WECHAT_WORK_AGENT_ID": "AGENT_ID",
                "WECHAT_WORK_SECRET": "SECRET",
                "WECHAT_WORK_DEFAULT_OWNER_ID": "DEFAULT_OWNER_ID",
            }
            config = {internal: db_configs[db] for db, internal in key_mapping.items() if db_configs.get(db)}
            logger.debug(f"从 SystemConfig 加载企业微信配置: {list(config.keys())}")
            return config
        except Exception as e:
            logger.debug(f"从 SystemConfig 加载配置失败: {e!s}")
            return {}

    def _load_config(self) -> dict[str, Any]:
        """加载企业微信配置"""
        try:
            config = self._load_config_from_db()

            if not config.get("CORP_ID") or not config.get("SECRET"):
                logger.warning(
                    "SystemConfig 中企业微信 CORP_ID/SECRET 未配置，"
                    "请在系统配置中设置 WECHAT_WORK_CORP_ID 和 WECHAT_WORK_SECRET"
                )

            config.setdefault("TIMEOUT", 30)
            try:
                config["TIMEOUT"] = int(config["TIMEOUT"])
            except (ValueError, TypeError):
                config["TIMEOUT"] = 30

            filtered_config = {k: v for k, v in config.items() if v is not None and v != ""}
            logger.debug(f"最终企业微信配置: {list(filtered_config.keys())}")
            return filtered_config

        except Exception as e:
            logger.error(f"加载企业微信配置失败: {e!s}")
            raise ConfigurationException(
                message=f"无法加载企业微信配置: {e!s}", platform="wechat_work", errors={"original_error": str(e)}
            ) from e

    def is_available(self) -> bool:
        """检查平台是否可用（至少需要 corp_id + agent_id + secret + default_owner_id）"""
        for config_key in ["CORP_ID", "AGENT_ID", "SECRET"]:
            if not self.config.get(config_key):
                logger.debug(f"企业微信配置缺失: {config_key}")
                return False
        if not self.config.get("DEFAULT_OWNER_ID"):
            logger.debug("企业微信配置缺失: DEFAULT_OWNER_ID（建群必须指定群主）")
            return False
        return True

    def _get_access_token(self) -> str:
        """获取企业微信 access_token，支持缓存和自动刷新"""
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now() < self._token_expires_at - timedelta(minutes=5)
        ):
            return self._access_token

        corp_id = self.config.get("CORP_ID")
        secret = self.config.get("SECRET")

        if not corp_id or not secret:
            raise ConfigurationException(
                message=_("企业微信 CORP_ID 或 SECRET 未配置"),
                platform="wechat_work",
                missing_config="CORP_ID, SECRET",
            )

        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={secret}"

        try:
            timeout = self.config.get("TIMEOUT", 30)
            response = httpx.get(url, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            errcode = data.get("errcode", 0)
            if errcode != 0:
                error_msg = data.get("errmsg", "未知错误")
                raise ChatProviderException(
                    message=f"获取企业微信 access_token 失败: {error_msg}",
                    platform="wechat_work",
                    error_code=str(errcode),
                    errors={"api_response": data},
                )

            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 7200)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            logger.debug("已获取企业微信 access_token")
            if self._access_token is None:
                raise ChatProviderException("企业微信 access_token 为空")
            return self._access_token

        except httpx.HTTPError as e:
            logger.error(f"请求企业微信 access_token 失败: {e!s}")
            raise ChatProviderException(
                message=f"网络请求失败: {e!s}", platform="wechat_work", errors={"original_error": str(e)}
            ) from e
        except (KeyError, ValueError) as e:
            logger.error(f"解析企业微信 API 响应失败: {e!s}")
            raise ChatProviderException(
                message=f"API 响应格式错误: {e!s}", platform="wechat_work", errors={"original_error": str(e)}
            ) from e
