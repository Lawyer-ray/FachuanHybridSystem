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
        "CASE_CHAT_NAME_TEMPLATE": {
            "key": "CASE_CHAT_NAME_TEMPLATE",
            "category": "feishu",
            "description": "群聊名称模板",
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
        "DINGTALK_DEFAULT_OWNER_ID": {
            "key": "DINGTALK_DEFAULT_OWNER_ID",
            "category": "dingtalk",
            "description": "钉钉默认群主 userid",
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
        "WECHAT_WORK_DEFAULT_OWNER_ID": {
            "key": "WECHAT_WORK_DEFAULT_OWNER_ID",
            "category": "wechat_work",
            "description": "企业微信默认群主 userid",
            "is_secret": False,
        },
        "TELEGRAM_BOT_TOKEN": {
            "key": "TELEGRAM_BOT_TOKEN",
            "category": "telegram",
            "description": "Telegram Bot Token",
            "is_secret": True,
        },
        "TELEGRAM_SUPERGROUP_ID": {
            "key": "TELEGRAM_SUPERGROUP_ID",
            "category": "telegram",
            "description": "Telegram 超级群组 ID",
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
        "SILICONFLOW_DEFAULT_MODEL": {
            "key": "SILICONFLOW_DEFAULT_MODEL",
            "category": "ai",
            "description": "硅基流动默认对话模型名称",
            "is_secret": False,
        },
        "SILICONFLOW_EMBEDDING_MODEL": {
            "key": "SILICONFLOW_EMBEDDING_MODEL",
            "category": "ai",
            "description": "硅基流动向量模型名称",
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
        "OLLAMA_TIMEOUT": {
            "key": "OLLAMA_TIMEOUT",
            "category": "ai",
            "description": "Ollama 请求超时时间（秒）",
            "is_secret": False,
        },
        "OLLAMA_EMBEDDING_MODEL": {
            "key": "OLLAMA_EMBEDDING_MODEL",
            "category": "ai",
            "description": "Ollama 向量模型名称",
            "is_secret": False,
        },
        "OPENAI_COMPATIBLE_API_KEY": {
            "key": "OPENAI_COMPATIBLE_API_KEY",
            "category": "ai",
            "description": "OpenAI-compatible API Key",
            "is_secret": True,
        },
        "OPENAI_COMPATIBLE_BASE_URL": {
            "key": "OPENAI_COMPATIBLE_BASE_URL",
            "category": "ai",
            "description": "OpenAI-compatible API 地址",
            "is_secret": False,
        },
        "OPENAI_COMPATIBLE_DEFAULT_MODEL": {
            "key": "OPENAI_COMPATIBLE_DEFAULT_MODEL",
            "category": "ai",
            "description": "OpenAI-compatible 默认对话模型名称",
            "is_secret": False,
        },
        "OPENAI_COMPATIBLE_EMBEDDING_MODEL": {
            "key": "OPENAI_COMPATIBLE_EMBEDDING_MODEL",
            "category": "ai",
            "description": "OpenAI-compatible 向量模型名称",
            "is_secret": False,
        },
        "LLM_DEFAULT_BACKEND": {
            "key": "LLM_DEFAULT_BACKEND",
            "category": "ai",
            "description": "默认 LLM 后端",
            "is_secret": False,
        },
        "TIANYANCHA_MCP_TRANSPORT": {
            "key": "TIANYANCHA_MCP_TRANSPORT",
            "category": "enterprise_data",
            "description": "天眼查 MCP 传输协议（streamable_http 或 sse）",
            "is_secret": False,
        },
        "TIANYANCHA_MCP_BASE_URL": {
            "key": "TIANYANCHA_MCP_BASE_URL",
            "category": "enterprise_data",
            "description": "天眼查 MCP Streamable-HTTP 地址",
            "is_secret": False,
        },
        "TIANYANCHA_MCP_SSE_URL": {
            "key": "TIANYANCHA_MCP_SSE_URL",
            "category": "enterprise_data",
            "description": "天眼查 MCP SSE 地址",
            "is_secret": False,
        },
        "TIANYANCHA_MCP_API_KEY": {
            "key": "TIANYANCHA_MCP_API_KEY",
            "category": "enterprise_data",
            "description": "天眼查 MCP API Key（支持多 Key；可用换行、逗号或分号分隔）",
            "is_secret": True,
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
