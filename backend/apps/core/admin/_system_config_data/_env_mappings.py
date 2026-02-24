"""环境变量到配置的映射数据"""

from typing import Any

__all__ = ["get_env_mappings"]


def get_env_mappings() -> dict[str, dict[str, Any]]:
    """获取环境变量到配置的映射"""
    return {
        "FEISHU_APP_ID": {
            "key": "FEISHU_APP_ID",
            "category": "feishu",
            "description": "飞书应用 App ID",
            "is_secret": False,
        },
        "FEISHU_APP_SECRET": {
            "key": "FEISHU_APP_SECRET",
            "category": "feishu",
            "description": "飞书应用 App Secret",
            "is_secret": True,
        },
        "FEISHU_DEFAULT_OWNER_ID": {
            "key": "FEISHU_DEFAULT_OWNER_ID",
            "category": "feishu",
            "description": "飞书群聊默认群主 ID",
            "is_secret": False,
        },
        "FEISHU_TIMEOUT": {
            "key": "FEISHU_TIMEOUT",
            "category": "feishu",
            "description": "飞书 API 超时时间",
            "is_secret": False,
        },
        "CASE_CHAT_NAME_TEMPLATE": {
            "key": "CASE_CHAT_NAME_TEMPLATE",
            "category": "feishu",
            "description": "群聊名称模板",
            "is_secret": False,
        },
        "CASE_CHAT_DEFAULT_STAGE": {
            "key": "CASE_CHAT_DEFAULT_STAGE",
            "category": "feishu",
            "description": "默认阶段显示文本",
            "is_secret": False,
        },
        "CASE_CHAT_NAME_MAX_LENGTH": {
            "key": "CASE_CHAT_NAME_MAX_LENGTH",
            "category": "feishu",
            "description": "群聊名称最大长度",
            "is_secret": False,
        },
        "DINGTALK_APP_KEY": {
            "key": "DINGTALK_APP_KEY",
            "category": "dingtalk",
            "description": "钉钉应用 App Key",
            "is_secret": False,
        },
        "DINGTALK_APP_SECRET": {
            "key": "DINGTALK_APP_SECRET",
            "category": "dingtalk",
            "description": "钉钉应用 App Secret",
            "is_secret": True,
        },
        "DINGTALK_AGENT_ID": {
            "key": "DINGTALK_AGENT_ID",
            "category": "dingtalk",
            "description": "钉钉应用 Agent ID",
            "is_secret": False,
        },
        "DINGTALK_TIMEOUT": {
            "key": "DINGTALK_TIMEOUT",
            "category": "dingtalk",
            "description": "钉钉 API 超时时间",
            "is_secret": False,
        },
        "WECHAT_WORK_CORP_ID": {
            "key": "WECHAT_WORK_CORP_ID",
            "category": "wechat_work",
            "description": "企业微信 Corp ID",
            "is_secret": False,
        },
        "WECHAT_WORK_AGENT_ID": {
            "key": "WECHAT_WORK_AGENT_ID",
            "category": "wechat_work",
            "description": "企业微信 Agent ID",
            "is_secret": False,
        },
        "WECHAT_WORK_SECRET": {
            "key": "WECHAT_WORK_SECRET",
            "category": "wechat_work",
            "description": "企业微信应用 Secret",
            "is_secret": True,
        },
        "WECHAT_WORK_TIMEOUT": {
            "key": "WECHAT_WORK_TIMEOUT",
            "category": "wechat_work",
            "description": "企业微信 API 超时时间",
            "is_secret": False,
        },
        "SILICONFLOW_API_KEY": {
            "key": "SILICONFLOW_API_KEY",
            "category": "ai",
            "description": "硅基流动 API Key",
            "is_secret": True,
        },
        "SILICONFLOW_BASE_URL": {
            "key": "SILICONFLOW_BASE_URL",
            "category": "ai",
            "description": "硅基流动 API 地址",
            "is_secret": False,
        },
        "SILICONFLOW_MODEL": {
            "key": "SILICONFLOW_MODEL",
            "category": "ai",
            "description": "硅基流动模型名称",
            "is_secret": False,
        },
        "OLLAMA_MODEL": {
            "key": "OLLAMA_MODEL",
            "category": "ai",
            "description": "Ollama 模型名称",
            "is_secret": False,
        },
        "OLLAMA_BASE_URL": {
            "key": "OLLAMA_BASE_URL",
            "category": "ai",
            "description": "Ollama API 地址",
            "is_secret": False,
        },
        "SCRAPER_ENCRYPTION_KEY": {
            "key": "SCRAPER_ENCRYPTION_KEY",
            "category": "scraper",
            "description": "爬虫加密密钥",
            "is_secret": True,
        },
        "SCRAPER_HEADLESS": {
            "key": "SCRAPER_HEADLESS",
            "category": "scraper",
            "description": "爬虫无头模式",
            "is_secret": False,
        },
        "SCRAPER_TIMEOUT": {
            "key": "SCRAPER_TIMEOUT",
            "category": "scraper",
            "description": "爬虫超时时间",
            "is_secret": False,
        },
    }
