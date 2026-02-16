"""Dependency injection wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.core.protocols import (
        IAutoTokenAcquisitionService,
        IBaoquanTokenService,
        ICauseCourtQueryService,
        ICourtTokenStoreService,
        IDocumentService,
        ILLMService,
        IOrganizationService,
    )


def get_llm_service() -> ILLMService:
    return ServiceLocator.get_llm_service()


def get_document_service() -> IDocumentService:
    return ServiceLocator.get_document_service()


def get_cause_court_query_service() -> ICauseCourtQueryService:
    return ServiceLocator.get_cause_court_query_service()


def get_baoquan_token_service() -> IBaoquanTokenService:
    return ServiceLocator.get_baoquan_token_service()


def get_organization_service() -> IOrganizationService:
    return ServiceLocator.get_organization_service()


def get_court_token_store_service() -> ICourtTokenStoreService:
    return ServiceLocator.get_court_token_store_service()


def get_auto_token_acquisition_service() -> IAutoTokenAcquisitionService:
    return ServiceLocator.get_auto_token_acquisition_service()


def get_anti_detection() -> Any:
    """获取反检测模块(通过 dependencies 层延迟导入)"""
    from apps.core.dependencies.automation_browser import get_anti_detection as _get

    return _get()


def get_court_zxfw_service_factory(*, page: Any, context: Any, site_name: str = "court_zxfw") -> Any:
    """创建法院一张网服务实例(通过 dependencies 层延迟导入)"""
    from apps.core.dependencies.automation_browser import create_court_zxfw_service

    return create_court_zxfw_service(page=page, context=context, site_name=site_name)
