"""案件处理工作流 - 跨 skill 公共模块。

提供后端 API 客户端(httpx 封装)和配置加载,供工作流内所有 skill 复用。
"""

from .http_client import (
    DEFAULT_BASE_URL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLL_TIMEOUT,
    APIClient,
    DocumentParsingClient,
    build_api_client,
)

__all__ = [
    'APIClient',
    'DocumentParsingClient',
    'build_api_client',
    'DEFAULT_BASE_URL',
    'DEFAULT_POLL_INTERVAL',
    'DEFAULT_POLL_TIMEOUT',
]
