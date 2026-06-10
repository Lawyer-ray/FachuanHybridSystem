"""Tests for apps.express_query.tasks module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.express_query.tasks import execute_express_query_task, execute_manual_express_query_task


class TestExecuteExpressQueryTask:
    def test_task_not_found(self) -> None:
        with patch("apps.express_query.tasks.ExpressQueryTask") as mock_model:
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.get.side_effect = mock_model.DoesNotExist()
            # Should return silently
            execute_express_query_task(999)

    def test_ocr_no_tracking_number(self) -> None:
        mock_task = MagicMock()
        mock_task.waybill_image.path = "/tmp/test.png"
        mock_task.waybill_image.name = "test.png"

        mock_extraction = SimpleNamespace(
            ocr_text="some text",
            carrier_type=None,
            tracking_number=None,
        )

        with (
            patch("apps.express_query.tasks.ExpressQueryTask") as mock_model,
            patch("apps.express_query.tasks.TrackingExtractionService") as mock_extract_svc,
        ):
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.get.return_value = mock_task
            mock_extract_svc.return_value.extract.return_value = mock_extraction

            execute_express_query_task(1)

        # Task should be marked as failed
        assert mock_task.status == "failed"
        assert "OCR 未识别" in mock_task.error_message

    def test_ocr_unsupported_carrier(self) -> None:
        mock_task = MagicMock()
        mock_task.waybill_image.path = "/tmp/test.png"
        mock_task.waybill_image.name = "test.png"

        mock_extraction = SimpleNamespace(
            ocr_text="some text",
            carrier_type="unknown_carrier",
            tracking_number="1234567890",
        )

        with (
            patch("apps.express_query.tasks.ExpressQueryTask") as mock_model,
            patch("apps.express_query.tasks.TrackingExtractionService") as mock_extract_svc,
        ):
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.get.return_value = mock_task
            mock_extract_svc.return_value.extract.return_value = mock_extraction

            execute_express_query_task(1)

        assert mock_task.status == "failed"
        assert "承运商" in mock_task.error_message


class TestExecuteManualExpressQueryTask:
    def test_task_not_found(self) -> None:
        with patch("apps.express_query.tasks.ExpressQueryTask") as mock_model:
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.get.side_effect = mock_model.DoesNotExist()
            execute_manual_express_query_task(999)

    def test_missing_tracking_number(self) -> None:
        mock_task = MagicMock()
        mock_task.tracking_number = ""
        mock_task.carrier_type = "sf"

        with patch("apps.express_query.tasks.ExpressQueryTask") as mock_model:
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.get.return_value = mock_task

            execute_manual_express_query_task(1)

        assert mock_task.status == "failed"
        assert "缺少运单号" in mock_task.error_message

    def test_unsupported_carrier(self) -> None:
        mock_task = MagicMock()
        mock_task.tracking_number = "123456"
        mock_task.carrier_type = "unknown"

        with patch("apps.express_query.tasks.ExpressQueryTask") as mock_model:
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.get.return_value = mock_task

            execute_manual_express_query_task(1)

        assert mock_task.status == "failed"
        assert "不支持" in mock_task.error_message
