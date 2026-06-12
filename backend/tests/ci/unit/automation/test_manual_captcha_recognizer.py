"""Tests for ManualCaptchaRecognizer and get_captcha_recognizer factory."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest


# ======================================================================
# ManualCaptchaRecognizer
# ======================================================================

class TestManualCaptchaRecognizer:
    def _make_recognizer(self, task=None, timeout=5, poll_interval=0.1):
        from apps.automation.services.scraper.core.captcha_recognizer import ManualCaptchaRecognizer

        if task is None:
            task = SimpleNamespace(id=42, status="running", captcha_image_path=None, captcha_answer=None, error_message=None)
            task.save = MagicMock()
            task.refresh_from_db = MagicMock()

        return ManualCaptchaRecognizer(task=task, timeout=timeout, poll_interval=poll_interval)

    def test_init(self):
        r = self._make_recognizer(timeout=600, poll_interval=1.0)
        assert r.timeout == 600
        assert r.poll_interval == 1.0
        assert r.task.id == 42

    def test_recognize_empty_bytes_returns_none(self):
        r = self._make_recognizer()
        assert r.recognize(b"") is None
        assert r.recognize(None) is None

    def test_recognize_saves_image_and_sets_status(self):
        task = SimpleNamespace(id=99, status="running", captcha_image_path=None, captcha_answer=None, error_message=None)
        task.save = MagicMock()
        task.refresh_from_db = MagicMock(side_effect=self._simulate_answer(task, "AB12", after_calls=1))

        r = self._make_recognizer(task=task, timeout=5, poll_interval=0.01)

        with patch("apps.automation.services.scraper.core.captcha_recognizer.Path") as MockPath, \
             patch("apps.automation.services.scraper.core.captcha_recognizer.time") as mock_time:
            mock_time.time.return_value = 1000.0
            mock_time.sleep = MagicMock()

            mock_captcha_dir = MagicMock()
            MockPath.return_value.__truediv__ = MagicMock(return_value=mock_captcha_dir)
            mock_captcha_dir.mkdir = MagicMock()
            mock_captcha_dir.__truediv__ = MagicMock(return_value=mock_captcha_dir)
            mock_captcha_dir.write_bytes = MagicMock()

            with patch("django.conf.settings.MEDIA_ROOT", "/media"):
                result = r.recognize(b"fake_captcha_image")

        assert result == "AB12"
        task.save.assert_called_once()

    def test_recognize_timeout_returns_none(self):
        """超时后应返回 None"""
        task = SimpleNamespace(id=77, status="running", captcha_image_path=None, captcha_answer=None, error_message=None)
        task.save = MagicMock()
        # refresh_from_db 永远不设置 answer → 超时
        task.refresh_from_db = MagicMock()

        r = self._make_recognizer(task=task, timeout=1, poll_interval=0.1)

        with patch("apps.automation.services.scraper.core.captcha_recognizer.Path") as MockPath:
            mock_file = MagicMock()
            MockPath.return_value.__truediv__ = MagicMock(return_value=MagicMock(
                mkdir=MagicMock(),
                __truediv__=MagicMock(return_value=mock_file),
            ))

            with patch("django.conf.settings.MEDIA_ROOT", "/media"):
                result = r.recognize(b"img")

        assert result is None
        assert task.error_message == "手动验证码等待超时"

    def test_recognize_strips_whitespace(self):
        """返回值应去除空格"""
        task = SimpleNamespace(id=1, status="running", captcha_image_path=None, captcha_answer=None, error_message=None)
        task.save = MagicMock()
        task.refresh_from_db = MagicMock(side_effect=self._simulate_answer(task, " A B 1 2 ", after_calls=1))

        r = self._make_recognizer(task=task, timeout=5, poll_interval=0.01)

        with patch("apps.automation.services.scraper.core.captcha_recognizer.Path") as MockPath:
            MockPath.return_value.__truediv__ = MagicMock(return_value=MagicMock(
                mkdir=MagicMock(),
                __truediv__=MagicMock(return_value=MagicMock(write_bytes=MagicMock())),
            ))
            with patch("django.conf.settings.MEDIA_ROOT", "/media"):
                result = r.recognize(b"img")

        assert result == "AB12"

    @staticmethod
    def _simulate_answer(task, answer, after_calls=1):
        """生成 refresh_from_db side_effect：前 N 次不设置 answer，之后设置"""
        call_count = {"n": 0}

        def side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] > after_calls:
                task.captcha_answer = answer

        return side_effect


# ======================================================================
# get_captcha_recognizer
# ======================================================================

class TestGetCaptchaRecognizer:
    def test_auto_enabled_returns_ddddocr(self):
        from apps.automation.services.scraper.core.captcha_recognizer import (
            get_captcha_recognizer, DdddocrRecognizer,
        )
        with patch("apps.core.services.system_config_service.SystemConfigService") as MockSvc:
            MockSvc.return_value.get_value.return_value = "true"
            result = get_captcha_recognizer()
        assert isinstance(result, DdddocrRecognizer)

    def test_auto_disabled_with_task_returns_manual(self):
        from apps.automation.services.scraper.core.captcha_recognizer import (
            get_captcha_recognizer, ManualCaptchaRecognizer,
        )
        task = SimpleNamespace(id=1)
        with patch("apps.core.services.system_config_service.SystemConfigService") as MockSvc:
            MockSvc.return_value.get_value.return_value = "false"
            result = get_captcha_recognizer(task=task)
        assert isinstance(result, ManualCaptchaRecognizer)
        assert result.task is task

    def test_auto_disabled_no_task_returns_ddddocr(self):
        from apps.automation.services.scraper.core.captcha_recognizer import (
            get_captcha_recognizer, DdddocrRecognizer,
        )
        with patch("apps.core.services.system_config_service.SystemConfigService") as MockSvc:
            MockSvc.return_value.get_value.return_value = "false"
            result = get_captcha_recognizer()
        assert isinstance(result, DdddocrRecognizer)
