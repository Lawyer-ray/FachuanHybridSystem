"""飞书、钉钉、企业微信、Telegram 配置数据"""

from typing import Any

__all__ = ["get_feishu_configs", "get_dingtalk_configs", "get_wechat_work_configs", "get_telegram_configs"]


def get_feishu_configs() -> list[dict[str, Any]]:
    """获取飞书配置项"""
    return [
        # ============ 飞书配置 ============
        {
            "key": "FEISHU_APP_ID",
            "category": "feishu",
            "description": "飞书应用 App ID",
            "value": "cli_a7c6d011527bd01d",
            "is_secret": False,
        },
        {
            "key": "FEISHU_APP_SECRET",
            "category": "feishu",
            "description": "飞书应用 App Secret",
            "value": "vkKUfuUb9QOxqjxESKMwCdKVsHOW81OL",
            "is_secret": True,
        },
        {
            "key": "FEISHU_DEFAULT_OWNER_ID",
            "category": "feishu",
            "description": "飞书群聊默认群主 ID（open_id 格式：ou_xxxxxx）",
            "value": "ou_ca5452b3e9bc932c9980f3e313867aed",
            "is_secret": False,
        },
        # ============ 群聊名称模板配置 ============
        {
            "key": "CASE_CHAT_NAME_TEMPLATE",
            "category": "feishu",
            "description": (
                "案件群聊名称模板，支持占位符：{stage}（案件阶段）、{case_name}（案件名称）、{case_type}（案件类型）"
            ),
            "value": "[{stage}]{case_name}",
            "is_secret": False,
        },
    ]


def get_dingtalk_configs() -> list[dict[str, Any]]:
    """获取钉钉配置项

    TIMEOUT 由代码默认值兜底（30秒），无需用户手动配置。
    """
    return [
        {"key": "DINGTALK_APP_KEY", "category": "dingtalk", "description": "钉钉应用 App Key", "is_secret": False},
        {
            "key": "DINGTALK_APP_SECRET",
            "category": "dingtalk",
            "description": "钉钉应用 App Secret",
            "is_secret": True,
        },
        {"key": "DINGTALK_AGENT_ID", "category": "dingtalk", "description": "钉钉应用 Agent ID", "is_secret": False},
        {
            "key": "DINGTALK_DEFAULT_OWNER_ID",
            "category": "dingtalk",
            "description": "钉钉默认群主 userid（创建群聊必须指定群主，填写企业内任一成员的 userid）",
            "is_secret": False,
        },
    ]


def get_wechat_work_configs() -> list[dict[str, Any]]:
    """获取企业微信配置项

    根据 https://developer.work.weixin.qq.com/document/path/90664 要求，
    建群（appchat/create）必须指定 owner，获取 access_token 需要 corpid + secret。
    TIMEOUT 由代码默认值兜底（30秒），无需用户手动配置。
    """
    return [
        {
            "key": "WECHAT_WORK_CORP_ID",
            "category": "wechat_work",
            "description": "企业微信 Corp ID（企业 ID，在管理后台「我的企业」页面获取）",
            "is_secret": False,
        },
        {
            "key": "WECHAT_WORK_AGENT_ID",
            "category": "wechat_work",
            "description": "企业微信应用 Agent ID（在应用管理页面获取）",
            "is_secret": False,
        },
        {
            "key": "WECHAT_WORK_SECRET",
            "category": "wechat_work",
            "description": "企业微信应用 Secret（在应用管理页面获取，用于获取 access_token）",
            "is_secret": True,
        },
        {
            "key": "WECHAT_WORK_DEFAULT_OWNER_ID",
            "category": "wechat_work",
            "description": "企业微信默认群主 userid（创建群聊 appchat/create 必须指定群主，填写企业内任一成员的 userid）",
            "is_secret": False,
        },
    ]


def get_telegram_configs() -> list[dict[str, Any]]:
    """获取 Telegram 配置项

    Telegram Bot API 使用 Bot Token 直接认证，无需额外获取 access_token。
    为实现"一案一群"，采用超级群组论坛(Topic)模式：
    管理员预先创建一个开启论坛功能的超级群组，每个案件在该群组中创建一个话题。
    """
    return [
        {
            "key": "TELEGRAM_BOT_TOKEN",
            "category": "telegram",
            "description": "Telegram Bot Token（从 @BotFather 获取）",
            "is_secret": True,
        },
        {
            "key": "TELEGRAM_SUPERGROUP_ID",
            "category": "telegram",
            "description": (
                "Telegram 超级群组 ID（需预先创建一个开启论坛功能的超级群组，"
                "将 Bot 添加为群管理员，并将群组 ID 填写于此。群组 ID 通常为负数，如 -1001234567890）"
            ),
            "is_secret": False,
        },
    ]
