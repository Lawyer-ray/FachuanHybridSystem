"""Tests for captcha_recognizer uncovered branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

from apps.automation.services.scraper.core.captcha_recognizer import (
    CaptchaRecognizer,
    ManualCaptchaRecognizer,
    get_captcha_recognizer,
)

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


class TestGetCaptchaRecognizer:
    """Cover get_captcha_recognizer branches."""

    def test_plugin_available_returns_ddddocr(self):
        with patch.dict("sys.modules", {
            "plugins": MagicMock(has_captcha_ocr_plugin=lambda: True),
            "plugins.captcha_ocr": MagicMock(DdddocrRecognizer=MagicMock(return_value="recognizer")),
        }):
            result = get_captcha_recognizer()
            assert result == "recognizer"

    def test_plugin_import_error_with_task_returns_manual(self):
        with patch.dict("sys.modules", {"plugins": None}):
            task = MagicMock()
            result = get_captcha_recognizer(task=task)
            assert isinstance(result, ManualCaptchaRecognizer)

    def test_plugin_not_available_with_task_returns_manual(self):
        with patch.dict("sys.modules", {
            "plugins": MagicMock(has_captcha_ocr_plugin=lambda: False),
        }):
            task = MagicMock()
            result = get_captcha_recognizer(task=task)
            assert isinstance(result, ManualCaptchaRecognizer)

    def test_no_plugin_no_task_raises(self):
        with patch.dict("sys.modules", {"plugins": None}):
            from apps.automation.services.scraper.core.captcha_recognizer import FileBasedCaptchaRecognizer
            result = get_captcha_recognizer()
            assert isinstance(result, FileBasedCaptchaRecognizer)

    def test_no_task_raises_when_plugin_unavailable(self):
        with patch.dict("sys.modules", {
            "plugins": MagicMock(has_captcha_ocr_plugin=lambda: False),
        }):
            from apps.automation.services.scraper.core.captcha_recognizer import FileBasedCaptchaRecognizer
            result = get_captcha_recognizer(task=None)
            assert isinstance(result, FileBasedCaptchaRecognizer)


class TestManualCaptchaRecognizerRecognizeSuccess:
    """Cover the success path of ManualCaptchaRecognizer.recognize."""

    def test_recognize_success_path(self):
        task = MagicMock()
        task.id = "task_1"
        task.captcha_answer = None
        task.status = "WAITING_FOR_CAPTCHA"

        r = ManualCaptchaRecognizer(task=task, timeout=5, poll_interval=0.01)

        # Simulate: first poll returns None, second returns answer
        call_count = 0
        def refresh_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                task.captcha_answer = "  1234  "

        task.refresh_from_db = MagicMock(side_effect=refresh_side_effect)

        with patch("plugins.court_automation.login.captcha_recognizer.Path") as mock_path_cls:
            mock_captcha_dir = MagicMock()
            mock_image_path = MagicMock()
            mock_image_path.__truediv__ = MagicMock(return_value=mock_image_path)
            mock_path_cls.return_value = mock_captcha_dir
            mock_captcha_dir.__truediv__ = MagicMock(return_value=mock_image_path)

            with patch("django.conf.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = "/tmp/media"
                with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
                    mock_status.WAITING_FOR_CAPTCHA = "WAITING_FOR_CAPTCHA"
                    with patch("django.core.files.storage.default_storage") as mock_storage:
                        mock_storage.save.return_value = "automation/captcha_pending/test.png"
                        result = r.recognize(b"\x89PNG")

        assert result == "1234"  # stripped and spaces removed
        mock_storage.delete.assert_called_once_with("automation/captcha_pending/test.png")

    def test_recognize_exception_returns_none(self):
        task = MagicMock()
        task.id = "task_1"
        r = ManualCaptchaRecognizer(task=task, timeout=1, poll_interval=0.01)

        with patch("plugins.court_automation.login.captcha_recognizer.Path") as mock_path_cls:
            mock_path_cls.side_effect = Exception("path error")
            with patch("django.conf.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = "/tmp/media"
                result = r.recognize(b"\x89PNG")
        assert result is None


class TestManualCaptchaRecognizerTimeoutWithStatusUpdate:
    """Cover timeout path with status update."""

    def test_timeout_updates_error_message(self):
        task = MagicMock()
        task.id = "task_timeout"
        task.captcha_answer = None
        task.status = "WAITING_FOR_CAPTCHA"
        task.save = MagicMock()

        r = ManualCaptchaRecognizer(task=task, timeout=0, poll_interval=0.01)

        with patch("plugins.court_automation.login.captcha_recognizer.Path") as mock_path_cls, \
             patch("django.conf.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/tmp/media"
            mock_dir = MagicMock()
            mock_path_instance = MagicMock()
            mock_path_instance.__truediv__ = MagicMock(return_value=MagicMock())
            mock_path_cls.return_value = mock_dir
            mock_dir.__truediv__ = MagicMock(return_value=mock_path_instance)

            result = r.recognize(b"\x89PNG")
        assert result is None


class TestManualCaptchaRecognizerUnlinkError:
    """Cover the unlink exception path."""

    def test_unlink_error_is_ignored(self):
        """When image_path.unlink raises, it should be silently caught and answer still returned."""
        task = MagicMock()
        task.id = "task_unlink"
        task.captcha_answer = None  # starts as None
        task.status = "WAITING_FOR_CAPTCHA"

        r = ManualCaptchaRecognizer(task=task, timeout=5, poll_interval=0.01)

        # First refresh returns None, second returns answer
        refresh_count = 0
        def refresh_side_effect(*args, **kwargs):
            nonlocal refresh_count
            refresh_count += 1
            if refresh_count >= 2:
                task.captcha_answer = "5678"

        task.refresh_from_db = MagicMock(side_effect=refresh_side_effect)

        with patch("plugins.court_automation.login.captcha_recognizer.Path") as mock_path_cls:
            mock_dir = MagicMock()
            mock_image_path = MagicMock()
            mock_image_path.unlink.side_effect = PermissionError("no access")
            mock_dir.__truediv__ = MagicMock(return_value=mock_image_path)
            mock_path_cls.return_value = mock_dir

            with patch("django.conf.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = "/tmp/media"
                with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
                    mock_status.WAITING_FOR_CAPTCHA = "WAITING_FOR_CAPTCHA"
                    result = r.recognize(b"\x89PNG")

        assert result == "5678"


class TestCaptchaRecognizerABC:
    """Cover ABC interface."""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            CaptchaRecognizer()
