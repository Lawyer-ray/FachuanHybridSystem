"""Dependency injection wiring."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_case_service() -> Any:
    return ServiceLocator.get_case_service()


def get_contract_service() -> Any:
    return ServiceLocator.get_contract_service()


def get_contract_query_service() -> Any:
    return ServiceLocator.get_contract_query_service()


def get_client_service() -> Any:
    return ServiceLocator.get_client_service()


def get_lawyer_service() -> Any:
    return ServiceLocator.get_lawyer_service()


def get_document_service() -> Any:
    return ServiceLocator.get_document_service()


def get_evidence_service() -> Any:
    return ServiceLocator.get_evidence_service()


def get_evidence_query_service() -> Any:
    return ServiceLocator.get_evidence_query_service()


def get_file_storage() -> Any:
    return ServiceLocator.get_file_storage()


def get_preservation_quote_service() -> Any:
    return ServiceLocator.get_preservation_quote_service()


def get_evidence_list_placeholder_service() -> Any:
    return ServiceLocator.get_evidence_list_placeholder_service()


def get_llm_service() -> Any:
    return ServiceLocator.get_llm_service()
