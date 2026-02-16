"""Dependency injection wiring."""

from __future__ import annotations

from apps.core.interfaces import ServiceLocator

from .authorization_material_generation_service import AuthorizationMaterialGenerationService


def build_authorization_material_generation_service() -> AuthorizationMaterialGenerationService:
    return AuthorizationMaterialGenerationService(
        case_service=ServiceLocator.get_case_service(),
        client_service=ServiceLocator.get_client_service(),
        document_service=ServiceLocator.get_document_service(),
    )
