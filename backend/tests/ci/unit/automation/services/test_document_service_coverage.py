"""Tests for automation/services/scraper/court_document_service.py (missing: 20 lines)
+ automation/services/admin/document_delivery_schedule_admin_service.py (missing: 22 lines)
+ automation/models/preservation.py (missing: 2 lines)
+ automation/models/scraper.py (missing: 7 lines).

Covers: CourtDocumentService get_documents_by_task, get_document_by_id,
CourtDocumentServiceAdapter methods,
DocumentDeliveryScheduleAdminService, PreservationQuote model hooks,
ScraperTask model methods.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError


# ── CourtDocumentService ──────────────────────────────────────────────────


class TestCourtDocumentServiceQueries:
    def test_get_documents_by_task(self) -> None:
        from apps.automation.services.scraper.court_document_service import CourtDocumentService
        svc = CourtDocumentService()
        with patch("apps.automation.services.scraper.court_document_service.CourtDocument") as MockDoc:
            MockDoc.objects.filter.return_value.select_related.return_value.order_by.return_value = [MagicMock()]
            result = svc.get_documents_by_task(1)
            assert len(result) == 1

    def test_get_document_by_id_found(self) -> None:
        from apps.automation.services.scraper.court_document_service import CourtDocumentService
        svc = CourtDocumentService()
        with patch("apps.automation.services.scraper.court_document_service.CourtDocument") as MockDoc:
            MockDoc.objects.select_related.return_value.get.return_value = MagicMock()
            result = svc.get_document_by_id(1)
            assert result is not None

    def test_get_document_by_id_not_found(self) -> None:
        from apps.automation.services.scraper.court_document_service import CourtDocumentService
        svc = CourtDocumentService()
        with patch("apps.automation.services.scraper.court_document_service.CourtDocument") as MockDoc:
            MockDoc.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockDoc.objects.select_related.return_value.get.side_effect = MockDoc.DoesNotExist()
            result = svc.get_document_by_id(999)
            assert result is None


class TestCourtDocumentServiceAdapter:
    def test_lazy_service_init(self) -> None:
        from apps.automation.services.scraper.court_document_service import CourtDocumentServiceAdapter
        adapter = CourtDocumentServiceAdapter()
        assert adapter.service is not None

    def test_get_documents_by_task_internal(self) -> None:
        from apps.automation.services.scraper.court_document_service import CourtDocumentServiceAdapter
        mock_service = MagicMock()
        mock_service.get_documents_by_task.return_value = [MagicMock()]
        adapter = CourtDocumentServiceAdapter(service=mock_service)
        result = adapter.get_documents_by_task_internal(1)
        assert len(result) == 1

    def test_get_document_by_id_internal(self) -> None:
        from apps.automation.services.scraper.court_document_service import CourtDocumentServiceAdapter
        mock_service = MagicMock()
        mock_service.get_document_by_id.return_value = None
        adapter = CourtDocumentServiceAdapter(service=mock_service)
        result = adapter.get_document_by_id_internal(1)
        assert result is None


# ── DocumentDeliveryScheduleAdminService ──────────────────────────────────


class TestDocumentDeliveryScheduleAdminService:
    def test_schedule_service_not_injected(self) -> None:
        from apps.automation.services.admin.document_delivery_schedule_admin_service import (
            DocumentDeliveryScheduleAdminService,
        )
        svc = DocumentDeliveryScheduleAdminService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.schedule_service

    def test_schedule_service_injected(self) -> None:
        from apps.automation.services.admin.document_delivery_schedule_admin_service import (
            DocumentDeliveryScheduleAdminService,
        )
        mock_schedule = MagicMock()
        svc = DocumentDeliveryScheduleAdminService(schedule_service=mock_schedule)
        assert svc.schedule_service is mock_schedule

    def test_get_schedule_by_id_found(self) -> None:
        from apps.automation.services.admin.document_delivery_schedule_admin_service import (
            DocumentDeliveryScheduleAdminService,
        )
        svc = DocumentDeliveryScheduleAdminService(schedule_service=MagicMock())
        with patch("apps.automation.services.admin.document_delivery_schedule_admin_service.DocumentDeliverySchedule") as MockSchedule:
            MockSchedule.objects.get.return_value = MagicMock()
            result = svc.get_schedule_by_id(1)
            assert result is not None

    def test_get_schedule_by_id_not_found(self) -> None:
        from apps.automation.services.admin.document_delivery_schedule_admin_service import (
            DocumentDeliveryScheduleAdminService,
        )
        svc = DocumentDeliveryScheduleAdminService(schedule_service=MagicMock())
        with patch("apps.automation.services.admin.document_delivery_schedule_admin_service.DocumentDeliverySchedule") as MockSchedule:
            MockSchedule.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockSchedule.objects.get.side_effect = MockSchedule.DoesNotExist
            with pytest.raises(NotFoundError, match="不存在"):
                svc.get_schedule_by_id(999)

    def test_execute_scheduled_task(self) -> None:
        from apps.automation.services.admin.document_delivery_schedule_admin_service import (
            DocumentDeliveryScheduleAdminService,
        )
        mock_service = MagicMock()
        mock_service.execute_scheduled_task.return_value = MagicMock()
        svc = DocumentDeliveryScheduleAdminService(schedule_service=mock_service)
        result = svc.execute_scheduled_task(1)
        mock_service.execute_scheduled_task.assert_called_once_with(1)

    def test_update_schedule(self) -> None:
        from apps.automation.services.admin.document_delivery_schedule_admin_service import (
            DocumentDeliveryScheduleAdminService,
        )
        mock_service = MagicMock()
        mock_service.update_schedule.return_value = MagicMock()
        svc = DocumentDeliveryScheduleAdminService(schedule_service=mock_service)
        result = svc.update_schedule(1, runs_per_day=3, is_active=True)
        mock_service.update_schedule.assert_called_once_with(
            1, runs_per_day=3, hour_interval=None, cutoff_hours=None, is_active=True
        )


# ── PreservationQuote model hooks ────────────────────────────────────────


class TestPreservationQuoteModel:
    def test_get_success_rate_zero_total(self) -> None:
        from apps.automation.models.preservation import PreservationQuote
        quote = PreservationQuote()
        quote.total_companies = 0
        quote.success_count = 0
        assert quote.get_success_rate() == 0.0

    def test_get_success_rate_with_data(self) -> None:
        from apps.automation.models.preservation import PreservationQuote
        quote = PreservationQuote()
        quote.total_companies = 10
        quote.success_count = 8
        assert quote.get_success_rate() == 80.0


# ── ScraperTask model ────────────────────────────────────────────────────


class TestScraperTaskModel:
    def test_should_execute_now_no_schedule(self) -> None:
        from apps.automation.models.scraper import ScraperTask
        task = ScraperTask()
        task.scheduled_at = None
        assert task.should_execute_now() is True

    def test_should_execute_now_past(self) -> None:
        from apps.automation.models.scraper import ScraperTask
        from django.utils import timezone
        from datetime import timedelta
        task = ScraperTask()
        task.scheduled_at = timezone.now() - timedelta(hours=1)
        assert task.should_execute_now() is True

    def test_should_execute_now_future(self) -> None:
        from apps.automation.models.scraper import ScraperTask
        from django.utils import timezone
        from datetime import timedelta
        task = ScraperTask()
        task.scheduled_at = timezone.now() + timedelta(hours=1)
        assert task.should_execute_now() is False
