"""
Repository 层

负责数据访问,封装 Model.objects 操作
"""

from .system_config_repository import SystemConfigRepository

__all__ = ["SystemConfigRepository"]
