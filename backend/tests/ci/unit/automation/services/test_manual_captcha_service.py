"""ManualCaptchaService 单元测试。

覆盖验证码图片读取（任务不存在 / 状态不符 / 无图片 / 文件丢失 / 成功）
与答案提交（任务不存在 / 状态不符 / 空答案 / 成功），失败路径返回
结果对象而非抛异常（200 契约由 API 层组装）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.automation.services.captcha.manual_captcha_service import ManualCaptchaService


def _task(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "status": None,
        "captcha_image_path": None,
        "captcha_answer": None,
        "error_message": "err",
        "asave": AsyncMock(),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_image_task_not_found() -> None:
    with patch("apps.automation.models.ScraperTask") as mock_task:
        mock_task.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_task.objects.aget = AsyncMock(side_effect=mock_task.DoesNotExist)
        payload = await ManualCaptchaService().get_captcha_image(999)
    assert payload.error_status == 404
    assert payload.error_message == "任务不存在"


@pytest.mark.asyncio
async def test_image_wrong_status() -> None:
    from apps.automation.models import ScraperTaskStatus

    task = _task(status=ScraperTaskStatus.RUNNING)
    with patch("apps.automation.models.ScraperTask") as mock_task:
        mock_task.objects.aget = AsyncMock(return_value=task)
        payload = await ManualCaptchaService().get_captcha_image(1)
    assert payload.error_status == 400
    assert payload.error_message == "当前任务不在等待验证码状态"


@pytest.mark.asyncio
async def test_image_no_path() -> None:
    from apps.automation.models import ScraperTaskStatus

    task = _task(status=ScraperTaskStatus.WAITING_FOR_CAPTCHA, captcha_image_path=None)
    with patch("apps.automation.models.ScraperTask") as mock_task:
        mock_task.objects.aget = AsyncMock(return_value=task)
        payload = await ManualCaptchaService().get_captcha_image(1)
    assert payload.error_status == 404
    assert payload.error_message == "验证码图片不存在"


@pytest.mark.asyncio
async def test_image_file_lost() -> None:
    from apps.automation.models import ScraperTaskStatus

    task = _task(status=ScraperTaskStatus.WAITING_FOR_CAPTCHA, captcha_image_path="/gone.png")
    with (
        patch("apps.automation.models.ScraperTask") as mock_task,
        patch("asyncio.to_thread", side_effect=FileNotFoundError),
    ):
        mock_task.objects.aget = AsyncMock(return_value=task)
        payload = await ManualCaptchaService().get_captcha_image(1)
    assert payload.error_status == 404
    assert payload.error_message == "验证码图片文件已丢失"


@pytest.mark.asyncio
async def test_image_success() -> None:
    from apps.automation.models import ScraperTaskStatus

    task = _task(status=ScraperTaskStatus.WAITING_FOR_CAPTCHA, captcha_image_path="/tmp/c.png")
    mock_file = MagicMock()
    with (
        patch("apps.automation.models.ScraperTask") as mock_task,
        patch("asyncio.to_thread", new=AsyncMock(return_value=mock_file)),
    ):
        mock_task.objects.aget = AsyncMock(return_value=task)
        payload = await ManualCaptchaService().get_captcha_image(1)
    assert payload.error_status is None
    assert payload.file_obj is mock_file


@pytest.mark.asyncio
async def test_answer_task_not_found() -> None:
    with patch("apps.automation.models.ScraperTask") as mock_task:
        mock_task.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_task.objects.aget = AsyncMock(side_effect=mock_task.DoesNotExist)
        result = await ManualCaptchaService().submit_answer(999, "ABC")
    assert result.success is False
    assert result.message == "任务不存在"


@pytest.mark.asyncio
async def test_answer_wrong_status() -> None:
    from apps.automation.models import ScraperTaskStatus

    task = _task(status=ScraperTaskStatus.RUNNING)
    with patch("apps.automation.models.ScraperTask") as mock_task:
        mock_task.objects.aget = AsyncMock(return_value=task)
        result = await ManualCaptchaService().submit_answer(1, "ABC")
    assert result.success is False
    assert "状态" in result.message


@pytest.mark.asyncio
async def test_answer_empty_rejected() -> None:
    from apps.automation.models import ScraperTaskStatus

    task = _task(status=ScraperTaskStatus.WAITING_FOR_CAPTCHA)
    with patch("apps.automation.models.ScraperTask") as mock_task:
        mock_task.objects.aget = AsyncMock(return_value=task)
        result = await ManualCaptchaService().submit_answer(1, "   ")
    assert result.success is False
    assert result.message == "验证码答案不能为空"
    task.asave.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_answer_success_restores_running() -> None:
    from apps.automation.models import ScraperTaskStatus

    task = _task(status=ScraperTaskStatus.WAITING_FOR_CAPTCHA)
    with patch("apps.automation.models.ScraperTask") as mock_task:
        mock_task.objects.aget = AsyncMock(return_value=task)
        result = await ManualCaptchaService().submit_answer(1, "  XYZ  ")

    assert result.success is True
    assert task.captcha_answer == "XYZ"
    assert task.status == ScraperTaskStatus.RUNNING
    assert task.error_message == ""
    task.asave.assert_awaited_once()  # type: ignore[attr-defined]
