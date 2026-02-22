"""
Repository 层

负责数据访问,封装 Model.objects 操作
"""

from .conversation_repository import ConversationHistoryRepository
from .prompt_template_repository import PromptTemplateRepository
from .system_config_repository import SystemConfigRepository

__all__ = [
    "SystemConfigRepository",
    "ConversationHistoryRepository",
    "PromptTemplateRepository",
]
