"""法院短信、AI、爬虫等服务配置数据"""

from typing import Any

__all__ = ["get_court_sms_configs", "get_ai_configs", "get_scraper_configs"]


def get_court_sms_configs() -> list[dict[str, Any]]:
    """获取法院短信与文书送达配置项"""
    return [
        # ============ 法院短信配置 ============
        {
            "key": "COURT_SMS_ENABLED",
            "category": "court_sms",
            "description": "启用法院短信处理功能",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "COURT_SMS_MAX_RETRIES",
            "category": "court_sms",
            "description": "法院短信处理最大重试次数",
            "value": "3",
            "is_secret": False,
        },
        {
            "key": "COURT_SMS_RETRY_DELAY",
            "category": "court_sms",
            "description": "法院短信处理重试延迟（秒）",
            "value": "60",
            "is_secret": False,
        },
        {
            "key": "COURT_SMS_AUTO_RECOVERY",
            "category": "court_sms",
            "description": "法院短信自动恢复",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "COURT_SMS_NOTIFY_ON_SUCCESS",
            "category": "court_sms",
            "description": "短信处理成功时发送通知",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "COURT_SMS_NOTIFY_ON_FAILURE",
            "category": "court_sms",
            "description": "短信处理失败时发送通知",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "COURT_SMS_AUTO_MATCH_CASE",
            "category": "court_sms",
            "description": "自动匹配案件",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "COURT_SMS_DOWNLOAD_TIMEOUT",
            "category": "court_sms",
            "description": "文书下载超时时间（秒）",
            "value": "120",
            "is_secret": False,
        },
        # ============ 文书送达配置 ============
        {
            "key": "DOCUMENT_DELIVERY_ENABLED",
            "category": "court_sms",
            "description": "启用文书送达自动处理",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "DOCUMENT_DELIVERY_SCHEDULE",
            "category": "court_sms",
            "description": "文书送达检查时间（cron 格式）",
            "value": "0 9,14,18 * * *",
            "is_secret": False,
        },
        {
            "key": "DOCUMENT_DELIVERY_BATCH_SIZE",
            "category": "court_sms",
            "description": "文书送达批量处理数量",
            "value": "10",
            "is_secret": False,
        },
    ]


def get_ai_configs() -> list[dict[str, Any]]:
    """获取 AI 配置项"""
    return [
        {"key": "AI_ENABLED", "category": "ai", "description": "启用 AI 功能", "value": "True", "is_secret": False},
        {
            "key": "AI_PROVIDER",
            "category": "ai",
            "description": "AI 服务提供商（ollama/moonshot/openai）",
            "value": "ollama",
            "is_secret": False,
        },
        {
            "key": "OLLAMA_MODEL",
            "category": "ai",
            "description": "Ollama 模型名称",
            "value": "qwen3:0.6b",
            "is_secret": False,
        },
        {
            "key": "OLLAMA_BASE_URL",
            "category": "ai",
            "description": "Ollama API 地址",
            "value": "http://localhost:11434",
            "is_secret": False,
        },
        {"key": "OPENAI_API_KEY", "category": "ai", "description": "OpenAI API Key", "is_secret": True},
        {
            "key": "OPENAI_BASE_URL",
            "category": "ai",
            "description": "OpenAI API 地址（可用于代理）",
            "value": "https://api.openai.com/v1",
            "is_secret": False,
        },
        {
            "key": "OPENAI_MODEL",
            "category": "ai",
            "description": "OpenAI 模型名称",
            "value": "gpt-3.5-turbo",
            "is_secret": False,
        },
        {
            "key": "AI_AUTO_NAMING_ENABLED",
            "category": "ai",
            "description": "启用 AI 自动命名功能",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "AI_CASE_ANALYSIS_ENABLED",
            "category": "ai",
            "description": "启用 AI 案件分析功能",
            "value": "False",
            "is_secret": False,
        },
    ]


def get_scraper_configs() -> list[dict[str, Any]]:
    """获取爬虫与 Token 配置项"""
    return [
        # ============ 爬虫配置 ============
        {
            "key": "SCRAPER_ENABLED",
            "category": "scraper",
            "description": "启用爬虫功能",
            "value": "True",
            "is_secret": False,
        },
        {"key": "SCRAPER_ENCRYPTION_KEY", "category": "scraper", "description": "爬虫加密密钥", "is_secret": True},
        {
            "key": "SCRAPER_HEADLESS",
            "category": "scraper",
            "description": "爬虫是否使用无头模式",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "SCRAPER_TIMEOUT",
            "category": "scraper",
            "description": "爬虫页面加载超时时间（秒）",
            "value": "60",
            "is_secret": False,
        },
        {
            "key": "SCRAPER_MAX_CONCURRENT",
            "category": "scraper",
            "description": "爬虫最大并发数",
            "value": "3",
            "is_secret": False,
        },
        {
            "key": "SCRAPER_RETRY_COUNT",
            "category": "scraper",
            "description": "爬虫失败重试次数",
            "value": "3",
            "is_secret": False,
        },
        {
            "key": "SCRAPER_DOWNLOAD_DIR",
            "category": "scraper",
            "description": "��虫下载目录",
            "value": "/tmp/scraper_downloads",  # nosec B108
            "is_secret": False,
        },
        # ============ Token 获取配置 ============
        {
            "key": "TOKEN_AUTO_REFRESH_ENABLED",
            "category": "scraper",
            "description": "启用 Token 自动刷新",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "TOKEN_REFRESH_INTERVAL",
            "category": "scraper",
            "description": "Token 刷新间隔（分钟）",
            "value": "30",
            "is_secret": False,
        },
        {
            "key": "TOKEN_CACHE_TTL",
            "category": "scraper",
            "description": "Token 缓存有效期（秒）",
            "value": "3600",
            "is_secret": False,
        },
    ]
