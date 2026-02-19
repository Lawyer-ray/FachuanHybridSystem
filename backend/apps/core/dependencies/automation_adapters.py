"""Module for automation adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.core.protocols import (
        IAutomationService,
        IAutoNamerService,
        ICourtDocumentRecognitionService,
        ICourtPleadingSignalsService,
        IDocumentProcessingService,
        IPerformanceMonitorService,
    )


def build_document_processing_service() -> IDocumentProcessingService:
    from apps.automation.services.document.document_processing_service_adapter import DocumentProcessingServiceAdapter

    return DocumentProcessingServiceAdapter()


def build_auto_namer_service() -> IAutoNamerService:
    from apps.automation.services.ai.auto_namer_service_adapter import AutoNamerServiceAdapter

    return AutoNamerServiceAdapter()


def build_automation_service() -> IAutomationService:
    from apps.automation.services.automation_service_adapter import AutomationServiceAdapter

    return AutomationServiceAdapter()


def build_performance_monitor_service() -> IPerformanceMonitorService:
    from apps.automation.services.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

    return PerformanceMonitorServiceAdapter()


def build_court_document_recognition_service() -> ICourtDocumentRecognitionService:
    from apps.automation.services.court_document_recognition.adapter import CourtDocumentRecognitionServiceAdapter

    return CourtDocumentRecognitionServiceAdapter()


def build_court_pleading_signals_service() -> ICourtPleadingSignalsService:
    from apps.automation.services.litigation.court_pleading_signals_service_adapter import (
        CourtPleadingSignalsServiceAdapter,
    )

    return CourtPleadingSignalsServiceAdapter()


def build_ai_service() -> Any:
    from apps.automation.services.ai.ai_service import AIService
    from apps.core.dependencies.core import build_llm_service

    return AIService(llm_service=build_llm_service())  # type: ignore[arg-type]


def build_automation_config_service() -> Any:
    from apps.automation.services.config_service import AutomationConfigService

    return AutomationConfigService()
