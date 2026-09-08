"""LLM 调用审计追踪测试"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.llm import tracking
from apps.core.llm.exceptions import LLMAPIError, LLMTimeoutError


def _write_kwargs() -> dict[str, Any]:
    return {
        "backend": "openai_compatible",
        "model": "kimi26",
        "duration_ms": 123.4,
        "caller": "test.module",
    }


class TestRecordLlmCall:
    def test_success_writes_record(self) -> None:
        with (
            patch.object(tracking, "is_tracking_enabled", return_value=True),
            patch("apps.core.models.LLMCallRecord.objects.create") as mock_create,
        ):
            tracking.record_llm_call(**_write_kwargs(), prompt_tokens=1, completion_tokens=2, total_tokens=3)

        kwargs = mock_create.call_args.kwargs
        assert kwargs["model"] == "kimi26"
        assert kwargs["backend"] == "openai_compatible"
        assert kwargs["success"] is True
        assert kwargs["total_tokens"] == 3
        assert kwargs["error_type"] == ""

    def test_failure_records_error(self) -> None:
        error = LLMTimeoutError(message="超时", timeout_seconds=120)
        with (
            patch.object(tracking, "is_tracking_enabled", return_value=True),
            patch("apps.core.models.LLMCallRecord.objects.create") as mock_create,
        ):
            tracking.record_llm_call(**_write_kwargs(), success=False, error=error)

        kwargs = mock_create.call_args.kwargs
        assert kwargs["success"] is False
        assert kwargs["error_type"] == "LLMTimeoutError"

    def test_disabled_skips_write(self) -> None:
        with (
            patch.object(tracking, "is_tracking_enabled", return_value=False),
            patch("apps.core.models.LLMCallRecord.objects.create") as mock_create,
        ):
            tracking.record_llm_call(**_write_kwargs())
        mock_create.assert_not_called()

    def test_db_error_is_swallowed(self) -> None:
        """追踪写入失败绝不能影响主流程。"""
        with (
            patch.object(tracking, "is_tracking_enabled", return_value=True),
            patch(
                "apps.core.models.LLMCallRecord.objects.create",
                side_effect=RuntimeError("db down"),
            ),
        ):
            tracking.record_llm_call(**_write_kwargs())  # 不应抛出

    def test_caller_truncated_to_200(self) -> None:
        kwargs = _write_kwargs()
        kwargs.pop("caller")
        with (
            patch.object(tracking, "is_tracking_enabled", return_value=True),
            patch("apps.core.models.LLMCallRecord.objects.create") as mock_create,
        ):
            tracking.record_llm_call(**kwargs, caller="x" * 500)
        assert len(mock_create.call_args.kwargs["caller"]) == 200


class TestArecordLlmCall:
    @pytest.mark.asyncio
    async def test_success_writes_record(self) -> None:
        with (
            patch.object(tracking, "is_tracking_enabled_async", new_callable=AsyncMock, return_value=True),
            patch("apps.core.models.LLMCallRecord.objects.acreate", new_callable=AsyncMock) as mock_create,
        ):
            await tracking.arecord_llm_call(**_write_kwargs(), error=LLMAPIError(message="boom"))

        kwargs = mock_create.call_args.kwargs
        assert kwargs["success"] is True  # error 参数不影响 success 字段，由调用方传入
        assert kwargs["error_type"] == "LLMAPIError"

    @pytest.mark.asyncio
    async def test_db_error_is_swallowed(self) -> None:
        with (
            patch.object(tracking, "is_tracking_enabled_async", new_callable=AsyncMock, return_value=True),
            patch(
                "apps.core.models.LLMCallRecord.objects.acreate",
                new_callable=AsyncMock,
                side_effect=RuntimeError("db down"),
            ),
        ):
            await tracking.arecord_llm_call(**_write_kwargs())  # 不应抛出


class TestIsTrackingEnabled:
    def test_default_enabled(self) -> None:
        with patch("apps.core.llm.config.LLMConfig._get_system_config", return_value=""):
            assert tracking.is_tracking_enabled() is True

    def test_explicit_off(self) -> None:
        with patch("apps.core.llm.config.LLMConfig._get_system_config", return_value="false"):
            assert tracking.is_tracking_enabled() is False


class TestCaptureCaller:
    def test_returns_module_name(self) -> None:
        def _probe() -> str:
            return tracking.capture_caller()

        assert _probe() == __name__

    def test_depth_overflow_returns_empty(self) -> None:
        assert tracking.capture_caller(depth=999) == ""
