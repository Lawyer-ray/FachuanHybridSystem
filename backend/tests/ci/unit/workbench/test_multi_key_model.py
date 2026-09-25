"""Unit tests for workbench.agents.multi_key_model."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings

from apps.core.llm.backends.base import OpenAIProviderConfig
from apps.core.llm.exceptions import LLMAPIError
from apps.core.llm.key_pool import KeyPool
from apps.workbench.agents.multi_key_model import (
    DEFAULT_AGENT_CONCURRENCY,
    MultiKeyOpenAIModel,
    agent_concurrency_capacity,
    shared_key_pool,
)

MODEL = "test-model"


class _FakeModel(Model):
    """最小可用的底层模型替身：记录调用次数，可配置为建立阶段即报错。"""

    def __init__(self, name: str, *, error: Exception | None = None, enter_error: Exception | None = None) -> None:
        super().__init__()
        self._name = name
        self._error = error
        self._enter_error = enter_error
        self.request_calls = 0
        self.stream_enters = 0
        self.stream_exits = 0

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def system(self) -> str:
        return "fake"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        self.request_calls += 1
        if self._error is not None:
            raise self._error
        return ModelResponse(parts=[TextPart(content=f"ok-{self._name}")])

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncGenerator[Any]:
        self.stream_enters += 1
        if self._enter_error is not None:
            raise self._enter_error
        try:
            yield f"stream-{self._name}"
        finally:
            self.stream_exits += 1


def _params() -> ModelRequestParameters:
    return ModelRequestParameters()


def _rotating(models: list[_FakeModel], *, limit: int = 0) -> tuple[MultiKeyOpenAIModel, KeyPool]:
    pool = KeyPool([f"k{i}" for i in range(len(models))], concurrency_per_key=limit)
    return MultiKeyOpenAIModel(list(models), pool, MODEL), pool


class TestRequest:
    @pytest.mark.asyncio
    async def test_round_robins_across_keys(self) -> None:
        a, b = _FakeModel("a"), _FakeModel("b")
        model, _ = _rotating([a, b])

        first = await model.request([], None, _params())
        second = await model.request([], None, _params())

        assert first.parts[0].content == "ok-a"  # type: ignore[union-attr]
        assert second.parts[0].content == "ok-b"  # type: ignore[union-attr]
        assert (a.request_calls, b.request_calls) == (1, 1)

    @pytest.mark.asyncio
    async def test_switches_key_on_failure(self) -> None:
        broken = _FakeModel("a", error=RuntimeError("bad key"))
        healthy = _FakeModel("b")
        model, pool = _rotating([broken, healthy])

        result = await model.request([], None, _params())

        assert result.parts[0].content == "ok-b"  # type: ignore[union-attr]
        assert pool.active_counts == [0, 0]
        assert pool.is_cooling(0, MODEL) is True
        assert pool.is_cooling(1, MODEL) is False

    @pytest.mark.asyncio
    async def test_all_keys_fail_raises_last_error(self) -> None:
        first = _FakeModel("a", error=RuntimeError("first"))
        second = _FakeModel("b", error=RuntimeError("second"))
        model, _ = _rotating([first, second])

        with pytest.raises(RuntimeError, match="second"):
            await model.request([], None, _params())

    @pytest.mark.asyncio
    async def test_single_failed_key_leaves_no_available_key(self) -> None:
        model, _ = _rotating([_FakeModel("a", error=RuntimeError("boom"))])

        with pytest.raises(RuntimeError, match="boom"):
            await model.request([], None, _params())
        # 唯一 Key 已进入冷却：不再有候选，抛出可读的兜底错误
        with pytest.raises(LLMAPIError, match="没有可用的 API Key"):
            await model.request([], None, _params())

    @pytest.mark.asyncio
    async def test_metadata_delegates_to_first_model(self) -> None:
        model, _ = _rotating([_FakeModel("a"), _FakeModel("b")])

        assert model.model_name == "a"
        assert model.system == "fake"

    def test_requires_at_least_one_model(self) -> None:
        with pytest.raises(ValueError, match="至少需要一个底层模型"):
            MultiKeyOpenAIModel([], KeyPool(["k"]), MODEL)


class TestRequestStream:
    @pytest.mark.asyncio
    async def test_holds_key_until_stream_closed(self) -> None:
        model, pool = _rotating([_FakeModel("a"), _FakeModel("b")])

        async with model.request_stream([], None, _params()) as stream:
            assert stream == "stream-a"
            # 流式期间必须一直占着槽位，否则「每 Key 并发上限」形同虚设
            assert pool.active_counts == [1, 0]

        assert pool.active_counts == [0, 0]

    @pytest.mark.asyncio
    async def test_establishment_failure_switches_key(self) -> None:
        broken = _FakeModel("a", enter_error=RuntimeError("429"))
        healthy = _FakeModel("b")
        model, pool = _rotating([broken, healthy])

        async with model.request_stream([], None, _params()) as stream:
            assert stream == "stream-b"

        assert broken.stream_enters == 1
        assert healthy.stream_enters == 1
        assert healthy.stream_exits == 1
        assert pool.active_counts == [0, 0]
        assert pool.is_cooling(0, MODEL) is True

    @pytest.mark.asyncio
    async def test_consumer_error_is_not_retried(self) -> None:
        first = _FakeModel("a")
        second = _FakeModel("b")
        model, _ = _rotating([first, second])

        with pytest.raises(RuntimeError, match="consumer"):
            async with model.request_stream([], None, _params()):
                raise RuntimeError("consumer")

        # 已建立连接后不再换 Key，否则会重复输出已产出的内容
        assert (first.stream_enters, second.stream_enters) == (1, 0)
        assert first.stream_exits == 1

    @pytest.mark.asyncio
    async def test_normal_completion_does_not_cool_down_key(self) -> None:
        model, pool = _rotating([_FakeModel("a")])

        async with model.request_stream([], None, _params()):
            pass

        assert pool.is_cooling(0, MODEL) is False

    @pytest.mark.asyncio
    async def test_early_exit_releases_key_without_cool_down(self) -> None:
        model, pool = _rotating([_FakeModel("a"), _FakeModel("b")])

        stream_cm = model.request_stream([], None, _params())
        await stream_cm.__aenter__()
        # 消费方提前退出（break / 客户端断开），未消费完就关闭上下文
        await stream_cm.__aexit__(None, None, None)

        assert pool.active_counts == [0, 0]
        assert pool.is_cooling(0, MODEL) is False
        assert pool.is_cooling(1, MODEL) is False

    @pytest.mark.asyncio
    async def test_all_keys_failing_to_establish_raises_last_error(self) -> None:
        model, _ = _rotating(
            [
                _FakeModel("a", enter_error=RuntimeError("first")),
                _FakeModel("b", enter_error=RuntimeError("second")),
            ]
        )

        with pytest.raises(RuntimeError, match="second"):
            async with model.request_stream([], None, _params()):
                pass

    @pytest.mark.asyncio
    async def test_cancellation_does_not_cool_down_key(self) -> None:
        model, pool = _rotating([_FakeModel("a")])

        async def _consume() -> None:
            async with model.request_stream([], None, _params()):
                await asyncio.sleep(10)

        task = asyncio.create_task(_consume())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert pool.active_counts == [0]
        assert pool.is_cooling(0, MODEL) is False


class TestSharedKeyPool:
    def test_same_config_returns_same_pool(self) -> None:
        provider = OpenAIProviderConfig(name="pool-same", api_keys=["a", "b"], concurrency_per_key=3)

        assert shared_key_pool(provider) is shared_key_pool(provider)

    def test_config_change_rebuilds_pool(self) -> None:
        provider = OpenAIProviderConfig(name="pool-change", api_keys=["a"], concurrency_per_key=3)
        first = shared_key_pool(provider)

        provider.api_keys = ["a", "b"]
        second = shared_key_pool(provider)

        assert first is not second
        assert second.keys == ["a", "b"]

    def test_pool_is_reused_across_builds(self) -> None:
        """每次请求都会 build_model，池必须复用，否则并发上限会被无限放大。"""
        provider = OpenAIProviderConfig(name="pool-reuse", api_keys=["a"], concurrency_per_key=1)

        pool = shared_key_pool(provider)
        pool.acquire(MODEL)

        assert shared_key_pool(provider).active_counts == [1]

    def test_service_path_and_agent_path_share_one_pool(self) -> None:
        """两条路径必须拿到同一个池，否则每 Key 并发上限会被放大成两倍。"""
        from apps.core.llm.backends.base import BackendConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        provider = OpenAIProviderConfig(name="pool-cross-path", api_keys=["a"], concurrency_per_key=1)
        config = BackendConfig(
            name="oai",
            enabled=True,
            priority=1,
            default_model="m",
            providers=[provider],
        )
        backend = OpenAICompatibleBackend(config=config)

        # _key_pool 是「哪条路径取哪个池」的接缝，正是本用例要验证的点
        assert backend._key_pool(provider) is shared_key_pool(provider)

    def test_shared_pool_registry_is_reset_between_tests(self) -> None:
        """conftest 的 autouse fixture 必须让每个用例从空注册表开始。"""
        provider = OpenAIProviderConfig(name="pool-fresh", api_keys=["a"], concurrency_per_key=1)

        assert shared_key_pool(provider).active_counts == [0]


class TestAgentConcurrencyCapacity:
    @pytest.mark.parametrize(
        ("provider", "expected"),
        [
            (None, DEFAULT_AGENT_CONCURRENCY),
            (OpenAIProviderConfig(name="no-key", api_keys=[]), DEFAULT_AGENT_CONCURRENCY),
            (
                OpenAIProviderConfig(name="unlimited", api_keys=["a", "b"], concurrency_per_key=0),
                DEFAULT_AGENT_CONCURRENCY,
            ),
            (OpenAIProviderConfig(name="capped", api_keys=["a", "b", "c"], concurrency_per_key=3), 9),
        ],
    )
    def test_capacity(self, provider: OpenAIProviderConfig | None, expected: int) -> None:
        assert agent_concurrency_capacity(provider) == expected
