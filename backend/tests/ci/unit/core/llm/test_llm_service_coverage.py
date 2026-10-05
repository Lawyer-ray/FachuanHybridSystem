"""apps/core/llm/service.py 单元测试。

覆盖 LLMService 的构造分支、create() 异步工厂、各入口对 LLMClient 的委托、
stream/astream 的调用记录（成功/失败/提前放弃）与 get_llm_service 单例。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.llm.backends import BackendConfig, LLMResponse, LLMStreamChunk, LLMUsage
from apps.core.llm.exceptions import LLMAPIError
from apps.core.llm.service import LLMService, get_llm_service


def _cfg(name: str, *, enabled: bool = True, priority: int = 1) -> BackendConfig:
    return BackendConfig(name=name, enabled=enabled, priority=priority, default_model="m")


def _chunk(content: str = "c", usage: LLMUsage | None = None) -> LLMStreamChunk:
    return LLMStreamChunk(content=content, usage=usage, model="m-used", backend="b-used")


def _make_service() -> tuple[LLMService, MagicMock]:
    """构造 LLMService 并把内部 client 替换为 mock。"""
    with patch("apps.core.llm.config.LLMConfig.get_default_backend", return_value="openai_compatible"):
        svc = LLMService()
    client = MagicMock()
    svc._client = client  # type: ignore[assignment]
    return svc, client


class TestInit:
    def test_explicit_default_backend_wins(self) -> None:
        svc = LLMService(backend_configs={"openai_compatible": _cfg("openai_compatible")}, default_backend="custom")
        assert svc._default_backend == "custom"

    def test_picks_lowest_priority_enabled_backend(self) -> None:
        configs = {
            "b_low": _cfg("b_low", priority=1),
            "b_high": _cfg("b_high", priority=5),
            "b_disabled": _cfg("b_disabled", enabled=False, priority=0),
        }
        svc = LLMService(backend_configs=configs)
        assert svc._default_backend == "b_low"

    def test_no_enabled_backends_falls_back_to_default_name(self) -> None:
        configs = {"b": _cfg("b", enabled=False)}
        svc = LLMService(backend_configs=configs)
        assert svc._default_backend == LLMService.BACKEND_OPENAI_COMPATIBLE

    def test_no_configs_uses_llm_config(self) -> None:
        with patch("apps.core.llm.config.LLMConfig.get_default_backend", return_value="cfg-backend"):
            svc = LLMService()
        assert svc._default_backend == "cfg-backend"

    def test_default_priorities_constant(self) -> None:
        assert LLMService.DEFAULT_PRIORITIES[LLMService.BACKEND_OPENAI_COMPATIBLE] == 1


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_without_args_resolves_async_default(self) -> None:
        cfg = MagicMock()
        cfg.get_default_backend_async = AsyncMock(return_value="async-default")
        cfg.get_openai_compatible_api_key_async = AsyncMock(return_value="k")
        cfg.get_openai_compatible_base_url_async = AsyncMock(return_value="http://x")

        with (
            patch("apps.core.llm.config.LLMConfig", cfg),
            patch("apps.core.llm.config.LLMConfig", cfg),
            patch("apps.core.services.llm_provider_service.LLMProviderService.aget_providers", new_callable=AsyncMock),
        ):
            svc = await LLMService.create()

        assert isinstance(svc, LLMService)
        assert svc._default_backend == "async-default"
        cfg.get_openai_compatible_api_key_async.assert_awaited_once()
        cfg.get_openai_compatible_base_url_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_with_default_backend_skips_async_lookup(self) -> None:
        cfg = MagicMock()
        cfg.get_default_backend_async = AsyncMock(return_value="should-not-be-used")
        cfg.get_openai_compatible_api_key_async = AsyncMock()
        cfg.get_openai_compatible_base_url_async = AsyncMock()

        with (
            patch("apps.core.llm.config.LLMConfig", cfg),
            patch("apps.core.llm.config.LLMConfig", cfg),
            patch("apps.core.services.llm_provider_service.LLMProviderService.aget_providers", new_callable=AsyncMock),
        ):
            svc = await LLMService.create(default_backend="given")

        assert svc._default_backend == "given"
        cfg.get_default_backend_async.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_with_backend_configs_keeps_default(self) -> None:
        cfg = MagicMock()
        cfg.get_default_backend_async = AsyncMock()
        cfg.get_openai_compatible_api_key_async = AsyncMock()
        cfg.get_openai_compatible_base_url_async = AsyncMock()

        with (
            patch("apps.core.llm.config.LLMConfig", cfg),
            patch("apps.core.llm.config.LLMConfig", cfg),
            patch("apps.core.services.llm_provider_service.LLMProviderService.aget_providers", new_callable=AsyncMock),
        ):
            svc = await LLMService.create(backend_configs={"openai_compatible": _cfg("openai_compatible")})

        assert svc._default_backend == "openai_compatible"
        cfg.get_default_backend_async.assert_not_awaited()


class TestDelegation:
    def test_complete_delegates_to_client(self) -> None:
        svc, client = _make_service()
        expected = LLMResponse(
            content="ok", model="m", prompt_tokens=1, completion_tokens=1, total_tokens=2, duration_ms=1.0
        )
        client.complete.return_value = expected

        result = svc.complete(
            "prompt", system_prompt="sp", backend="b", model="m", temperature=0.3, max_tokens=9, caller="caller-x"
        )

        assert result is expected
        kwargs = client.complete.call_args.kwargs
        assert kwargs["prompt"] == "prompt"
        assert kwargs["system_prompt"] == "sp"
        assert kwargs["caller"] == "caller-x"
        assert kwargs["fallback_policy"] is svc._fallback_policy

    def test_complete_captures_caller_when_missing(self) -> None:
        svc, client = _make_service()
        svc.complete("p")
        assert client.complete.call_args.kwargs["caller"]  # capture_caller 兜底

    def test_chat_delegates_to_client(self) -> None:
        svc, client = _make_service()
        msgs: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]
        expected = LLMResponse(
            content="r", model="m", prompt_tokens=1, completion_tokens=1, total_tokens=2, duration_ms=2.0
        )
        client.chat.return_value = expected

        result = svc.chat(msgs, backend="b", model="m", caller="c1")

        assert result is expected
        kwargs = client.chat.call_args.kwargs
        assert kwargs["messages"] is msgs
        assert kwargs["caller"] == "c1"

    @pytest.mark.asyncio
    async def test_achat_delegates_to_client(self) -> None:
        svc, client = _make_service()
        expected = LLMResponse(
            content="r2", model="m2", prompt_tokens=1, completion_tokens=1, total_tokens=2, duration_ms=3.0
        )
        client.achat = AsyncMock(return_value=expected)

        result = await svc.achat([{"role": "user", "content": "x"}], backend="b2", caller="c2")

        assert result is expected
        kwargs = client.achat.await_args.kwargs
        assert kwargs["backend"] == "b2"
        assert kwargs["caller"] == "c2"

    def test_embed_texts_delegates_to_client(self) -> None:
        svc, client = _make_service()
        client.embed_texts.return_value = [[0.1, 0.2]]

        result = svc.embed_texts(["a", "b"], backend="b3", caller="c3")

        assert result == [[0.1, 0.2]]
        kwargs = client.embed_texts.call_args.kwargs
        assert kwargs["texts"] == ["a", "b"]
        assert kwargs["caller"] == "c3"

    @pytest.mark.asyncio
    async def test_aembed_texts_delegates_to_client(self) -> None:
        svc, client = _make_service()
        client.aembed_texts = AsyncMock(return_value=[[0.3]])

        result = await svc.aembed_texts(["z"], model="embed-m", caller="c4")

        assert result == [[0.3]]
        assert client.aembed_texts.await_args.kwargs["model"] == "embed-m"


class TestStream:
    def _patched_stream(self, chunks: list[LLMStreamChunk]) -> MagicMock:
        def fake_stream(**kwargs: Any):
            yield from chunks

        return MagicMock(side_effect=fake_stream)

    def test_stream_success_records_usage(self) -> None:
        svc, _ = _make_service()
        usage = LLMUsage(prompt_tokens=11, completion_tokens=22, total_tokens=33)
        chunks = [_chunk("a"), _chunk("b", usage=usage)]

        with (
            patch("apps.core.llm.service.stream_with_fallback", self._patched_stream(chunks)),
            patch("apps.core.llm.service.record_llm_call") as mock_record,
        ):
            out = list(svc.stream([{"role": "user", "content": "hi"}], caller="sc"))

        assert [c.content for c in out] == ["a", "b"]
        mock_record.assert_called_once()
        kwargs = mock_record.call_args.kwargs
        assert kwargs["success"] is True
        assert kwargs["model"] == "m-used"
        assert kwargs["backend"] == "b-used"
        assert kwargs["prompt_tokens"] == 11
        assert kwargs["completion_tokens"] == 22
        assert kwargs["total_tokens"] == 33

    def test_stream_without_usage_records_zero_tokens(self) -> None:
        svc, _ = _make_service()

        with (
            patch("apps.core.llm.service.stream_with_fallback", self._patched_stream([_chunk("only")])),
            patch("apps.core.llm.service.record_llm_call") as mock_record,
        ):
            list(svc.stream([{"role": "user", "content": "hi"}]))

        kwargs = mock_record.call_args.kwargs
        assert kwargs["prompt_tokens"] == 0
        assert kwargs["total_tokens"] == 0

    def test_stream_error_records_failure_and_reraises(self) -> None:
        svc, _ = _make_service()

        def failing_stream(**kwargs: Any):
            # 首个 chunk 前即失败：记录应回退到调用参数里的 backend/model
            raise LLMAPIError(message="backend exploded")

        with (
            patch("apps.core.llm.service.stream_with_fallback", MagicMock(side_effect=failing_stream)),
            patch("apps.core.llm.service.record_llm_call") as mock_record,
        ):
            with pytest.raises(LLMAPIError):
                list(svc.stream([{"role": "user", "content": "hi"}], backend="b9", model="m9", caller="err-caller"))

        mock_record.assert_called_once()
        kwargs = mock_record.call_args.kwargs
        assert kwargs["success"] is False
        assert kwargs["backend"] == "b9"
        assert kwargs["model"] == "m9"
        assert isinstance(kwargs["error"], LLMAPIError)

    def test_stream_generator_exit_not_recorded(self) -> None:
        svc, _ = _make_service()

        with (
            patch("apps.core.llm.service.stream_with_fallback", self._patched_stream([_chunk("1"), _chunk("2")])),
            patch("apps.core.llm.service.record_llm_call") as mock_record,
        ):
            gen = svc.stream([{"role": "user", "content": "hi"}])
            next(gen)
            gen.close()

        mock_record.assert_not_called()


class TestAstream:
    def _patched_astream(self, chunks: list[LLMStreamChunk]) -> MagicMock:
        async def fake_astream(**kwargs: Any):
            for c in chunks:
                yield c

        return MagicMock(side_effect=fake_astream)

    @pytest.mark.asyncio
    async def test_astream_success_records_usage(self) -> None:
        svc, _ = _make_service()
        usage = LLMUsage(prompt_tokens=4, completion_tokens=5, total_tokens=9)
        chunks = [_chunk("x"), _chunk("y", usage=usage)]

        with (
            patch("apps.core.llm.service.astream_with_fallback", self._patched_astream(chunks)),
            patch("apps.core.llm.service.arecord_llm_call", new_callable=AsyncMock) as mock_record,
        ):
            out = [c async for c in svc.astream([{"role": "user", "content": "hi"}], caller="ac")]

        assert [c.content for c in out] == ["x", "y"]
        mock_record.assert_awaited_once()
        kwargs = mock_record.await_args.kwargs
        assert kwargs["success"] is True
        assert kwargs["total_tokens"] == 9
        assert kwargs["model"] == "m-used"

    @pytest.mark.asyncio
    async def test_astream_error_records_failure(self) -> None:
        svc, _ = _make_service()

        async def failing(**kwargs: Any):
            yield _chunk("first")
            raise LLMAPIError(message="async boom")

        with (
            patch("apps.core.llm.service.astream_with_fallback", MagicMock(side_effect=failing)),
            patch("apps.core.llm.service.arecord_llm_call", new_callable=AsyncMock) as mock_record,
        ):
            with pytest.raises(LLMAPIError):
                _ = [c async for c in svc.astream([{"role": "user", "content": "hi"}])]

        mock_record.assert_awaited_once()
        assert mock_record.await_args.kwargs["success"] is False

    @pytest.mark.asyncio
    async def test_astream_generator_exit_not_recorded(self) -> None:
        svc, _ = _make_service()

        with (
            patch("apps.core.llm.service.astream_with_fallback", self._patched_astream([_chunk("1"), _chunk("2")])),
            patch("apps.core.llm.service.arecord_llm_call", new_callable=AsyncMock) as mock_record,
        ):
            agen = svc.astream([{"role": "user", "content": "hi"}])
            await agen.__anext__()
            await agen.aclose()

        mock_record.assert_not_awaited()


class TestBackendAccess:
    def test_get_backend_via_router(self) -> None:
        svc, _ = _make_service()
        backend = MagicMock()
        with patch.object(svc._router, "get_backend", return_value=backend) as mock_router_get:
            assert svc.get_backend("openai_compatible") is backend
            mock_router_get.assert_called_once_with("openai_compatible")

    def test_get_backend_config_via_router(self) -> None:
        svc, _ = _make_service()
        config = _cfg("openai_compatible")
        with patch.object(svc._router, "get_backend_config", return_value=config) as mock_cfg_get:
            assert svc._get_backend_config("openai_compatible") is config
            mock_cfg_get.assert_called_once_with("openai_compatible")

    def test_internal_get_backend_and_priority_list(self) -> None:
        svc, _ = _make_service()
        backend = MagicMock()
        pairs = [("openai_compatible", backend)]
        with (
            patch.object(svc._router, "get_backend", return_value=backend) as mock_get,
            patch.object(svc._router, "get_backends_by_priority", return_value=pairs) as mock_priority,
        ):
            assert svc._get_backend("openai_compatible") is backend
            assert svc._get_backends_by_priority() == pairs
        mock_get.assert_called_once_with("openai_compatible")
        mock_priority.assert_called_once()


class TestGetLlmServiceSingleton:
    @pytest.mark.django_db
    def test_lazy_init_and_cache(self) -> None:
        import apps.core.llm.service as service_module

        original = service_module._llm_service
        service_module._llm_service = None
        try:
            first = get_llm_service()
            second = get_llm_service()
            assert first is second
            assert isinstance(first, LLMService)
        finally:
            service_module._llm_service = original
