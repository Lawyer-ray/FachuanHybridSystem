"""Coverage tests for _logging_document_mixin."""

from __future__ import annotations

from unittest.mock import patch

from apps.automation.utils._logging_document_mixin import DocumentLoggingMixin


class TestDocumentLoggingMixin:
    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_creation_start(self, mock_logger):
        DocumentLoggingMixin.log_document_creation_start(scraper_task_id=1, case_id=42, extra_field="val")
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "开始创建文档记录"
        extra = call_args[1]["extra"]
        assert extra["scraper_task_id"] == 1
        assert extra["case_id"] == 42
        assert extra["extra_field"] == "val"

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_creation_start_no_case(self, mock_logger):
        DocumentLoggingMixin.log_document_creation_start(scraper_task_id=2)
        extra = mock_logger.info.call_args[1]["extra"]
        assert "case_id" not in extra

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

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_processing_start_with_size(self, mock_logger):
        DocumentLoggingMixin.log_document_processing_start(file_type="PDF", file_size=1024)
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["file_type"] == "PDF"
        assert extra["file_size"] == 1024

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_processing_start_no_size(self, mock_logger):
        DocumentLoggingMixin.log_document_processing_start(file_type="DOCX")
        extra = mock_logger.info.call_args[1]["extra"]
        assert "file_size" not in extra

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_processing_success(self, mock_logger):
        DocumentLoggingMixin.log_document_processing_success(
            file_type="PDF", processing_time=1.5, content_length=100, file_size=200,
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["success"] is True
        assert extra["processing_time"] == 1.5
        assert extra["file_size"] == 200

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_processing_success_no_size(self, mock_logger):
        DocumentLoggingMixin.log_document_processing_success(
            file_type="PDF", processing_time=1.5, content_length=100,
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert "file_size" not in extra

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_processing_failed(self, mock_logger):
        DocumentLoggingMixin.log_document_processing_failed(
            file_type="PDF", error_message="timeout", processing_time=5.0, file_size=1024,
        )
        mock_logger.error.assert_called_once()
        extra = mock_logger.error.call_args[1]["extra"]
        assert extra["success"] is False
        assert extra["error_message"] == "timeout"

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_document_processing_failed_no_size(self, mock_logger):
        DocumentLoggingMixin.log_document_processing_failed(
            file_type="PDF", error_message="err", processing_time=1.0,
        )
        extra = mock_logger.error.call_args[1]["extra"]
        assert "file_size" not in extra

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_ai_filename_generation_start(self, mock_logger):
        DocumentLoggingMixin.log_ai_filename_generation_start(content_length=500)
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["content_length"] == 500

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_ai_filename_generation_success(self, mock_logger):
        DocumentLoggingMixin.log_ai_filename_generation_success(
            generated_filename="doc.pdf", processing_time=0.5, content_length=100,
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["generated_filename"] == "doc.pdf"
        assert extra["success"] is True

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_ai_filename_generation_failed(self, mock_logger):
        DocumentLoggingMixin.log_ai_filename_generation_failed(
            error_message="api error", processing_time=1.0, content_length=100,
        )
        mock_logger.error.assert_called_once()
        extra = mock_logger.error.call_args[1]["extra"]
        assert extra["error_message"] == "api error"

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_audio_transcription_start_with_size(self, mock_logger):
        DocumentLoggingMixin.log_audio_transcription_start(file_format="mp3", file_size=5000)
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["file_format"] == "mp3"
        assert extra["file_size"] == 5000

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_audio_transcription_start_no_size(self, mock_logger):
        DocumentLoggingMixin.log_audio_transcription_start(file_format="wav")
        extra = mock_logger.info.call_args[1]["extra"]
        assert "file_size" not in extra

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_audio_transcription_success(self, mock_logger):
        DocumentLoggingMixin.log_audio_transcription_success(
            transcription_length=100, processing_time=2.0, file_format="mp3", file_size=3000,
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["success"] is True
        assert extra["transcription_length"] == 100

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_audio_transcription_success_no_size(self, mock_logger):
        DocumentLoggingMixin.log_audio_transcription_success(
            transcription_length=50, processing_time=1.0, file_format="wav",
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert "file_size" not in extra

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_audio_transcription_failed(self, mock_logger):
        DocumentLoggingMixin.log_audio_transcription_failed(
            error_message="format error", processing_time=0.5, file_format="mp3", file_size=1000,
        )
        mock_logger.error.assert_called_once()
        extra = mock_logger.error.call_args[1]["extra"]
        assert extra["error_message"] == "format error"

    @patch("apps.automation.utils._logging_document_mixin.logger")
    def test_log_audio_transcription_failed_no_size(self, mock_logger):
        DocumentLoggingMixin.log_audio_transcription_failed(
            error_message="err", processing_time=0.1, file_format="wav",
        )
        extra = mock_logger.error.call_args[1]["extra"]
        assert "file_size" not in extra
