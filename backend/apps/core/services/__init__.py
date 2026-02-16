"""
Core 模块服务层

提供核心业务服务,包括:
- CourtApiClient: 法院 API 客户端
- CauseCourtInitializationService: 案由法院数据初始化服务
- InitializationResult: 初始化结果数据类
- SystemConfigService: 系统配置服务
- BusinessConfigService: 业务配置服务
- SystemConfigAdminService: 系统配置 Admin 服务
- PromptTemplateService: Prompt 模板服务
- ConversationService: 对话服务
"""

from .business_config_service import BusinessConfigService
from .cause_court_initialization_service import CauseCourtInitializationService, InitializationResult
from .court_api_client import CourtApiClient
from .prompt_template_service import PromptTemplateService
from .system_config_admin_service import SystemConfigAdminService
from .system_config_service import SystemConfigService

__all__ = [
    "BusinessConfigService",
    "CauseCourtInitializationService",
    "ConversationService",
    "CoreConversationService",
    "CourtApiClient",
    "InitializationResult",
    "PromptTemplateService",
    "SystemConfigAdminService",
    "SystemConfigService",
]


def __getattr__(name: str) -> type:
    if name == "ConversationService":
        from .conversation_service import ConversationService

        return ConversationService
    if name == "CoreConversationService":
        from .conversation_service import ConversationService

        return ConversationService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
