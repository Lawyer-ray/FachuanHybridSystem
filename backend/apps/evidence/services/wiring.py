"""证据模块服务依赖注入配置"""

from __future__ import annotations

from typing import Any


def get_case_service() -> Any:
    """获取案件服务实例"""
    from apps.core.infrastructure.service_locator import ServiceLocator

    return ServiceLocator.get_case_service()


def get_evidence_list_placeholder_service() -> Any:
    """获取证据清单占位符服务实例"""
    from apps.evidence.services.admin.evidence_list_placeholder_service import EvidenceListPlaceholderService

    return EvidenceListPlaceholderService()


def get_evidence_service() -> Any:
    """获取证据服务实例"""
    from apps.evidence.services.core.evidence_service import EvidenceService

    return EvidenceService(case_service=get_case_service())
