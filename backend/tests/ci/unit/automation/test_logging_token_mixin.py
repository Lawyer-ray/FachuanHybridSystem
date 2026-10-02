"""Coverage tests for _logging_token_mixin."""

from __future__ import annotations

from unittest.mock import patch

from apps.automation.utils._logging_token_mixin import TokenLoggingMixin


class TestTokenLoggingMixin:
    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_captcha_recognition_start_with_size(self, mock_logger):
        TokenLoggingMixin.log_captcha_recognition_start(image_size=1024)
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["image_size"] == 1024
        assert extra["action"] == "captcha_recognition_start"

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_captcha_recognition_start_no_size(self, mock_logger):
        TokenLoggingMixin.log_captcha_recognition_start()
        extra = mock_logger.info.call_args[1]["extra"]
        assert "image_size" not in extra

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_captcha_recognition_success(self, mock_logger):
        TokenLoggingMixin.log_captcha_recognition_success(
            processing_time=1.5, result_length=4, image_size=2048,
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["success"] is True
        assert extra["image_size"] == 2048

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_captcha_recognition_success_no_size(self, mock_logger):
        TokenLoggingMixin.log_captcha_recognition_success(
            processing_time=0.5, result_length=4,
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert "image_size" not in extra

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_captcha_recognition_failed(self, mock_logger):
        TokenLoggingMixin.log_captcha_recognition_failed(
            processing_time=2.0, error_message="ocr error", image_size=512,
        )
        mock_logger.error.assert_called_once()
        extra = mock_logger.error.call_args[1]["extra"]
        assert extra["success"] is False
        assert extra["image_size"] == 512

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_captcha_recognition_failed_no_size(self, mock_logger):
        TokenLoggingMixin.log_captcha_recognition_failed(
            processing_time=1.0, error_message="err",
        )
        extra = mock_logger.error.call_args[1]["extra"]
        assert "image_size" not in extra

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_token_acquisition_start(self, mock_logger):
        TokenLoggingMixin.log_token_acquisition_start(
            acquisition_id="acq1", site_name="court", account="user1",
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["acquisition_id"] == "acq1"
        assert extra["site_name"] == "court"
        assert extra["account"] == "user1"

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_token_acquisition_start_no_account(self, mock_logger):
        TokenLoggingMixin.log_token_acquisition_start(
            acquisition_id="acq1", site_name="court",
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert "account" not in extra

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_token_acquisition_success(self, mock_logger):
        TokenLoggingMixin.log_token_acquisition_success(
            acquisition_id="acq1", site_name="court", account="user1", total_duration=5.0,
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["success"] is True
        assert extra["total_duration"] == 5.0

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_auto_login_start(self, mock_logger):
        TokenLoggingMixin.log_auto_login_start(
            acquisition_id="acq1", site_name="court", account="user1",
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["action"] == "auto_login_start"

    @patch("apps.automation.utils._logging_token_mixin.logger")
    def test_log_auto_login_success(self, mock_logger):
        TokenLoggingMixin.log_auto_login_success(
            acquisition_id="acq1", site_name="court", account="user1", login_duration=3.5,
        )
        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["login_duration"] == 3.5
