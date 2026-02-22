"""Dependency injection wiring."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_contract_domain_service() -> Any:
    return ServiceLocator.get_contract_service().contract_service  # type: ignore


def get_contract_mutation_facade() -> Any:
    return get_contract_domain_service().mutation_facade


def get_contract_query_facade() -> Any:
    return get_contract_domain_service().query_facade


def get_case_service() -> Any:
    return ServiceLocator.get_case_service()


def get_reminder_service() -> Any:
    return ServiceLocator.get_reminder_service()


def get_contract_generation_service() -> Any:
    return ServiceLocator.get_contract_generation_service()


def get_supplementary_agreement_generation_service() -> Any:
    return ServiceLocator.get_supplementary_agreement_generation_service()


def get_contract_folder_binding_service() -> Any:
    return ServiceLocator.get_contract_folder_binding_service()


def get_document_service() -> Any:
    return ServiceLocator.get_document_service()
