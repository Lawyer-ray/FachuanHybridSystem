"""Tests for automation/api/captcha_manual_api.py (missing: 30 lines).

Covers: get_captcha_image and submit_captcha_answer endpoints - all branches.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetCaptchaImage:
    @pytest.mark.asyncio
    async def test_task_not_found(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        mock_manager = MagicMock()
        mock_manager.aget = AsyncMock(side_effect=type("DoesNotExist", (Exception,), {}))
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects = mock_manager
            MockTask.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_manager.aget = AsyncMock(side_effect=MockTask.DoesNotExist)
            response = await get_captcha_image(request, 999)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_task_wrong_status(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(status=ScraperTaskStatus.RUNNING)
        mock_manager = MagicMock()
        mock_manager.aget = AsyncMock(return_value=task)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects = mock_manager
            response = await get_captcha_image(request, 1)
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_no_image_path(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(status=ScraperTaskStatus.WAITING_FOR_CAPTCHA, captcha_image_path=None)
        mock_manager = MagicMock()
        mock_manager.aget = AsyncMock(return_value=task)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects = mock_manager
            response = await get_captcha_image(request, 1)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_image_file_not_found(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(
            status=ScraperTaskStatus.WAITING_FOR_CAPTCHA,
            captcha_image_path="/nonexistent/path.png",
        )
        mock_manager = MagicMock()
        mock_manager.aget = AsyncMock(return_value=task)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects = mock_manager
            with patch("asyncio.to_thread", side_effect=FileNotFoundError):
                response = await get_captcha_image(request, 1)
                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from apps.automation.api.captcha_manual_api import get_captcha_image
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(
            status=ScraperTaskStatus.WAITING_FOR_CAPTCHA,
            captcha_image_path="/tmp/test.png",
        )
        mock_file = MagicMock()
        mock_manager = MagicMock()
        mock_manager.aget = AsyncMock(return_value=task)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects = mock_manager
            with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_file):
                response = await get_captcha_image(request, 1)
                assert response.status_code == 200


class TestSubmitCaptchaAnswer:
    @pytest.mark.asyncio
    async def test_task_not_found(self) -> None:
        from apps.automation.api.captcha_manual_api import submit_captcha_answer, CaptchaAnswerIn
        request = MagicMock()
        mock_manager = MagicMock()
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockTask.objects = mock_manager
            mock_manager.aget = AsyncMock(side_effect=MockTask.DoesNotExist)
            result = await submit_captcha_answer(request, 999, CaptchaAnswerIn(answer="ABC"))
            assert result.success is False
            assert "不存在" in result.message

    @pytest.mark.asyncio
    async def test_wrong_status(self) -> None:
        from apps.automation.api.captcha_manual_api import submit_captcha_answer, CaptchaAnswerIn
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(status=ScraperTaskStatus.RUNNING)
        mock_manager = MagicMock()
        mock_manager.aget = AsyncMock(return_value=task)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects = mock_manager
            result = await submit_captcha_answer(request, 1, CaptchaAnswerIn(answer="ABC"))
            assert result.success is False
            assert "状态" in result.message

    @pytest.mark.asyncio
    async def test_empty_answer(self) -> None:
        from apps.automation.api.captcha_manual_api import submit_captcha_answer, CaptchaAnswerIn
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = SimpleNamespace(status=ScraperTaskStatus.WAITING_FOR_CAPTCHA)
        mock_manager = MagicMock()
        mock_manager.aget = AsyncMock(return_value=task)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects = mock_manager
            result = await submit_captcha_answer(request, 1, CaptchaAnswerIn(answer="   "))
            assert result.success is False
            assert "不能为空" in result.message

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from apps.automation.api.captcha_manual_api import submit_captcha_answer, CaptchaAnswerIn
        from apps.automation.models import ScraperTaskStatus
        request = MagicMock()
        task = MagicMock()
        task.status = ScraperTaskStatus.WAITING_FOR_CAPTCHA
        task.captcha_answer = None
        task.error_message = "some error"
        task.asave = AsyncMock()
        mock_manager = MagicMock()
        mock_manager.aget = AsyncMock(return_value=task)
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects = mock_manager
            result = await submit_captcha_answer(request, 1, CaptchaAnswerIn(answer="XYZ"))
            assert result.success is True
            assert task.captcha_answer == "XYZ"
            assert task.status == ScraperTaskStatus.RUNNING
            assert task.error_message is None
            task.asave.assert_called_once()
