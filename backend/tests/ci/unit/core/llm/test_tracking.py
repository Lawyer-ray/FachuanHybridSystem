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


class _StubFallbackPolicy:
    """只回放预设响应的最小 fallback 策略，用于隔离 client 层。"""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    async def execute_async(self, *, operation: Any, backend: str, fallback: bool) -> Any:
        if self._error is not None:
            raise self._error
        return self._response


class TestClientAsyncAuditIntegration:
    """LLMClient.achat/aembed_texts 在真实事件循环 + 真实 DB 下写入审计。

    回归保护：异步路径必须走 acreate，否则在事件循环里调用同步
    objects.create 会抛 SynchronousOnlyOperation 且被吞掉，导致审计静默丢失。
    """

    def _make_response(self) -> Any:
        from apps.core.llm.backends import LLMResponse

        return LLMResponse(
            content="ok",
            model="kimi26",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            duration_ms=3.2,
            backend="openai_compatible",
        )

    async def _run_achat(self, policy: _StubFallbackPolicy) -> None:
        from apps.core.llm.client import LLMClient

        client = LLMClient(default_backend="openai_compatible")
        await client.achat(
            fallback_policy=policy,
            messages=[{"role": "user", "content": "hi"}],
            caller="test.client_async",
        )

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_achat_success_writes_record(self) -> None:
        from asgiref.sync import sync_to_async

        from apps.core.models import LLMCallRecord

        await self._run_achat(_StubFallbackPolicy(response=self._make_response()))

        record = await sync_to_async(LLMCallRecord.objects.get)()
        assert record.success is True
        assert record.model == "kimi26"
        assert record.backend == "openai_compatible"
        assert record.caller == "test.client_async"
        assert record.total_tokens == 15

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_achat_failure_records_error(self) -> None:
        from asgiref.sync import sync_to_async

        from apps.core.llm.exceptions import LLMTimeoutError
        from apps.core.models import LLMCallRecord

        error = LLMTimeoutError(message="超时", timeout_seconds=120)
        with pytest.raises(LLMTimeoutError):
            await self._run_achat(_StubFallbackPolicy(error=error))

        record = await sync_to_async(LLMCallRecord.objects.get)()
        assert record.success is False
        assert record.error_type == "LLMTimeoutError"

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_aembed_success_writes_record(self) -> None:
        from asgiref.sync import sync_to_async

        from apps.core.llm.client import LLMClient
        from apps.core.models import LLMCallRecord

        client = LLMClient(default_backend="openai_compatible")
        result = await client.aembed_texts(
            fallback_policy=_StubFallbackPolicy(response=[[0.1, 0.2]]),
            texts=["a"],
            model="kimi26",
            caller="test.client_async",
        )

        assert result == [[0.1, 0.2]]
        record = await sync_to_async(LLMCallRecord.objects.get)()
        assert record.success is True
        assert record.model == "kimi26"
