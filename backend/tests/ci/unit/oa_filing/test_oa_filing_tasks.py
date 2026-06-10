"""Tests for apps.oa_filing.tasks module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.core.tasking import TaskTimeoutError


class TestRunClientImportTask:
    def test_session_not_found(self) -> None:
        from apps.oa_filing.tasks import run_client_import_task

        with patch("apps.oa_filing.models.ClientImportSession") as mock_model:
            mock_qs = MagicMock()
            mock_qs.get.side_effect = mock_model.DoesNotExist("not found")
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_qs.get.side_effect = mock_model.DoesNotExist("not found")
            mock_model.objects.select_related.return_value = mock_qs
            run_client_import_task(999)

    def test_skips_completed_session(self) -> None:
        from apps.oa_filing.tasks import run_client_import_task

        mock_session = MagicMock()
        mock_session.status = "completed"

        with (
            patch("apps.oa_filing.models.ClientImportSession") as mock_model,
            patch("apps.oa_filing.models.ClientImportStatus") as mock_status,
        ):
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.return_value = mock_session
            mock_status.COMPLETED = "completed"
            mock_status.CANCELLED = "cancelled"

            with patch("apps.oa_filing.services.client_import_service.ClientImportService") as mock_svc:
                run_client_import_task(1)
                mock_svc.assert_not_called()

    def test_sets_started_at_when_none(self) -> None:
        from apps.oa_filing.tasks import run_client_import_task

        mock_session = MagicMock()
        mock_session.status = "pending"
        mock_session.started_at = None

        with (
            patch("apps.oa_filing.models.ClientImportSession") as mock_model,
            patch("apps.oa_filing.models.ClientImportStatus") as mock_status,
            patch("apps.oa_filing.models.ClientImportPhase") as mock_phase,
            patch("apps.oa_filing.services.client_import_service.ClientImportService") as mock_svc,
        ):
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.return_value = mock_session
            mock_status.COMPLETED = "completed"
            mock_status.CANCELLED = "cancelled"
            mock_status.IN_PROGRESS = "in_progress"
            mock_phase.DISCOVERING = "discovering"
            mock_instance = MagicMock()
            mock_svc.return_value = mock_instance

            run_client_import_task(1)
            assert mock_session.started_at is not None
            mock_instance.run_import.assert_called_once()

    def test_handles_generic_exception(self) -> None:
        from apps.oa_filing.tasks import run_client_import_task

        mock_session = MagicMock()
        mock_session.status = "pending"
        mock_session.started_at = timezone.now()

        with (
            patch("apps.oa_filing.models.ClientImportSession") as mock_model,
            patch("apps.oa_filing.models.ClientImportStatus") as mock_status,
            patch("apps.oa_filing.models.ClientImportPhase") as mock_phase,
            patch("apps.oa_filing.services.client_import_service.ClientImportService") as mock_svc,
        ):
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.return_value = mock_session
            mock_status.COMPLETED = "completed"
            mock_status.CANCELLED = "cancelled"
            mock_status.FAILED = "failed"
            mock_phase.FAILED = "failed"
            mock_instance = MagicMock()
            mock_instance.run_import.side_effect = RuntimeError("unexpected error")
            mock_svc.return_value = mock_instance

            run_client_import_task(1)
        assert mock_session.status == "failed"

    def test_handles_timeout_error(self) -> None:
        from apps.oa_filing.tasks import run_client_import_task

        mock_session = MagicMock()
        mock_session.status = "pending"
        mock_session.started_at = timezone.now()

        with (
            patch("apps.oa_filing.models.ClientImportSession") as mock_model,
            patch("apps.oa_filing.models.ClientImportStatus") as mock_status,
            patch("apps.oa_filing.models.ClientImportPhase") as mock_phase,
            patch("apps.oa_filing.services.client_import_service.ClientImportService") as mock_svc,
        ):
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.return_value = mock_session
            mock_status.COMPLETED = "completed"
            mock_status.CANCELLED = "cancelled"
            mock_status.FAILED = "failed"
            mock_phase.FAILED = "failed"
            mock_instance = MagicMock()
            mock_instance.run_import.side_effect = TaskTimeoutError("timeout")
            mock_svc.return_value = mock_instance

            with pytest.raises(TaskTimeoutError):
                run_client_import_task(1)
        assert mock_session.status == "failed"


class TestRunCaseImportPreviewTask:
    def test_session_not_found(self) -> None:
        from apps.oa_filing.tasks import run_case_import_preview_task

        with patch("apps.oa_filing.models.CaseImportSession") as mock_model:
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.side_effect = mock_model.DoesNotExist()
            run_case_import_preview_task(999, "/tmp/test.xlsx")

    def test_skips_completed_session(self) -> None:
        from apps.oa_filing.tasks import run_case_import_preview_task

        mock_session = MagicMock()
        mock_session.status = "completed"

        with (
            patch("apps.oa_filing.models.CaseImportSession") as mock_model,
            patch("apps.oa_filing.models.CaseImportStatus") as mock_status,
        ):
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.return_value = mock_session
            mock_status.COMPLETED = "completed"
            mock_status.CANCELLED = "cancelled"

            with patch("apps.oa_filing.services.case_import_service.CaseImportService") as mock_svc:
                run_case_import_preview_task(1, "/tmp/test.xlsx")
                mock_svc.assert_not_called()


class TestRunCaseImportTask:
    def test_session_not_found(self) -> None:
        from apps.oa_filing.tasks import run_case_import_task

        with patch("apps.oa_filing.models.CaseImportSession") as mock_model:
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.side_effect = mock_model.DoesNotExist()
            run_case_import_task(999, ["case-001"])

    def test_skips_completed_session(self) -> None:
        from apps.oa_filing.tasks import run_case_import_task

        mock_session = MagicMock()
        mock_session.status = "completed"

        with (
            patch("apps.oa_filing.models.CaseImportSession") as mock_model,
            patch("apps.oa_filing.models.CaseImportStatus") as mock_status,
        ):
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.return_value = mock_session
            mock_status.COMPLETED = "completed"
            mock_status.CANCELLED = "cancelled"

            with patch("apps.oa_filing.services.case_import_service.CaseImportService") as mock_svc:
                run_case_import_task(1, ["case-001"])
                mock_svc.assert_not_called()

    def test_sets_started_at_when_none(self) -> None:
        from apps.oa_filing.tasks import run_case_import_task

        mock_session = MagicMock()
        mock_session.status = "pending"
        mock_session.started_at = None

        with (
            patch("apps.oa_filing.models.CaseImportSession") as mock_model,
            patch("apps.oa_filing.models.CaseImportStatus") as mock_status,
            patch("apps.oa_filing.models.CaseImportPhase") as mock_phase,
            patch("apps.oa_filing.services.case_import_service.CaseImportService") as mock_svc,
        ):
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.return_value = mock_session
            mock_status.COMPLETED = "completed"
            mock_status.CANCELLED = "cancelled"
            mock_status.IN_PROGRESS = "in_progress"
            mock_phase.DISCOVERING = "discovering"
            mock_instance = MagicMock()
            mock_instance.run_import.return_value = []
            mock_svc.return_value = mock_instance

            run_case_import_task(1, ["case-001"])
            assert mock_session.started_at is not None
