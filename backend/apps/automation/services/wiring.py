"""Dependency injection wiring."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_case_service() -> Any:
    return ServiceLocator.get_case_service()


def get_case_chat_service() -> Any:
    return ServiceLocator.get_case_chat_service()


def get_case_number_service() -> Any:
    return ServiceLocator.get_case_number_service()


def get_organization_service() -> Any:
    return ServiceLocator.get_organization_service()


def get_system_config_service() -> Any:
    return ServiceLocator.get_system_config_service()


def get_document_service() -> Any:
    return ServiceLocator.get_document_service()


def get_document_processing_service() -> Any:
    return ServiceLocator.get_document_processing_service()


def get_auto_namer_service() -> Any:
    return ServiceLocator.get_auto_namer_service()


def get_auto_token_acquisition_service() -> Any:
    return ServiceLocator.get_auto_token_acquisition_service()


def get_preservation_quote_service() -> Any:
    return ServiceLocator.get_preservation_quote_service()


def get_court_pleading_signals_service() -> Any:
    return ServiceLocator.get_court_pleading_signals_service()


def get_court_document_service() -> Any:
    return ServiceLocator.get_court_document_service()


def get_evidence_service() -> Any:
    return ServiceLocator.get_evidence_service()


def get_evidence_query_service() -> Any:
    return ServiceLocator.get_evidence_query_service()


def get_litigation_fee_calculator_service() -> Any:
    return ServiceLocator.get_litigation_fee_calculator_service()


def get_cause_court_query_service() -> Any:
    return ServiceLocator.get_cause_court_query_service()


def get_llm_service() -> Any:
    return ServiceLocator.get_llm_service()


def get_court_sms_service() -> Any:
    return ServiceLocator.get_court_sms_service()


def get_token_service() -> Any:
    return ServiceLocator.get_token_service()


def get_baoquan_token_service() -> Any:
    return ServiceLocator.get_baoquan_token_service()


def get_task_service() -> Any:
    return ServiceLocator.get_task_service()


def get_browser_service() -> Any:
    return ServiceLocator.get_browser_service()


def get_captcha_service() -> Any:
    return ServiceLocator.get_captcha_service()


def get_validator_service() -> Any:
    return ServiceLocator.get_validator_service()


def get_security_service() -> Any:
    return ServiceLocator.get_security_service()


def get_monitor_service() -> Any:
    return ServiceLocator.get_monitor_service()
