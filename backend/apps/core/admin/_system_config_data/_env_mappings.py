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
        "ENTERPRISE_DATA_DEFAULT_PROVIDER": {
            "key": "ENTERPRISE_DATA_DEFAULT_PROVIDER",
            "category": "enterprise_data",
            "description": "企业数据默认提供商",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_CACHE_TTL_SECONDS": {
            "key": "ENTERPRISE_DATA_CACHE_TTL_SECONDS",
            "category": "enterprise_data",
            "description": "企业数据缓存时长（秒）",
            "is_secret": False,
        },
        "TIANYANCHA_MCP_ENABLED": {
            "key": "TIANYANCHA_MCP_ENABLED",
            "category": "enterprise_data",
            "description": "启用天眼查 MCP",
            "is_secret": False,
        },
        "TIANYANCHA_MCP_TRANSPORT": {
            "key": "TIANYANCHA_MCP_TRANSPORT",
            "category": "enterprise_data",
            "description": "天眼查 MCP 传输协议",
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
            "description": "天眼查 MCP API Key",
            "is_secret": True,
        },
        "TIANYANCHA_MCP_TIMEOUT_SECONDS": {
            "key": "TIANYANCHA_MCP_TIMEOUT_SECONDS",
            "category": "enterprise_data",
            "description": "天眼查 MCP 超时时间（秒）",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_RATE_LIMIT_REQUESTS": {
            "key": "ENTERPRISE_DATA_RATE_LIMIT_REQUESTS",
            "category": "enterprise_data",
            "description": "企业数据限流最大请求数",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_RATE_LIMIT_WINDOW_SECONDS": {
            "key": "ENTERPRISE_DATA_RATE_LIMIT_WINDOW_SECONDS",
            "category": "enterprise_data",
            "description": "企业数据限流窗口时长（秒）",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_RETRY_MAX_ATTEMPTS": {
            "key": "ENTERPRISE_DATA_RETRY_MAX_ATTEMPTS",
            "category": "enterprise_data",
            "description": "企业数据重试上限",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_RETRY_BACKOFF_SECONDS": {
            "key": "ENTERPRISE_DATA_RETRY_BACKOFF_SECONDS",
            "category": "enterprise_data",
            "description": "企业数据重试退避时间（秒）",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_METRICS_WINDOW_SECONDS": {
            "key": "ENTERPRISE_DATA_METRICS_WINDOW_SECONDS",
            "category": "enterprise_data",
            "description": "企业数据指标聚合窗口（秒）",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_ALERT_MIN_SAMPLES": {
            "key": "ENTERPRISE_DATA_ALERT_MIN_SAMPLES",
            "category": "enterprise_data",
            "description": "企业数据告警最小样本数",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_ALERT_SUCCESS_RATE_THRESHOLD": {
            "key": "ENTERPRISE_DATA_ALERT_SUCCESS_RATE_THRESHOLD",
            "category": "enterprise_data",
            "description": "企业数据成功率告警阈值",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_ALERT_FALLBACK_RATE_THRESHOLD": {
            "key": "ENTERPRISE_DATA_ALERT_FALLBACK_RATE_THRESHOLD",
            "category": "enterprise_data",
            "description": "企业数据回退率告警阈值",
            "is_secret": False,
        },
        "ENTERPRISE_DATA_ALERT_AVG_LATENCY_MS_THRESHOLD": {
            "key": "ENTERPRISE_DATA_ALERT_AVG_LATENCY_MS_THRESHOLD",
            "category": "enterprise_data",
            "description": "企业数据平均耗时告警阈值（毫秒）",
            "is_secret": False,
        },
        "QICHACHA_MCP_ENABLED": {
            "key": "QICHACHA_MCP_ENABLED",
            "category": "enterprise_data",
            "description": "启用企查查 MCP",
            "is_secret": False,
        },
        "QICHACHA_MCP_TRANSPORT": {
            "key": "QICHACHA_MCP_TRANSPORT",
            "category": "enterprise_data",
            "description": "企查查 MCP 传输协议",
            "is_secret": False,
        },
        "QICHACHA_MCP_BASE_URL": {
            "key": "QICHACHA_MCP_BASE_URL",
            "category": "enterprise_data",
            "description": "企查查 MCP Streamable-HTTP 地址",
            "is_secret": False,
        },
        "QICHACHA_MCP_SSE_URL": {
            "key": "QICHACHA_MCP_SSE_URL",
            "category": "enterprise_data",
            "description": "企查查 MCP SSE 地址",
            "is_secret": False,
        },
        "QICHACHA_MCP_API_KEY": {
            "key": "QICHACHA_MCP_API_KEY",
            "category": "enterprise_data",
            "description": "企查查 MCP API Key",
            "is_secret": True,
        },
        "QICHACHA_MCP_TIMEOUT_SECONDS": {
            "key": "QICHACHA_MCP_TIMEOUT_SECONDS",
            "category": "enterprise_data",
            "description": "企查查 MCP 超时时间（秒）",
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
