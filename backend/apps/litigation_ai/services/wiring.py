"""Dependency injection wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.core.protocols import (
        ICaseService,
        IConversationHistoryService,
        ICourtPleadingSignalsService,
        IDocumentService,
        IEvidenceQueryService,
        IGenerationTaskService,
        ILLMService,
    )


def get_document_service() -> IDocumentService:
    return ServiceLocator.get_document_service()


def get_case_service() -> ICaseService:
    return ServiceLocator.get_case_service()


def get_evidence_service() -> object:
    return ServiceLocator.get_evidence_service()


def get_evidence_query_service() -> IEvidenceQueryService:
    return ServiceLocator.get_evidence_query_service()


def get_conversation_history_service() -> IConversationHistoryService:
    return ServiceLocator.get_conversation_history_service()


def get_court_pleading_signals_service() -> ICourtPleadingSignalsService:
    return ServiceLocator.get_court_pleading_signals_service()


def get_generation_task_service() -> IGenerationTaskService:
    return ServiceLocator.get_generation_task_service()


def get_llm_service() -> ILLMService:
    return ServiceLocator.get_llm_service()
