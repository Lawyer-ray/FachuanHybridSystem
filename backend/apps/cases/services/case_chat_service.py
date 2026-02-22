"""
案件群聊服务 - 纯重导出文件

所有实现已迁移到 services/chat/ 子目录.
本文件仅做重导出,保持向后兼容性.
"""

from __future__ import annotations

from apps.cases.services.chat.case_chat_service import CaseChatService

__all__ = ["CaseChatService"]
