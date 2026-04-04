"""
Core 模块服务层

提供核心业务服务,包括:
- CourtApiClient: 法院 API 客户端
- CauseCourtInitializationService: 案由法院数据初始化服务
- InitializationResult: 初始化结果数据类
- SystemConfigService: 系统配置服务
- BusinessConfigService: 业务配置服务
- ConversationService: 对话服务
"""

from typing import Any

from .business_config_service import BusinessConfigService
from .cause_court_initialization_service import CauseCourtInitializationService, InitializationResult
from .court_api_client import CourtApiClient
from .system_config_service import SystemConfigService
from .system_update_service import SystemUpdateService

__all__ = [
    "BusinessConfigService",
    "CauseCourtInitializationService",
    "ConversationService",
    "CourtApiClient",
    "InitializationResult",
    "SystemConfigService",
    "SystemUpdateService",
]


def __getattr__(name: str) -> Any:
    if name == "ConversationService":
        from .conversation_service import ConversationService

        return ConversationService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
