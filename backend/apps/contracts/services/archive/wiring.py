"""归档服务工厂函数"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .checklist import ArchiveChecklistService

if TYPE_CHECKING:
    from .generation import ArchiveGenerationService
    from .learning_service import ArchiveLearningService


def build_archive_checklist_service() -> ArchiveChecklistService:
    """构建归档检查清单服务实例"""
    return ArchiveChecklistService()


def build_archive_generation_service() -> ArchiveGenerationService:
    """构建归档文书生成服务实例。"""
    # 从包路径导入，与既有调用方/测试的补丁点（archive.ArchiveGenerationService）一致
    from apps.contracts.services.archive import ArchiveGenerationService

    return ArchiveGenerationService()


def build_archive_learning_service() -> ArchiveLearningService:
    """构建归档分类规则学习服务实例。"""
    from .learning_service import ArchiveLearningService

    return ArchiveLearningService()
