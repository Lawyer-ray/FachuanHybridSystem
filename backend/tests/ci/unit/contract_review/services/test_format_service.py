"""Tests for contract_review.services.format_service（format_api 下沉的任务级业务）."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError


def _make_task(
    task_id: uuid.UUID | None = None, *, user_id: int = 1, original_file: str = "uploads/a.docx"
) -> MagicMock:
    task = MagicMock()
    task.id = task_id or uuid.uuid4()
    task.user_id = user_id
    task.original_file = original_file
    task.output_file = None
    return task


class TestGetTaskForUser:
    def test_owner_gets_task(self):
        from apps.contract_review.services.format_service import FormatTaskService

        task = _make_task()
        user = MagicMock()
        user.is_superuser = False
        user.id = 1

        with patch("apps.contract_review.services.format_service.ReviewTask") as mock_model:
            mock_model.objects.get.return_value = task
            result = FormatTaskService().get_task_for_user(task.id, user, denied_message="无权操作此任务")

        assert result is task

    def test_task_not_found_raises_not_found(self):
        from apps.contract_review.services.format_service import FormatTaskService

        with patch("apps.contract_review.services.format_service.ReviewTask") as mock_model:
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.get.side_effect = mock_model.DoesNotExist

            with pytest.raises(NotFoundError, match="任务不存在"):
                FormatTaskService().get_task_for_user(uuid.uuid4(), MagicMock(), denied_message="无权操作此任务")

    def test_denied_user_raises_not_found(self):
        from apps.contract_review.services.format_service import FormatTaskService

        task = _make_task(user_id=1)
        user = MagicMock()
        user.is_superuser = False
        user.id = 2

        with patch("apps.contract_review.services.format_service.ReviewTask") as mock_model:
            mock_model.objects.get.return_value = task

            # 无权也走 404 语义（NotFound），不泄露任务存在性
            with pytest.raises(NotFoundError, match="无权操作此任务"):
                FormatTaskService().get_task_for_user(task.id, user, denied_message="无权操作此任务")


class TestNormalizeDocument:
    @pytest.fixture
    def superuser(self) -> MagicMock:
        user = MagicMock()
        user.is_superuser = True
        return user

    def test_success(self, superuser):
        from apps.contract_review.services.format_service import FormatTaskService

        task = _make_task()
        saved = "contract_review/output/规范化.docx"

        with (
            patch("apps.contract_review.services.format_service.ReviewTask") as mock_model,
            patch("apps.contract_review.services.format_service.to_media_abs") as mock_to_abs,
            patch("apps.contract_review.services.format_service.normalize_to_media", return_value=saved) as mock_norm,
        ):
            mock_model.objects.get.return_value = task
            mock_to_abs.return_value = MagicMock(exists=MagicMock(return_value=True))

            result = FormatTaskService().normalize_document(task_id=task.id, user=superuser, reference_file=None)

        assert result["status"] == "success"
        assert result["output_file"] == saved
        assert result["task_id"] == task.id
        mock_norm.assert_called_once()
        task.save.assert_called_once_with(update_fields=["output_file"])
        assert task.output_file == saved

    def test_no_original_file_returns_failed(self, superuser):
        from apps.contract_review.services.format_service import FormatTaskService

        task = _make_task(original_file="")

        with patch("apps.contract_review.services.format_service.ReviewTask") as mock_model:
            mock_model.objects.get.return_value = task

            result = FormatTaskService().normalize_document(task_id=task.id, user=superuser, reference_file=None)

        assert result["status"] == "failed"
        assert "原始文件不存在" in result["message"]
        task.save.assert_not_called()

    def test_normalize_exception_returns_failed(self, superuser):
        from apps.contract_review.services.format_service import FormatTaskService

        task = _make_task()

        with (
            patch("apps.contract_review.services.format_service.ReviewTask") as mock_model,
            patch("apps.contract_review.services.format_service.to_media_abs") as mock_to_abs,
            patch(
                "apps.contract_review.services.format_service.normalize_to_media",
                side_effect=RuntimeError("boom"),
            ),
        ):
            mock_model.objects.get.return_value = task
            mock_to_abs.return_value = MagicMock(exists=MagicMock(return_value=True))

            result = FormatTaskService().normalize_document(task_id=task.id, user=superuser, reference_file=None)

        assert result["status"] == "failed"
        assert "boom" in result["message"]
        task.save.assert_not_called()


class TestResolveOutputFile:
    def test_success(self, tmp_path):
        from apps.contract_review.services.format_service import FormatTaskService

        output = tmp_path / "规范化.docx"
        output.write_bytes(b"docx")
        task = _make_task()
        task.output_file = "contract_review/output/规范化.docx"
        user = MagicMock()
        user.is_superuser = True

        with (
            patch("apps.contract_review.services.format_service.ReviewTask") as mock_model,
            patch("apps.contract_review.services.format_service.to_media_abs", return_value=output),
        ):
            mock_model.objects.get.return_value = task
            result = FormatTaskService().resolve_output_file(task_id=task.id, user=user)

        assert result == output

    def test_no_output_file_raises_not_found(self):
        from apps.contract_review.services.format_service import FormatTaskService

        task = _make_task()
        task.output_file = None
        user = MagicMock()
        user.is_superuser = True

        with patch("apps.contract_review.services.format_service.ReviewTask") as mock_model:
            mock_model.objects.get.return_value = task

            with pytest.raises(NotFoundError, match="输出文件不存在"):
                FormatTaskService().resolve_output_file(task_id=task.id, user=user)
