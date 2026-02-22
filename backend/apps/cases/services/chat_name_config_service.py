"""
群聊名称配置服务 - 纯重导出文件

所有实现已迁移到 services/chat/ 子目录.
本文件仅做重导出,保持向后兼容性.
"""

from __future__ import annotations

from apps.cases.services.chat.chat_name_config_service import ChatNameConfigService

__all__ = ["ChatNameConfigService"]
