"""法院短信、AI、企业数据、爬虫等服务配置数据"""

from typing import Any

__all__ = ["get_court_sms_configs", "get_ai_configs", "get_enterprise_data_configs", "get_scraper_configs", "get_ocr_configs"]


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
            "key": "LLM_DEFAULT_BACKEND",
            "category": "ai",
            "description": "默认 LLM 后端（siliconflow/ollama/openai_compatible）",
            "value": "siliconflow",
            "is_secret": False,
        },
        {
            "key": "OLLAMA_MODEL",
            "category": "ai",
            "description": "Ollama 模型名称",
            "value": "qwen3.5:0.8b",
            "is_secret": False,
        },
        {
            "key": "OLLAMA_EMBEDDING_MODEL",
            "category": "ai",
            "description": "Ollama 向量模型名称（默认沿用 OLLAMA_MODEL）",
            "value": "",
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
            "value": "<SILICONFLOW_API_KEY>",
            "is_secret": True,
        },
        {
            # Faker
            "key": "SILICONFLOW_BASE_URL",
            "category": "ai",
            "description": "硅基流动 API 地址",
            "value": "https://api.siliconflow.cn/v1",
            "is_secret": False,
        },
        {
            "key": "SILICONFLOW_MODEL",
            "category": "ai",
            "description": "硅基流动模型名称（兼容旧键，建议改用 SILICONFLOW_DEFAULT_MODEL）",
            "value": "Pro/Qwen/Qwen3-0.6B",
            "is_secret": False,
        },
        {
            "key": "SILICONFLOW_DEFAULT_MODEL",
            "category": "ai",
            "description": "硅基流动默认对话模型名称",
            "value": "Pro/Qwen/Qwen3-0.6B",
            "is_secret": False,
        },
        {
            "key": "SILICONFLOW_EMBEDDING_MODEL",
            "category": "ai",
            "description": "硅基流动向量模型名称（默认沿用 SILICONFLOW_DEFAULT_MODEL）",
            "value": "",
            "is_secret": False,
        },
        {
            "key": "OPENAI_COMPATIBLE_API_KEY",
            "category": "ai",
            "description": "OpenAI-compatible API Key（Moonshot/Kimi/DeepSeek 等）",
            "value": "<OPENAI_COMPATIBLE_API_KEY>",
            "is_secret": True,
        },
        {
            "key": "OPENAI_COMPATIBLE_BASE_URL",
            "category": "ai",
            "description": "OpenAI-compatible API 地址",
            "value": "https://api.moonshot.cn/v1",
            "is_secret": False,
        },
        {
            "key": "OPENAI_COMPATIBLE_DEFAULT_MODEL",
            "category": "ai",
            "description": "OpenAI-compatible 默认对话模型名称",
            "value": "moonshot-v1-8k",
            "is_secret": False,
        },
        {
            "key": "OPENAI_COMPATIBLE_EMBEDDING_MODEL",
            "category": "ai",
            "description": "OpenAI-compatible 向量模型名称（默认沿用 DEFAULT_MODEL）",
            "value": "",
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


def get_enterprise_data_configs() -> list[dict[str, Any]]:
    """获取企业数据配置项（仅保留用户真正需要配置的项）"""
    return [
        {
            "key": "TIANYANCHA_MCP_BASE_URL",
            "category": "enterprise_data",
            "description": "天眼查 MCP Streamable-HTTP 地址",
            "value": "https://mcp-service.tianyancha.com/mcp",
            "is_secret": False,
        },
        {
            "key": "TIANYANCHA_MCP_SSE_URL",
            "category": "enterprise_data",
            "description": "天眼查 MCP SSE 地址",
            "value": "https://mcp-service.tianyancha.com/sse",
            "is_secret": False,
        },
        {
            "key": "TIANYANCHA_MCP_API_KEY",
            "category": "enterprise_data",
            "description": "天眼查 MCP API Key（Bearer Token，支持多 Key；每行一个）",
            "value": "sk_qJKABWT2vMAa0c35LJOtzg2dougEOzab",  # pragma: allowlist secret
            "is_secret": True,
        },
    ]


def get_ocr_configs() -> list[dict[str, Any]]:
    """获取 OCR 服务配置项"""
    return [
        {
            "key": "OCR_PROVIDER",
            "category": "ocr",
            "description": "OCR 引擎选择（local=本地 RapidOCR / paddleocr_api=百度 PaddleOCR API）",
            "value": "local",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_API_MODEL",
            "category": "ocr",
            "description": (
                "PaddleOCR API 模型选择（"
                "pp_ocrv5=纯文字OCR-适合证件/快递单号/简单文字提取, "
                "pp_structure_v3=文档结构化-适合表格/版面分析, "
                "paddleocr_vl=版面分析+OCR-适合复杂文档/合同, "
                "paddleocr_vl_1_5=高精度版面分析-适合法律文书/密集排版文档）"
            ),
            "value": "pp_ocrv5",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_OCR_API_URL",
            "category": "ocr",
            "description": "PaddleOCR OCR 接口地址（PP-OCRv5 / PP-StructureV3 共用）",
            "value": "",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_VL_API_URL",
            "category": "ocr",
            "description": "PaddleOCR-VL 版面分析接口地址",
            "value": "",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_VL15_API_URL",
            "category": "ocr",
            "description": "PaddleOCR-VL-1.5 高精度版面分析接口地址",
            "value": "",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_API_TOKEN",
            "category": "ocr",
            "description": "PaddleOCR API Token（Authorization: token {TOKEN}）",
            "value": "",
            "is_secret": True,
        },
    ]
