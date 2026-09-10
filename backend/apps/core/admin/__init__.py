"""Core 模块 Admin 配置"""

from . import cause_of_action_admin, court_admin, llm_provider_admin, llm_record_admin, redis_queue_admin
from .system_config_admin import SystemConfigAdmin

__all__ = ["SystemConfigAdmin"]
