"""
Infrastructure wiring - 服务依赖注入配置

此模块提供 documents services 所需的各种服务实例。
"""

from __future__ import annotations

from typing import Any


def get_case_service() -> Any:
    """获取案件服务实例"""
    from apps.cases.services.case.wiring import get_case_service as _get_case_service

    return _get_case_service()


def get_contract_service() -> Any:
    """获取合同服务实例"""
    from apps.contracts.services.contract.wiring import get_contract_service as _get_contract_service

    return _get_contract_service()


def get_client_service() -> Any:
    """获取客户/当事人服务实例"""
    from apps.core.service_locator import ServiceLocator

    return ServiceLocator.get_client_service()


def get_llm_service() -> Any:
    """获取 LLM 服务实例"""
    from apps.core.service_locator import ServiceLocator

    return ServiceLocator.get_llm_service()


def get_document_service() -> Any:
    """获取文档服务实例"""
    from apps.core.dependencies import build_document_service

    return build_document_service()


def get_analysis_service() -> Any:
    """获取外部模板分析服务实例"""
    from apps.documents.services.external_template.analysis_service import AnalysisService
    from apps.documents.services.external_template.fingerprint_service import FingerprintService
    from apps.documents.services.placeholders.registry import PlaceholderRegistry

    return AnalysisService(
        fingerprint_service=FingerprintService(),
        llm_service=get_llm_service(),
        placeholder_registry=PlaceholderRegistry(),
    )


def get_filling_service() -> Any:
    """获取外部模板填充服务实例"""
    from apps.documents.services.external_template.filling_service import FillingService
    from apps.documents.services.placeholders.registry import PlaceholderRegistry

    return FillingService(placeholder_registry=PlaceholderRegistry())


def get_matching_service() -> Any:
    """获取外部模板匹配服务实例"""
    from apps.documents.services.external_template.matching_service import MatchingService

    return MatchingService()


def get_evidence_list_placeholder_service() -> Any:
    """获取证据清单占位符服务实例"""
    from apps.evidence.services.evidence_list_placeholder_service import EvidenceListPlaceholderService

    return EvidenceListPlaceholderService()
