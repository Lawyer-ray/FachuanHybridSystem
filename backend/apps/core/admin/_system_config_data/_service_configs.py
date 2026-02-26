"""法院短信、AI、爬虫等服务配置数据"""

from typing import Any

__all__ = ["get_court_sms_configs", "get_ai_configs", "get_scraper_configs"]


def get_court_sms_configs() -> list[dict[str, Any]]:
    """获取法院短信与文书送达配置项"""
    return []


def get_ai_configs() -> list[dict[str, Any]]:
    """获取 AI 配置项"""
    return [
        {
            "key": "AI_PROVIDER",
            "category": "ai",
            "description": "AI 服务提供商（ollama/siliconflow）",
            "value": "siliconflow",
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
        {
            "key": "SILICONFLOW_API_KEY",
            "category": "ai",
            "description": "硅基流动 API Key",
            "is_secret": True,
        },
        {
            "key": "SILICONFLOW_BASE_URL",
            "category": "ai",
            "description": "硅基流动 API 地址",
            "value": "https://api.siliconflow.cn/v1",
            "is_secret": False,
        },
        {
            "key": "SILICONFLOW_MODEL",
            "category": "ai",
            "description": "硅基流动模型名称",
            "value": "Pro/Qwen/Qwen3-0.6B",
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
            "description": "爬虫下载目录",
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
