"""Targeted tests for express_query module to push coverage to 80%+."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExpressQueryModels:
    def test_express_query_tool_meta(self):
        from apps.express_query.models import ExpressQueryTool

        assert ExpressQueryTool._meta.managed is False
        assert ExpressQueryTool._meta.verbose_name == "查询EMS/顺丰"

    def test_carrier_type_choices(self):
        from apps.express_query.models import ExpressCarrierType

        assert ExpressCarrierType.UNKNOWN == "unknown"
        assert ExpressCarrierType.EMS == "ems"
        assert ExpressCarrierType.SF == "sf"
        assert len(ExpressCarrierType.choices) == 3

    def test_task_status_choices(self):
        from apps.express_query.models import ExpressQueryTaskStatus

        assert ExpressQueryTaskStatus.PENDING == "pending"
        assert ExpressQueryTaskStatus.OCR_PARSING == "ocr_parsing"
        assert ExpressQueryTaskStatus.WAITING_LOGIN == "waiting_login"
        assert ExpressQueryTaskStatus.QUERYING == "querying"
        assert ExpressQueryTaskStatus.SUCCESS == "success"
        assert ExpressQueryTaskStatus.FAILED == "failed"
        assert len(ExpressQueryTaskStatus.choices) == 6

    def test_task_str_with_tracking_number(self):
        from apps.express_query.models import ExpressQueryTask, ExpressQueryTaskStatus

        task = ExpressQueryTask(
            status=ExpressQueryTaskStatus.SUCCESS,
            tracking_number="SF1234567890123",
        )
        assert str(task) == "success - SF1234567890123"

    def test_task_str_with_title(self):
        from apps.express_query.models import ExpressQueryTask, ExpressQueryTaskStatus

        task = ExpressQueryTask(
            status=ExpressQueryTaskStatus.PENDING,
            title="Test Title",
        )
        assert str(task) == "pending - Test Title"

    def test_task_str_fallback_to_id(self):
        from apps.express_query.models import ExpressQueryTask, ExpressQueryTaskStatus

        task = ExpressQueryTask(
            id=42,
            status=ExpressQueryTaskStatus.FAILED,
        )
        assert str(task) == "failed - 42"


# ---------------------------------------------------------------------------
# tracking_extraction_service
# ---------------------------------------------------------------------------


class TestTrackingExtractionService:
    def test_pick_sf_tracking_number(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        svc = TrackingExtractionService.__new__(TrackingExtractionService)
        svc._sf_pattern = re.compile(r"(?<![A-Z0-9])SF\d{10,20}(?![A-Z0-9])", re.IGNORECASE)
        svc._ems_pattern = re.compile(r"(?<!\d)\d{13}(?!\d)")
        result = svc._pick_tracking_number("快递单号 SF1234567890123 请查收")
        assert result is not None
        assert result["carrier"] == "sf"
        assert "SF1234567890123" in result["tracking_number"]

    def test_pick_ems_tracking_number(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        svc = TrackingExtractionService.__new__(TrackingExtractionService)
        svc._sf_pattern = re.compile(r"(?<![A-Z0-9])SF\d{10,20}(?![A-Z0-9])", re.IGNORECASE)
        svc._ems_pattern = re.compile(r"(?<!\d)\d{13}(?!\d)")
        result = svc._pick_tracking_number("EMS运单 1234567890123")
        assert result is not None
        assert result["carrier"] == "ems"
        assert result["tracking_number"] == "1234567890123"

    def test_pick_no_tracking_number(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        svc = TrackingExtractionService.__new__(TrackingExtractionService)
        svc._sf_pattern = re.compile(r"(?<![A-Z0-9])SF\d{10,20}(?![A-Z0-9])", re.IGNORECASE)
        svc._ems_pattern = re.compile(r"(?<!\d)\d{13}(?!\d)")
        result = svc._pick_tracking_number("没有任何运单号的文本")
        assert result is None

    def test_pick_empty_text(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        svc = TrackingExtractionService.__new__(TrackingExtractionService)
        svc._sf_pattern = re.compile(r"(?<![A-Z0-9])SF\d{10,20}(?![A-Z0-9])", re.IGNORECASE)
        svc._ems_pattern = re.compile(r"(?<!\d)\d{13}(?!\d)")
        result = svc._pick_tracking_number("")
        assert result is None

    def test_pick_sf_over_ems_priority(self):
        """SF numbers that overlap with EMS digits should be excluded from EMS matches."""
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        svc = TrackingExtractionService.__new__(TrackingExtractionService)
        svc._sf_pattern = re.compile(r"(?<![A-Z0-9])SF\d{10,20}(?![A-Z0-9])", re.IGNORECASE)
        svc._ems_pattern = re.compile(r"(?<!\d)\d{13}(?!\d)")
        # The 13-digit tail of SF overlaps EMS pattern
        result = svc._pick_tracking_number("SF1234567890123456")
        assert result is not None
        assert result["carrier"] == "sf"

    def test_tracking_result_dataclass(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionResult

        r = TrackingExtractionResult(carrier_type="sf", tracking_number="SF123", ocr_text="text")
        assert r.carrier_type == "sf"
        assert r.tracking_number == "SF123"
        assert r.ocr_text == "text"


# ---------------------------------------------------------------------------
# api
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExpressQueryApi:
    def test_api_schema_fields(self):
        from apps.express_query.api import ExpressQueryTaskOut

        schema = ExpressQueryTaskOut(
            id=1,
            title="Test",
            status="pending",
            carrier_type="ems",
            tracking_number="123",
            result_pdf=None,
            created_at=None,
            updated_at=None,
        )
        assert schema.id == 1
        assert schema.result_pdf is None


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExpressQueryTasks:
    @patch("apps.express_query.tasks.TrackingExtractionService")
    @patch("apps.express_query.tasks.ExpressBrowserQueryService")
    def test_execute_task_not_found(self, mock_browser_cls, mock_extract_cls):
        from apps.express_query.tasks import execute_express_query_task

        # Should not raise even if task doesn't exist
        execute_express_query_task(999999)

    @patch("apps.express_query.tasks.TrackingExtractionService")
    def test_execute_task_no_tracking(self, mock_extract_cls):
        """Test that execute_express_query_task handles missing tracking number."""
        from apps.express_query.models import ExpressQueryTask, ExpressQueryTaskStatus
        from apps.express_query.tasks import execute_express_query_task

        task = ExpressQueryTask.objects.create(
            title="Test",
            status=ExpressQueryTaskStatus.PENDING,
        )

        mock_svc = MagicMock()
        mock_svc.extract.return_value = SimpleNamespace(
            carrier_type="unknown",
            tracking_number="",
            ocr_text="no tracking",
        )
        mock_extract_cls.return_value = mock_svc

        # The task has no waybill_image set, so Path(task.waybill_image.path) will raise ValueError
        # which is caught and sets status to FAILED
        execute_express_query_task(task.id)
        task.refresh_from_db()
        assert task.status == ExpressQueryTaskStatus.FAILED

    @patch("apps.express_query.tasks.ExpressBrowserQueryService")
    def test_execute_manual_task_not_found(self, mock_browser_cls):
        from apps.express_query.tasks import execute_manual_express_query_task

        execute_manual_express_query_task(999999)

    @patch("apps.express_query.tasks.ExpressBrowserQueryService")
    def test_execute_manual_task_missing_tracking(self, mock_browser_cls):
        from apps.express_query.models import ExpressQueryTask, ExpressQueryTaskStatus
        from apps.express_query.tasks import execute_manual_express_query_task

        task = ExpressQueryTask.objects.create(
            title="Test",
            status=ExpressQueryTaskStatus.WAITING_LOGIN,
            tracking_number="",
            carrier_type="",
        )

        execute_manual_express_query_task(task.id)
        task.refresh_from_db()
        assert task.status == ExpressQueryTaskStatus.FAILED
        assert "缺少运单号或承运商信息" in task.error_message

    @patch("apps.express_query.tasks.ExpressBrowserQueryService")
    def test_execute_manual_task_unsupported_carrier(self, mock_browser_cls):
        from apps.express_query.models import ExpressQueryTask, ExpressQueryTaskStatus
        from apps.express_query.tasks import execute_manual_express_query_task

        task = ExpressQueryTask.objects.create(
            title="Test",
            status=ExpressQueryTaskStatus.WAITING_LOGIN,
            tracking_number="1234567890123",
            carrier_type="unknown",
        )

        execute_manual_express_query_task(task.id)
        task.refresh_from_db()
        assert task.status == ExpressQueryTaskStatus.FAILED
        assert "不支持的承运商" in task.error_message

    def test_execute_task_with_ocr_service_extract(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = SimpleNamespace(text="SF1234567890123")
        svc = TrackingExtractionService(ocr_service=mock_ocr)

        with patch.object(svc, "_load_waybill_bytes_for_ocr", return_value=b"fake"):
            result = svc.extract(Path("/tmp/test.png"))
            assert result.tracking_number == "SF1234567890123"
            assert result.carrier_type == "sf"

    def test_execute_task_ocr_no_tracking(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = SimpleNamespace(text="some random text")
        svc = TrackingExtractionService(ocr_service=mock_ocr)

        with patch.object(svc, "_load_waybill_bytes_for_ocr", return_value=b"fake"):
            result = svc.extract(Path("/tmp/test.png"))
            assert result.tracking_number == ""
            assert result.carrier_type == "unknown"

    def test_load_waybill_bytes_non_pdf(self, tmp_path):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        svc = TrackingExtractionService.__new__(TrackingExtractionService)
        f = tmp_path / "test.png"
        f.write_bytes(b"image_data")
        result = svc._load_waybill_bytes_for_ocr(f)
        assert result == b"image_data"
