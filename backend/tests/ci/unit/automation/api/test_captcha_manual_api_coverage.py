"""Tests for automation/api/captcha_manual_api.py (missing: 30 lines).

Covers: get_captcha_image and submit_captcha_answer endpoints - all branches.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestGetCaptchaImage:
    def test_task_not_found(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        request = MagicMock()
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockTask.objects.get.side_effect = MockTask.DoesNotExist
            response = get_captcha_image(request, 999)
            assert response.status_code == 404

    def test_task_wrong_status(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(status=ScraperTaskStatus.RUNNING)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects.get.return_value = task
            response = get_captcha_image(request, 1)
            assert response.status_code == 400

    def test_no_image_path(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(status=ScraperTaskStatus.WAITING_FOR_CAPTCHA, captcha_image_path=None)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects.get.return_value = task
            response = get_captcha_image(request, 1)
            assert response.status_code == 404

    def test_image_file_not_found(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(
            status=ScraperTaskStatus.WAITING_FOR_CAPTCHA,
            captcha_image_path="/nonexistent/path.png",
        )
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects.get.return_value = task
            with patch("builtins.open", side_effect=FileNotFoundError):
                response = get_captcha_image(request, 1)
                assert response.status_code == 404

    def test_success(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(
            status=ScraperTaskStatus.WAITING_FOR_CAPTCHA,
            captcha_image_path="/tmp/test.png",
        )
        mock_file = MagicMock()
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects.get.return_value = task
            with patch("builtins.open", return_value=mock_file):
                response = get_captcha_image(request, 1)
                assert response.status_code == 200


class TestSubmitCaptchaAnswer:
    def test_task_not_found(self) -> None:
        from apps.automation.api.captcha_manual_api import submit_captcha_answer, CaptchaAnswerIn
        request = MagicMock()
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockTask.objects.get.side_effect = MockTask.DoesNotExist
            result = submit_captcha_answer(request, 999, CaptchaAnswerIn(answer="ABC"))
            assert result.success is False
            assert "不存在" in result.message

    def test_wrong_status(self) -> None:
        from apps.automation.api.captcha_manual_api import submit_captcha_answer, CaptchaAnswerIn
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(status=ScraperTaskStatus.RUNNING)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects.get.return_value = task
            result = submit_captcha_answer(request, 1, CaptchaAnswerIn(answer="ABC"))
            assert result.success is False
            assert "状态" in result.message

    def test_empty_answer(self) -> None:
        from apps.automation.api.captcha_manual_api import submit_captcha_answer, CaptchaAnswerIn
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(status=ScraperTaskStatus.WAITING_FOR_CAPTCHA)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects.get.return_value = task
            result = submit_captcha_answer(request, 1, CaptchaAnswerIn(answer="   "))
            assert result.success is False
            assert "不能为空" in result.message

    def test_success(self) -> None:
        from apps.automation.api.captcha_manual_api import submit_captcha_answer, CaptchaAnswerIn
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = MagicMock()
        task.status = ScraperTaskStatus.WAITING_FOR_CAPTCHA
        task.captcha_answer = None
        task.error_message = "some error"
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects.get.return_value = task
            result = submit_captcha_answer(request, 1, CaptchaAnswerIn(answer="XYZ"))
            assert result.success is True
            assert task.captcha_answer == "XYZ"
            assert task.status == ScraperTaskStatus.RUNNING
            assert task.error_message is None
            task.save.assert_called_once()
