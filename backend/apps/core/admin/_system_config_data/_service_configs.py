"""法院短信、AI、企业数据、爬虫等服务配置数据"""

from typing import Any

__all__ = [
    "get_court_sms_configs",
    "get_ai_configs",
    "get_enterprise_data_configs",
    "get_scraper_configs",
    "get_ocr_configs",
]


def get_court_sms_configs() -> list[dict[str, Any]]:
    """获取法院短信与文书送达配置项"""
    return []


def get_ai_configs() -> list[dict[str, Any]]:
    """获取 AI 配置项（仅保留用户必须配置的项，其余由代码默认值兜底）"""
    return [
        {
            "key": "SILICONFLOW_API_KEY",
            "category": "ai",
            "description": "硅基流动 API Key",
            "value": "<SILICONFLOW_API_KEY>",
            "is_secret": True,
        },
        {
            "key": "SILICONFLOW_DEFAULT_MODEL",
            "category": "ai",
            "description": "硅基流动默认对话模型名称（从在线模型列表中选择）",
            "value": "Pro/Qwen/Qwen3-0.6B",
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
            "key": "OPENAI_COMPATIBLE_API_KEY",
            "category": "ai",
            "description": "OpenAI-compatible API Key（Moonshot/Kimi/DeepSeek 等）",
            "value": "<OPENAI_COMPATIBLE_API_KEY>",
            "is_secret": True,
        },
    ]


def get_scraper_configs() -> list[dict[str, Any]]:
    """获取爬虫配置项（仅保留用户必须配置的项）"""
    return [
        {"key": "SCRAPER_ENCRYPTION_KEY", "category": "scraper", "description": "爬虫加密密钥", "is_secret": True},
        {
            "key": "SCRAPER_HEADLESS",
            "category": "scraper",
            "description": "爬虫是否使用无头模式（默认根据 DEBUG 模式自动判断）",
            "value": "True",
            "is_secret": False,
        },
    ]


def get_enterprise_data_configs() -> list[dict[str, Any]]:
    """获取企业数据配置项（仅保留用户必须配置的项）"""
    return [
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
            "value": "https://ndvex8b5vcd0teg7.aistudio-app.com/ocr",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_VL_API_URL",
            "category": "ocr",
            "description": "PaddleOCR-VL 版面分析接口地址",
            "value": "https://h8d58fh8mfw84cj4.aistudio-app.com/layout-parsing",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_VL15_API_URL",
            "category": "ocr",
            "description": "PaddleOCR-VL-1.5 高精度版面分析接口地址",
            "value": "https://k4j5n7j1afr2j9p5.aistudio-app.com/layout-parsing",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_API_TOKEN",
            "category": "ocr",
            "description": "PaddleOCR API Token（Authorization: token {TOKEN}）",
            "value": "7c120d2b6d1c17b97e755ca59f82b6ecb28a6ee9",  # pragma: allowlist secret
            "is_secret": True,
        },
    ]
