"""Coverage tests for _logging_document_mixin."""

from __future__ import annotations

from unittest.mock import patch

from apps.automation.utils._logging_document_mixin import DocumentLoggingMixin


class TestDocumentLoggingMixin:
    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_creation_success(self, mock_logger):
        DocumentLoggingMixin.log_document_creation_success(document_id=10, scraper_task_id=1, case_id=5)
        mock_logger.info.assert_called_once()
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["document_id"] == 10
        assert extra["success"] is True
        assert extra["case_id"] == 5

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_creation_success_no_case(self, mock_logger):
        DocumentLoggingMixin.log_document_creation_success(document_id=10, scraper_task_id=1)
        extra = mock_logger.info.call_args[1]["extra"]
        assert "case_id" not in extra

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_status_update(self, mock_logger):
        DocumentLoggingMixin.log_document_status_update(document_id=1, old_status="pending", new_status="done")
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["old_status"] == "pending"
        assert extra["new_status"] == "done"
