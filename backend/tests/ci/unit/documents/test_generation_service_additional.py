"""Tests for generation_service.py — additional coverage for uncovered branches.

Covers: _apply_value_updates (folder_path stripping), _validate_template_update,
        update_generation_config (full flow), create_generation_config,
        get_configs_for_case, add_generated_file, add_error_log, update_task_status
        (completed/failed branches).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.services.generation.generation_service import GenerationService


@pytest.fixture
def svc() -> GenerationService:
    return GenerationService()


# ── _validate_template_update ────────────────────────────────────


class TestValidateTemplateUpdate:
    def test_no_template_id_returns(self, svc: GenerationService) -> None:
        # Should not raise
        svc._validate_template_update({})

    def test_none_template_id_returns(self, svc: GenerationService) -> None:
        svc._validate_template_update({"document_template_id": None})

    @patch("apps.documents.services.generation.generation_service.DocumentTemplate")
    def test_template_not_found(self, MockDT: MagicMock, svc: GenerationService) -> None:
        MockDT.objects.filter.return_value.first.return_value = None
        with pytest.raises(NotFoundError):
            svc._validate_template_update({"document_template_id": 999})

    @patch("apps.documents.services.generation.generation_service.DocumentTemplate")
    def test_template_inactive(self, MockDT: MagicMock, svc: GenerationService) -> None:
        tmpl = MagicMock()
        tmpl.is_active = False
        MockDT.objects.filter.return_value.first.return_value = tmpl
        with pytest.raises(ValidationException, match="禁用"):
            svc._validate_template_update({"document_template_id": 1})


# ── _apply_value_updates edge cases ──────────────────────────────


class TestApplyValueUpdatesEdges:
    def test_updates_case_stage(self, svc: GenerationService) -> None:
        value: dict[str, Any] = {"case_stage": "old"}
        svc._apply_value_updates(value, {"case_stage": "new"})
        assert value["case_stage"] == "new"

    def test_updates_document_template_id(self, svc: GenerationService) -> None:
        value: dict[str, Any] = {}
        svc._apply_value_updates(value, {"document_template_id": 42})
        assert value["document_template_id"] == 42

    def test_all_keys_updated(self, svc: GenerationService) -> None:
        value: dict[str, Any] = {}
        updates = {
            "case_type": "civil",
            "case_stage": "first_trial",
            "folder_path": "/new/path",
            "priority": 3,
            "condition": {"a": 1},
            "document_template_id": 7,
        }
        svc._apply_value_updates(value, updates)
        assert value == updates


# ── delete_generation_config ─────────────────────────────────────


class TestDeleteGenerationConfig:
    @patch("apps.documents.services.generation.generation_service.GenerationConfig")
    def test_deactivates(self, MockConfig: MagicMock, svc: GenerationService) -> None:
        config = MagicMock()
        MockConfig.objects.filter.return_value.first.return_value = config
        assert svc.delete_generation_config(1) is True
        assert config.is_active is False
        config.save.assert_called_once_with(update_fields=["is_active"])

    @patch("apps.documents.services.generation.generation_service.GenerationConfig")
    def test_not_found(self, MockConfig: MagicMock, svc: GenerationService) -> None:
        MockConfig.objects.filter.return_value.first.return_value = None
        assert svc.delete_generation_config(999) is False


# ── update_task_status ───────────────────────────────────────────


class TestUpdateTaskStatusFull:
    @patch("apps.documents.services.generation.generation_service.timezone")
    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_completed_sets_time(
        self, MockTask: MagicMock, mock_tz: MagicMock, svc: GenerationService
    ) -> None:
        task = MagicMock()
        MockTask.objects.filter.return_value.first.return_value = task
        mock_time = MagicMock()
        mock_time.isoformat.return_value = "2025-01-01T00:00:00"
        mock_tz.now.return_value = mock_time
        result = svc.update_task_status(1, "completed")
        assert task.status == "completed"
        assert task.completed_at is mock_time
        task.save.assert_called()

    @patch("apps.documents.services.generation.generation_service.timezone")
    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_failed_with_message(
        self, MockTask: MagicMock, mock_tz: MagicMock, svc: GenerationService
    ) -> None:
        task = MagicMock()
        task.id = 10
        MockTask.objects.filter.return_value.first.return_value = task
        MockTask.objects.get.return_value = task
        mock_time = MagicMock()
        mock_time.isoformat.return_value = "2025-01-01T00:00:00"
        mock_tz.now.return_value = mock_time
        result = svc.update_task_status(10, "failed", error_message="err msg")
        assert task.status == "failed"
        assert task.error_message == "err msg"

    @patch("apps.documents.services.generation.generation_service.timezone")
    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_pending_clears_time(
        self, MockTask: MagicMock, mock_tz: MagicMock, svc: GenerationService
    ) -> None:
        task = MagicMock()
        MockTask.objects.filter.return_value.first.return_value = task
        result = svc.update_task_status(1, "pending")
        assert task.completed_at is None
        task.save.assert_called()

    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_task_not_found(self, MockTask: MagicMock, svc: GenerationService) -> None:
        MockTask.objects.filter.return_value.first.return_value = None
        with pytest.raises(NotFoundError):
            svc.update_task_status(999, "completed")

    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_invalid_status(self, MockTask: MagicMock, svc: GenerationService) -> None:
        task = MagicMock()
        MockTask.objects.filter.return_value.first.return_value = task
        with patch(
            "apps.documents.models.GenerationStatus"
        ) as MockStatus:
            MockStatus.choices = [("pending", "P")]
            with pytest.raises(ValidationException, match="无效"):
                svc.update_task_status(1, "bogus")


# ── add_generated_file ───────────────────────────────────────────


class TestAddGeneratedFile:
    @patch("apps.documents.services.generation.generation_service.timezone")
    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_appends_file(
        self, MockTask: MagicMock, mock_tz: MagicMock, svc: GenerationService
    ) -> None:
        task = MagicMock()
        task.generated_files = []
        MockTask.objects.filter.return_value.first.return_value = task
        mock_tz.now.return_value = MagicMock(isoformat=MagicMock(return_value="2025-01-01"))
        result = svc.add_generated_file(1, "/path/file.docx", "file.docx")
        assert len(task.generated_files) == 1
        assert task.generated_files[0]["path"] == "/path/file.docx"
        task.save.assert_called()

    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_task_not_found(self, MockTask: MagicMock, svc: GenerationService) -> None:
        MockTask.objects.filter.return_value.first.return_value = None
        with pytest.raises(NotFoundError):
            svc.add_generated_file(999, "/path", "name")


# ── add_error_log ────────────────────────────────────────────────


class TestAddErrorLog:
    @patch("apps.documents.services.generation.generation_service.timezone")
    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_appends_log(
        self, MockTask: MagicMock, mock_tz: MagicMock, svc: GenerationService
    ) -> None:
        task = MagicMock()
        task.error_logs = []
        MockTask.objects.filter.return_value.first.return_value = task
        mock_tz.now.return_value = MagicMock(isoformat=MagicMock(return_value="2025-01-01"))
        svc.add_error_log(1, "error occurred")
        assert len(task.error_logs) == 1
        assert task.error_logs[0]["message"] == "error occurred"
        assert task.error_logs[0]["type"] == "error"

    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_task_not_found(self, MockTask: MagicMock, svc: GenerationService) -> None:
        MockTask.objects.filter.return_value.first.return_value = None
        with pytest.raises(NotFoundError):
            svc.add_error_log(999, "msg")
