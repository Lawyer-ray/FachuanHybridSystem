"""群聊平台配置注册"""

from .field import ConfigField


def register_chat_configs(registry: dict[str, ConfigField]) -> None:
    # 飞书
    registry["chat_platforms.feishu.app_id"] = ConfigField(
        name="chat_platforms.feishu.app_id",
        type=str,
        required=False,
        sensitive=True,
        env_var="FEISHU_APP_ID",
        description="飞书应用 ID",
    )
    registry["chat_platforms.feishu.app_secret"] = ConfigField(
        name="chat_platforms.feishu.app_secret",
        type=str,
        required=False,
        sensitive=True,
        env_var="FEISHU_APP_SECRET",
        description="飞书应用密钥",
    )
    registry["chat_platforms.feishu.webhook_url"] = ConfigField(
        name="chat_platforms.feishu.webhook_url",
        type=str,
        env_var="FEISHU_WEBHOOK_URL",
        description="飞书 Webhook URL",
    )
    registry["chat_platforms.feishu.timeout"] = ConfigField(
        name="chat_platforms.feishu.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="飞书 API 超时时间（秒）",
    )
    registry["chat_platforms.feishu.default_owner_id"] = ConfigField(
        name="chat_platforms.feishu.default_owner_id",
        type=str,
        env_var="FEISHU_DEFAULT_OWNER_ID",
        description="飞书默认群主 ID",
    )
    # 钉钉
    registry["chat_platforms.dingtalk.app_key"] = ConfigField(
        name="chat_platforms.dingtalk.app_key",
        type=str,
        env_var="DINGTALK_APP_KEY",
        description="钉钉应用 Key",
    )
    registry["chat_platforms.dingtalk.app_secret"] = ConfigField(
        name="chat_platforms.dingtalk.app_secret",
        type=str,
        sensitive=True,
        env_var="DINGTALK_APP_SECRET",
        description="钉钉应用密钥",
    )
    registry["chat_platforms.dingtalk.agent_id"] = ConfigField(
        name="chat_platforms.dingtalk.agent_id",
        type=str,
        env_var="DINGTALK_AGENT_ID",
        description="钉钉应用 Agent ID",
    )
    registry["chat_platforms.dingtalk.default_owner_id"] = ConfigField(
        name="chat_platforms.dingtalk.default_owner_id",
        type=str,
        env_var="DINGTALK_DEFAULT_OWNER_ID",
        description="钉钉默认群主 userid（建群必须指定群主）",
    )
    registry["chat_platforms.dingtalk.timeout"] = ConfigField(
        name="chat_platforms.dingtalk.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="钉钉 API 超时时间（秒）",
    )
    # 企业微信
    registry["chat_platforms.wechat_work.corp_id"] = ConfigField(
        name="chat_platforms.wechat_work.corp_id",
        type=str,
        env_var="WECHAT_WORK_CORP_ID",
        description="企业微信 Corp ID",
    )
    registry["chat_platforms.wechat_work.agent_id"] = ConfigField(
        name="chat_platforms.wechat_work.agent_id",
        type=str,
        env_var="WECHAT_WORK_AGENT_ID",
        description="企业微信应用 Agent ID",
    )
    registry["chat_platforms.wechat_work.secret"] = ConfigField(
        name="chat_platforms.wechat_work.secret",
        type=str,
        sensitive=True,
        env_var="WECHAT_WORK_SECRET",
        description="企业微信应用密钥",
    )
    registry["chat_platforms.wechat_work.timeout"] = ConfigField(
        name="chat_platforms.wechat_work.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="企业微信 API 超时时间（秒）",
    )
    registry["chat_platforms.wechat_work.default_owner_id"] = ConfigField(
        name="chat_platforms.wechat_work.default_owner_id",
        type=str,
        env_var="WECHAT_WORK_DEFAULT_OWNER_ID",
        description="企业微信默认群主 userid（建群必须指定群主）",
    )
    # Telegram
    registry["chat_platforms.telegram.bot_token"] = ConfigField(
        name="chat_platforms.telegram.bot_token",
        type=str,
        sensitive=True,
        env_var="TELEGRAM_BOT_TOKEN",
        description="Telegram Bot Token",
    )
    registry["chat_platforms.telegram.supergroup_id"] = ConfigField(
        name="chat_platforms.telegram.supergroup_id",
        type=str,
        env_var="TELEGRAM_SUPERGROUP_ID",
        description="Telegram 超级群组 ID（开启论坛功能的超级群组，用于一案一群 Topic 模式）",
    )
    registry["chat_platforms.telegram.timeout"] = ConfigField(
        name="chat_platforms.telegram.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="Telegram API 超时时间（秒）",
    )
    # Slack
    registry["chat_platforms.slack.bot_token"] = ConfigField(
        name="chat_platforms.slack.bot_token",
        type=str,
        sensitive=True,
        env_var="SLACK_BOT_TOKEN",
        description="Slack Bot Token",
    )
    registry["chat_platforms.slack.signing_secret"] = ConfigField(
        name="chat_platforms.slack.signing_secret",
        type=str,
        sensitive=True,
        env_var="SLACK_SIGNING_SECRET",
        description="Slack 签名密钥",
    )
    registry["chat_platforms.slack.timeout"] = ConfigField(
        name="chat_platforms.slack.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="Slack API 超时时间（秒）",
    )
