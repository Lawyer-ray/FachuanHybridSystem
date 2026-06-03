"""Core 模块 Admin 配置"""

from . import cause_of_action_admin, court_admin
from ..cloud_storage import admin as cloud_storage_admin  # noqa: F401
from .system_config_admin import SystemConfigAdmin

__all__ = ["SystemConfigAdmin"]
