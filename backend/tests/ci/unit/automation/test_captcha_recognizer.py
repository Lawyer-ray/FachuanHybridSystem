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


# ── ManualCaptchaRecognizer.__init__ ─────────────────────────────────────────


class TestManualCaptchaRecognizerInit:

    def test_default_values(self):
        task = MagicMock()
        r = ManualCaptchaRecognizer(task=task)
        assert r.task is task
        assert r.timeout == 300
        assert r.poll_interval == 2.0

    def test_custom_values(self):
        task = MagicMock()
        r = ManualCaptchaRecognizer(task=task, timeout=60, poll_interval=0.5)
        assert r.timeout == 60
        assert r.poll_interval == 0.5


# ── ManualCaptchaRecognizer.recognize ───────────────────────────────────────


class TestManualCaptchaRecognizerRecognize:

    def test_empty_bytes_returns_none(self):
        task = MagicMock()
        r = ManualCaptchaRecognizer(task=task)
        assert r.recognize(b"") is None

    def test_timeout_returns_none(self):
        """Test that when the poll loop times out, None is returned."""
        task = MagicMock()
        task.id = "task_1"
        task.captcha_answer = None
        task.status = "WAITING_FOR_CAPTCHA"

        r = ManualCaptchaRecognizer(task=task, timeout=0, poll_interval=0.01)

        with patch("plugins.court_automation.login.captcha_recognizer.Path") as mock_path_cls:
            mock_path_instance = MagicMock()
            mock_path_instance.__truediv__ = MagicMock(return_value=MagicMock())
            mock_path_cls.return_value = mock_path_instance

            with patch("django.conf.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = "/tmp/media"
                result = r.recognize(b"\x89PNG")
                assert result is None


# ── ManualCaptchaRecognizer.recognize_from_element ──────────────────────────


class TestRecognizeFromElement:

    def test_element_screenshot_success(self):
        task = MagicMock()
        r = ManualCaptchaRecognizer(task=task)

        mock_element = MagicMock()
        mock_element.screenshot.return_value = b"\x89PNG_data"

        mock_page = MagicMock()
        mock_page.locator.return_value = mock_element

        with patch.object(r, "recognize", return_value="1234") as mock_rec:
            result = r.recognize_from_element(mock_page, "#captcha")
            mock_page.locator.assert_called_once_with("#captcha")
            mock_element.wait_for.assert_called_once_with(state="visible", timeout=5000)
            mock_element.screenshot.assert_called_once()
            mock_rec.assert_called_once_with(b"\x89PNG_data")
            assert result == "1234"

    def test_element_not_found_returns_none(self):
        task = MagicMock()
        r = ManualCaptchaRecognizer(task=task)

        mock_element = MagicMock()
        mock_element.wait_for.side_effect = TimeoutError("element not found")

        mock_page = MagicMock()
        mock_page.locator.return_value = mock_element

        result = r.recognize_from_element(mock_page, "#missing")
        assert result is None

    def test_screenshot_failure_returns_none(self):
        task = MagicMock()
        r = ManualCaptchaRecognizer(task=task)

        mock_element = MagicMock()
        mock_element.screenshot.side_effect = RuntimeError("screenshot failed")

        mock_page = MagicMock()
        mock_page.locator.return_value = mock_element

        result = r.recognize_from_element(mock_page, "#captcha")
        assert result is None


# ── get_captcha_recognizer ──────────────────────────────────────────────────


class TestGetCaptchaRecognizer:

    def test_plugin_available(self):
        mock_plugin = MagicMock(return_value=True)

        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=mock_plugin)}):
            mock_ddddocr = MagicMock()
            mock_ddddocr_cls = MagicMock(return_value=mock_ddddocr)
            with patch.dict("sys.modules", {"plugins.captcha_ocr": MagicMock(DdddocrRecognizer=mock_ddddocr_cls)}):
                result = get_captcha_recognizer()
                assert result is mock_ddddocr

    def test_plugin_not_available_with_task(self):
        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=MagicMock(return_value=False))}):
            task = MagicMock()
            result = get_captcha_recognizer(task=task)
            assert isinstance(result, ManualCaptchaRecognizer)
            assert result.task is task

    def test_import_error_with_task(self):
        with patch.dict("sys.modules", {"plugins": None}):
            task = MagicMock()
            with patch.dict("sys.modules", {"plugins.captcha_ocr": None}):
                result = get_captcha_recognizer(task=task)
                assert isinstance(result, ManualCaptchaRecognizer)

    def test_no_task_no_plugin_raises(self):
        with patch.dict("sys.modules", {"plugins": None}):
            with patch.dict("sys.modules", {"plugins.captcha_ocr": None}):
                result = get_captcha_recognizer(task=None)
                from apps.automation.services.scraper.core.captcha_recognizer import FileBasedCaptchaRecognizer
                assert isinstance(result, FileBasedCaptchaRecognizer)


# ── CaptchaRecognizer ABC ──────────────────────────────────────────────────


class TestCaptchaRecognizerABC:

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            CaptchaRecognizer()  # type: ignore[abstract]

    def test_subclass_must_implement(self):
        class IncompleteRecognizer(CaptchaRecognizer):
            pass

        with pytest.raises(TypeError):
            IncompleteRecognizer()  # type: ignore[abstract]

    def test_complete_subclass(self):
        class CompleteRecognizer(CaptchaRecognizer):
            def recognize(self, image_bytes):
                return "done"

            def recognize_from_element(self, page, selector):
                return "done"

        r = CompleteRecognizer()
        assert r.recognize(b"") == "done"
        assert r.recognize_from_element(None, "") == "done"
