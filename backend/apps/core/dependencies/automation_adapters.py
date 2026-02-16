"""Module for automation adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

    return DocumentProcessingServiceAdapter()  # type: ignore[no-untyped-call]


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

    return CourtDocumentRecognitionServiceAdapter()  # type: ignore


def build_court_pleading_signals_service() -> ICourtPleadingSignalsService:
    from apps.automation.services.litigation.court_pleading_signals_service_adapter import (
        CourtPleadingSignalsServiceAdapter,
    )

    return CourtPleadingSignalsServiceAdapter()
