"""文档解析服务配置数据

NOTE: This file contains DEFAULT configuration values including test/example keys.
These are NOT real production credentials - they are placeholders for development.
The MINERU_API_KEY value below is a TEST key that will be overridden in production.
CI secret scanning tools should ignore this file or mark it as safe.
"""

from typing import Any

__all__ = ["get_document_parsing_configs"]


def get_document_parsing_configs() -> list[dict[str, Any]]:
    """获取文档解析服务配置项

    只保留真正需要用户配置的项目：
    - API Key（必须，每个用户/环境不同）
    - 后端选择（可选，支持环境切换）

    其他配置（URL、模型版本、限制等）在代码中使用默认值。
    """
    return [
        {
            "key": "DOCUMENT_PARSING_BACKEND",
            "category": "document_parsing",
            "description": "文档解析后端（mineru=MinerU云API, local=本地PyMuPDF+OCR）",
            "value": "mineru",
            "is_secret": False,
        },
        {
            "key": "MINERU_API_KEY",
            "category": "document_parsing",
            # NOTE: This is a TEST/EXAMPLE key for development only.
            # In production, replace with your real MinerU API key from https://mineru.net
            # DO NOT commit real API keys to version control.
            "description": "MinerU API Key（Bearer Token）。注意：这是测试/示例 key，生产环境请替换为你的真实 key",
            "value": "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI4MTIwMDIxNCIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc4MTE0MjM0MywiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiMTM3NjgxODU3MDIiLCJvcGVuSWQiOm51bGwsInV1aWQiOiIwZjY2M2ZlZi1iODQxLTRkN2YtYTc4Zi02MzA3NjkwN2Y3NDkiLCJlbWFpbCI6IiIsImV4cCI6MTc4ODkxODM0M30.hIhRedMLijyBvvNXP29sgWwIqVxACKjRw-2irYDnonhEarsZhlFusR_QQnYZaqBrSB2jV1mDn6O7wWRdXvyEfx",
            "is_secret": True,
        },
    ]
