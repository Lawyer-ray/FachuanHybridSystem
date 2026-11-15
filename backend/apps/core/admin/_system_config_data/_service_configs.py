"""法院短信、AI、企业数据、爬虫等服务配置数据"""

import os
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
            "key": "OPENAI_COMPATIBLE_API_KEY",
            "category": "ai",
            "description": "OpenAI-compatible API Key（兼容旧配置，单 Key）。多平台 / 多 Key 并发请在「AI 平台」管理页配置",
            "value": "<OPENAI_COMPATIBLE_API_KEY>",
            "is_secret": True,
        },
        {
            "key": "OPENAI_COMPATIBLE_BASE_URL",
            "category": "ai",
            "description": "OpenAI-compatible API 地址（兼容旧配置，kimi26 vLLM）。多平台请在「AI 平台」管理页配置",
            # 默认网关 URL 可经 LLM_DEFAULT_BASE_URL 环境变量替换（回退值保持原网关，行为零变化）
            "value": os.environ.get("LLM_DEFAULT_BASE_URL", "http://116.196.92.175:8001/v1"),
            "is_secret": False,
        },
        {
            "key": "OPENAI_COMPATIBLE_DEFAULT_MODEL",
            "category": "ai",
            "description": "OpenAI-compatible 默认模型名称（兼容旧配置）",
            "value": "kimi26",
            "is_secret": False,
        },
    ]


def get_scraper_configs() -> list[dict[str, Any]]:
    """获取爬虫配置项（仅保留用户必须配置的项）"""
    return [
        {"key": "SCRAPER_ENCRYPTION_KEY", "category": "scraper", "description": "爬虫加密密钥", "is_secret": True},
        {
            "key": "PLAYWRIGHT_HEADED",
            "category": "scraper",
            "description": "Playwright 浏览器有头模式（true=显示浏览器窗口，便于调试；false=无头后台运行）",
            "value": "true",
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
        {
            "key": "QCC_MCP_API_KEY",
            "category": "enterprise_data",
            "description": "企查查 MCP API Key（Bearer Token，支持多 Key；每行一个）",
            "value": "M8AqueMrJJGv79nHRaEK72QxYTfrh4YF6W48UBpwA4aWeVmK",  # pragma: allowlist secret
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
            "value": "paddleocr_api",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_API_MODEL",
            "category": "ocr",
            "description": (
                "PaddleOCR API 模型选择（"
                "pp_ocrv6=纯文字OCR-快但生僻字易错, "
                "pp_structure_v3=文档结构化-适合表格/版面分析, "
                "paddleocr_vl=版面分析+OCR-适合复杂文档/合同, "
                "paddleocr_vl_1_5=高精度版面分析-适合法律文书/密集排版文档, "
                "paddleocr_vl_1_6=最新版-生僻字/印章增强，推荐法律文书使用）"
            ),
            "value": "paddleocr_vl_1_6",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_JOB_API_URL",
            "category": "ocr",
            "description": "PaddleOCR v2 异步 Job API 地址（所有模型共用，靠 model 参数区分产品线）",
            "value": "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs",
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
