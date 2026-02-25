"""飞书、钉钉、企业微信配置数据"""

from typing import Any

__all__ = ["get_feishu_configs", "get_dingtalk_configs", "get_wechat_work_configs"]


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
        {
            "key": "FEISHU_TIMEOUT",
            "category": "feishu",
            "description": "飞书 API 超时时间（秒）",
            "value": "30",
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
        {
            "key": "CASE_CHAT_NAME_MAX_LENGTH",
            "category": "feishu",
            "description": "群聊名称最大长度（飞书限制为60）",
            "value": "60",
            "is_secret": False,
        },
    ]


def get_dingtalk_configs() -> list[dict[str, Any]]:
    """获取钉钉配置项"""
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
            "key": "DINGTALK_TIMEOUT",
            "category": "dingtalk",
            "description": "钉钉 API 超时时间（秒）",
            "value": "30",
            "is_secret": False,
        },
    ]


def get_wechat_work_configs() -> list[dict[str, Any]]:
    """获取企业微信配置项"""
    return [
        {
            "key": "WECHAT_WORK_CORP_ID",
            "category": "wechat_work",
            "description": "企业微信 Corp ID",
            "is_secret": False,
        },
        {
            "key": "WECHAT_WORK_AGENT_ID",
            "category": "wechat_work",
            "description": "企业微信 Agent ID",
            "is_secret": False,
        },
        {
            "key": "WECHAT_WORK_SECRET",
            "category": "wechat_work",
            "description": "企业微信应用 Secret",
            "is_secret": True,
        },
        {
            "key": "WECHAT_WORK_TIMEOUT",
            "category": "wechat_work",
            "description": "企业微信 API 超时时间（秒）",
            "value": "30",
            "is_secret": False,
        },
    ]
