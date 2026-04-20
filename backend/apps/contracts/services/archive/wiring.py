"""归档服务工厂函数"""

from __future__ import annotations

from .checklist_service import ArchiveChecklistService


def build_archive_checklist_service() -> ArchiveChecklistService:
    """构建归档检查清单服务实例"""
    return ArchiveChecklistService()
