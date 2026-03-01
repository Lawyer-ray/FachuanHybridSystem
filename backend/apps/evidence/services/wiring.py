"""证据模块服务依赖注入配置"""

from __future__ import annotations

from typing import Any


def get_case_service() -> Any:
    """获取案件服务实例"""
    from apps.cases.services.case.wiring import get_case_service as _get_case_service

    return _get_case_service()


def get_evidence_list_placeholder_service() -> Any:
    """获取证据清单占位符服务实例"""
    from apps.evidence.services.evidence_list_placeholder_service import (
        EvidenceListPlaceholderService,
    )

    return EvidenceListPlaceholderService()
