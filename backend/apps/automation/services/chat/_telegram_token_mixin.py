"""Telegram Token 与配置加载 Mixin

本模块负责 Telegram 配置加载。

Telegram Bot API 使用 Bot Token 直接认证，无需额外的 access_token 获取流程。
每个 API 请求通过 URL 路径携带 Bot Token：https://api.telegram.org/bot{token}/methodName

配置要求：
- TELEGRAM.BOT_TOKEN: Telegram Bot Token（从 @BotFather 获取）
- TELEGRAM.SUPERGROUP_ID: 预建的超级群组 ID（用作论坛容器，一案一群通过 Topic 实现）

设计说明：
  标准的 Telegram Bot API 无法主动创建群组。为兼容"一案一群"语义，
  采用**超级群组论坛(Topic)模式**：
  - 管理员预先创建一个 Telegram 超级群组并开启论坛功能
  - 每个案件在该群组中创建一个 Topic（论坛话题），等同于"一案一群"
  - create_chat → createForumTopic（创建话题）
  - 消息/文件发送时携带 message_thread_id 指向对应话题

API文档参考：
- Telegram Bot API：https://core.telegram.org/bots/api
- createForumTopic：https://core.telegram.org/bots/api#createforumtopic
"""

import logging
from typing import Any

from apps.core.exceptions import ConfigurationException

logger = logging.getLogger(__name__)


class TelegramTokenMixin:
    """负责 Telegram 配置加载

    Telegram 使用 Bot Token 直接认证，无需额外获取 access_token。
    """

    config: dict[str, Any]

    API_BASE_URL = "https://api.telegram.org"

    def _load_config_from_db(self) -> dict[str, Any]:
        """从 SystemConfig 加载 Telegram 配置"""
        try:
            from apps.core.config.utils import get_telegram_category_configs

            db_configs = get_telegram_category_configs()
            if not db_configs:
                return {}
            key_mapping = {
                "TELEGRAM_BOT_TOKEN": "BOT_TOKEN",
                "TELEGRAM_SUPERGROUP_ID": "SUPERGROUP_ID",
            }
            config = {internal: db_configs[db] for db, internal in key_mapping.items() if db_configs.get(db)}
            logger.debug(f"从 SystemConfig 加载 Telegram 配置: {list(config.keys())}")
            return config
        except Exception as e:
            logger.debug(f"从 SystemConfig 加载配置失败: {e!s}")
            return {}

    def _load_config(self) -> dict[str, Any]:
        """加载 Telegram 配置"""
        try:
            config = self._load_config_from_db()

            if not config.get("BOT_TOKEN"):
                logger.warning(
                    "SystemConfig 中 Telegram BOT_TOKEN 未配置，"
                    "请在系统配置中设置 TELEGRAM_BOT_TOKEN"
                )

            if not config.get("SUPERGROUP_ID"):
                logger.warning(
                    "SystemConfig 中 Telegram SUPERGROUP_ID 未配置，"
                    "请预先创建一个开启论坛功能的超级群组，并将群组 ID 配置到 TELEGRAM_SUPERGROUP_ID"
                )

            config.setdefault("TIMEOUT", 30)
            try:
                config["TIMEOUT"] = int(config["TIMEOUT"])
            except (ValueError, TypeError):
                config["TIMEOUT"] = 30

            # SUPERGROUP_ID 需要转为 int（Telegram chat_id 是整数）
            if config.get("SUPERGROUP_ID"):
                try:
                    config["SUPERGROUP_ID"] = int(config["SUPERGROUP_ID"])
                except (ValueError, TypeError):
                    logger.warning(f"TELEGRAM_SUPERGROUP_ID 无法转为整数: {config['SUPERGROUP_ID']}")

            filtered_config = {k: v for k, v in config.items() if v is not None and v != ""}
            logger.debug(f"最终 Telegram 配置: {list(filtered_config.keys())}")
            return filtered_config

        except Exception as e:
            logger.error(f"加载 Telegram 配置失败: {e!s}")
            raise ConfigurationException(
                message=f"无法加载 Telegram 配置: {e!s}", platform="telegram", errors={"original_error": str(e)}
            ) from e

    def is_available(self) -> bool:
        """检查平台是否可用（至少需要 bot_token + supergroup_id）"""
        for config_key in ["BOT_TOKEN", "SUPERGROUP_ID"]:
            if not self.config.get(config_key):
                logger.debug(f"Telegram 配置缺失: {config_key}")
                return False
        return True

    def _get_bot_api_url(self, method: str) -> str:
        """构建 Bot API 请求 URL

        Args:
            method: Bot API 方法名（如 sendMessage, createForumTopic）

        Returns:
            完整的 API URL
        """
        bot_token = self.config.get("BOT_TOKEN")
        if not bot_token:
            raise ConfigurationException(
                message="Telegram BOT_TOKEN 未配置",
                platform="telegram",
                missing_config="BOT_TOKEN",
            )
        return f"{self.API_BASE_URL}/bot{bot_token}/{method}"
