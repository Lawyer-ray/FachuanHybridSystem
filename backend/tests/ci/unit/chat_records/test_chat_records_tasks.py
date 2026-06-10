"""Tests for apps.chat_records.tasks module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestExportChatRecordTask:
    def test_task_not_found(self) -> None:
        from apps.chat_records.tasks import export_chat_record_task

        with patch("apps.chat_records.models.ChatRecordExportTask") as mock_model:
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.side_effect = mock_model.DoesNotExist()
            result = export_chat_record_task("nonexistent-id")
        assert result["status"] == "failed"
        assert "不存在" in result["error"]


class TestExtractRecordingFramesTask:
    def test_recording_not_found(self) -> None:
        from apps.chat_records.tasks import extract_recording_frames_task

        with patch("apps.chat_records.models.ChatRecordRecording") as mock_model:
            mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_model.objects.select_related.return_value.get.side_effect = mock_model.DoesNotExist()
            result = extract_recording_frames_task("nonexistent-id")
        assert result["status"] == "failed"
        assert "不存在" in result["error"]
