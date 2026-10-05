"""apps/core/llm/streaming.py 单元测试。

覆盖 stream_with_fallback / astream_with_fallback 的：
指定后端直通、优先级降级、不可用跳过、空流、认证错误透传、
可重试与未知错误的 fallback/非 fallback 分支、全部失败聚合。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.core.llm.backends import LLMStreamChunk
from apps.core.llm.exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMBackendUnavailableError,
    LLMNetworkError,
    LLMTimeoutError,
)
from apps.core.llm.streaming import (
    _build_stream_kwargs,
    _handle_stream_error,
    _resolve_backends,
    astream_with_fallback,
    stream_with_fallback,
)


def _chunk(content: str = "", model: str = "m1", backend: str = "b1") -> LLMStreamChunk:
    return LLMStreamChunk(content=content, model=model, backend=backend)


def _backend(
    *,
    available: bool = True,
    chunks: list[LLMStreamChunk] | None = None,
    error: Exception | None = None,
) -> MagicMock:
    b = MagicMock()
    b.is_available.return_value = available
    b.api_key = "k"
    b.base_url = "http://x"
    b.default_model = "m1"

    effective_chunks = chunks if chunks is not None else [_chunk("hello")]

    def _stream(**kwargs: Any) -> Iterator[LLMStreamChunk]:
        if error is not None:
            raise error
        yield from effective_chunks

    async def _astream(**kwargs: Any) -> AsyncIterator[LLMStreamChunk]:
        if error is not None:
            raise error
        for c in effective_chunks:
            yield c

    b.stream.side_effect = _stream
    b.astream.side_effect = _astream
    return b


MSG: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]


def _collect(gen: Iterator[LLMStreamChunk]) -> list[LLMStreamChunk]:
    return list(gen)


async def _acollect(gen: AsyncIterator[LLMStreamChunk]) -> list[LLMStreamChunk]:
    return [c async for c in gen]


class TestBuildStreamKwargs:
    def test_base_fields(self) -> None:
        kwargs = _build_stream_kwargs(MSG, "m", 0.5, 100)
        assert kwargs == {"messages": MSG, "model": "m", "temperature": 0.5, "max_tokens": 100}

    def test_extra_kwargs_merged(self) -> None:
        kwargs = _build_stream_kwargs(MSG, "m", 0.5, 100, {"top_p": 0.9})
        assert kwargs["top_p"] == 0.9
        assert kwargs["model"] == "m"


class TestResolveBackends:
    def test_named_backend_without_fallback(self) -> None:
        b = _backend()
        result = _resolve_backends(lambda n: b, lambda: [("other", b)], "primary", False)
        assert result == [("primary", b)]

    def test_named_backend_with_fallback_appends_others(self) -> None:
        primary, secondary = _backend(), _backend()
        result = _resolve_backends(
            lambda n: primary,
            lambda: [("primary", primary), ("secondary", secondary)],
            "primary",
            True,
        )
        assert [name for name, _ in result] == ["primary", "secondary"]

    def test_no_backend_uses_priority_list(self) -> None:
        b1, b2 = _backend(), _backend()
        result = _resolve_backends(lambda n: b1, lambda: [("a", b1), ("b", b2)], None, True)
        assert result == [("a", b1), ("b", b2)]


class TestHandleStreamError:
    def test_retriable_with_fallback_records_and_continues(self) -> None:
        errors: list[Any] = []
        _handle_stream_error("b1", LLMTimeoutError(message="t"), True, errors)
        assert len(errors) == 1

    def test_retriable_without_fallback_raises(self) -> None:
        """生产代码在 except 块内调用，bare raise 在该上下文中重抛原异常。"""
        with pytest.raises(LLMTimeoutError):
            try:
                raise LLMTimeoutError(message="t")
            except LLMTimeoutError:
                _handle_stream_error("b1", LLMTimeoutError(message="t"), False, [])

    def test_unknown_error_without_fallback_wraps_in_api_error(self) -> None:
        with pytest.raises(LLMAPIError):
            _handle_stream_error("b1", ValueError("boom"), False, [])

    def test_unknown_error_with_fallback_records(self) -> None:
        errors: list[Any] = []
        _handle_stream_error("b1", ValueError("boom"), True, errors)
        assert len(errors) == 1


class TestStreamWithFallback:
    def test_pinned_backend_without_fallback_streams_directly(self) -> None:
        b = _backend(chunks=[_chunk("a"), _chunk("b")])
        result = _collect(
            stream_with_fallback(
                get_backend=lambda n: b,
                get_backends_by_priority=lambda: [],
                backend="openai_compatible",
                fallback=False,
                messages=MSG,
                model="m1",
                temperature=0.7,
                max_tokens=10,
            )
        )
        assert [c.content for c in result] == ["a", "b"]
        b.stream.assert_called_once()

    def test_pinned_backend_kwarg_passthrough(self) -> None:
        b = _backend(chunks=[_chunk("x")])
        _collect(
            stream_with_fallback(
                get_backend=lambda n: b,
                get_backends_by_priority=lambda: [],
                backend="openai_compatible",
                fallback=False,
                messages=MSG,
                model="m1",
                temperature=0.2,
                max_tokens=5,
                top_p=0.8,
            )
        )
        assert b.stream.call_args.kwargs["top_p"] == 0.8
        assert b.stream.call_args.kwargs["temperature"] == 0.2

    def test_first_backend_stream_works(self) -> None:
        b = _backend(chunks=[_chunk("ok")])
        result = _collect(
            stream_with_fallback(
                get_backend=lambda n: b,
                get_backends_by_priority=lambda: [("openai_compatible", b)],
                backend=None,
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        assert result[0].content == "ok"

    def test_fallback_to_second_backend_on_retriable_error(self) -> None:
        bad = _backend(error=LLMNetworkError(message="down"))
        good = _backend(chunks=[_chunk("rescued")])
        result = _collect(
            stream_with_fallback(
                get_backend=lambda n: bad if n == "bad" else good,
                get_backends_by_priority=lambda: [("bad", bad), ("good", good)],
                backend=None,
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        assert [c.content for c in result] == ["rescued"]

    def test_no_fallback_first_backend_error_raises(self) -> None:
        bad = _backend(error=LLMAPIError(message="err"))
        with pytest.raises(LLMAPIError):
            _collect(
                stream_with_fallback(
                    get_backend=lambda n: bad,
                    get_backends_by_priority=lambda: [("bad", bad)],
                    backend=None,
                    fallback=False,
                    messages=MSG,
                    model=None,
                    temperature=0.7,
                    max_tokens=None,
                )
            )

    def test_unavailable_backend_skipped_then_success(self) -> None:
        unavailable = _backend(available=False)
        good = _backend(chunks=[_chunk("second")])
        result = _collect(
            stream_with_fallback(
                get_backend=lambda n: unavailable if n == "u" else good,
                get_backends_by_priority=lambda: [("u", unavailable), ("good", good)],
                backend=None,
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        assert result[0].content == "second"

    def test_empty_stream_returns_nothing(self) -> None:
        b = _backend(chunks=[])
        result = _collect(
            stream_with_fallback(
                get_backend=lambda n: b,
                get_backends_by_priority=lambda: [("openai_compatible", b)],
                backend=None,
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        assert result == []

    def test_authentication_error_propagates(self) -> None:
        bad = _backend(error=LLMAuthenticationError(message="bad key"))
        with pytest.raises(LLMAuthenticationError):
            _collect(
                stream_with_fallback(
                    get_backend=lambda n: bad,
                    get_backends_by_priority=lambda: [("bad", bad)],
                    backend=None,
                    fallback=True,
                    messages=MSG,
                    model=None,
                    temperature=0.7,
                    max_tokens=None,
                )
            )

    def test_unknown_error_falls_back_when_fallback_enabled(self) -> None:
        bad = _backend(error=ValueError("weird"))
        good = _backend(chunks=[_chunk("ok-after-weird")])
        result = _collect(
            stream_with_fallback(
                get_backend=lambda n: bad if n == "bad" else good,
                get_backends_by_priority=lambda: [("bad", bad), ("good", good)],
                backend=None,
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        assert result[0].content == "ok-after-weird"

    def test_all_backends_unavailable_raises_backend_unavailable(self) -> None:
        b1 = _backend(available=False)
        b2 = _backend(error=LLMTimeoutError(message="busy"))
        with pytest.raises(LLMBackendUnavailableError) as exc_info:
            _collect(
                stream_with_fallback(
                    get_backend=lambda n: b1 if n == "b1" else b2,
                    get_backends_by_priority=lambda: [("b1", b1), ("b2", b2)],
                    backend=None,
                    fallback=True,
                    messages=MSG,
                    model=None,
                    temperature=0.7,
                    max_tokens=None,
                )
            )
        err = exc_info.value
        assert "所有 LLM 后端均不可用" in str(err)
        # attempts 含错误后端，skipped 含不可用后端
        assert any(n == "b2" for n, _ in err.errors["attempts"])
        assert any(n == "b1" for n, _ in err.errors["skipped"])

    def test_named_backend_with_fallback_includes_priority_backends(self) -> None:
        bad = _backend(error=LLMTimeoutError(message="t"))
        good = _backend(chunks=[_chunk("named-fb")])
        result = _collect(
            stream_with_fallback(
                get_backend=lambda n: bad if n == "bad" else good,
                get_backends_by_priority=lambda: [("good", good)],
                backend="bad",
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        assert result[0].content == "named-fb"


class TestAstreamWithFallback:
    @pytest.mark.asyncio
    async def test_pinned_backend_without_fallback(self) -> None:
        b = _backend(chunks=[_chunk("a1"), _chunk("a2")])
        result = await _acollect(
            astream_with_fallback(
                get_backend=lambda n: b,
                get_backends_by_priority=lambda: [],
                backend="openai_compatible",
                fallback=False,
                messages=MSG,
                model="m1",
                temperature=0.7,
                max_tokens=10,
            )
        )
        assert [c.content for c in result] == ["a1", "a2"]
        b.astream.assert_called_once()

    @pytest.mark.asyncio
    async def test_priority_list_success(self) -> None:
        b = _backend(chunks=[_chunk("async-ok"), _chunk("async-second")])
        result = await _acollect(
            astream_with_fallback(
                get_backend=lambda n: b,
                get_backends_by_priority=lambda: [("openai_compatible", b)],
                backend=None,
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        # 多 chunk 流：首个 chunk 与后续 chunk 都要被产出
        assert [c.content for c in result] == ["async-ok", "async-second"]

    @pytest.mark.asyncio
    async def test_fallback_after_retriable_error(self) -> None:
        bad = _backend(error=LLMTimeoutError(message="timeout"))
        good = _backend(chunks=[_chunk("async-rescued")])
        result = await _acollect(
            astream_with_fallback(
                get_backend=lambda n: bad if n == "bad" else good,
                get_backends_by_priority=lambda: [("bad", bad), ("good", good)],
                backend=None,
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        assert result[0].content == "async-rescued"

    @pytest.mark.asyncio
    async def test_no_fallback_retriable_error_raises(self) -> None:
        bad = _backend(error=LLMNetworkError(message="net down"))
        with pytest.raises(LLMNetworkError):
            await _acollect(
                astream_with_fallback(
                    get_backend=lambda n: bad,
                    get_backends_by_priority=lambda: [("bad", bad)],
                    backend=None,
                    fallback=False,
                    messages=MSG,
                    model=None,
                    temperature=0.7,
                    max_tokens=None,
                )
            )

    @pytest.mark.asyncio
    async def test_unavailable_skipped(self) -> None:
        unavailable = _backend(available=False)
        good = _backend(chunks=[_chunk("async-second")])
        result = await _acollect(
            astream_with_fallback(
                get_backend=lambda n: unavailable if n == "u" else good,
                get_backends_by_priority=lambda: [("u", unavailable), ("good", good)],
                backend=None,
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        assert result[0].content == "async-second"

    @pytest.mark.asyncio
    async def test_empty_async_stream(self) -> None:
        b = _backend(chunks=[])
        result = await _acollect(
            astream_with_fallback(
                get_backend=lambda n: b,
                get_backends_by_priority=lambda: [("openai_compatible", b)],
                backend=None,
                fallback=True,
                messages=MSG,
                model=None,
                temperature=0.7,
                max_tokens=None,
            )
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_authentication_error_propagates(self) -> None:
        bad = _backend(error=LLMAuthenticationError(message="401"))
        with pytest.raises(LLMAuthenticationError):
            await _acollect(
                astream_with_fallback(
                    get_backend=lambda n: bad,
                    get_backends_by_priority=lambda: [("bad", bad)],
                    backend=None,
                    fallback=True,
                    messages=MSG,
                    model=None,
                    temperature=0.7,
                    max_tokens=None,
                )
            )

    @pytest.mark.asyncio
    async def test_unknown_error_wrapped_when_no_fallback(self) -> None:
        bad = _backend(error=RuntimeError("kaboom"))
        with pytest.raises(LLMAPIError):
            await _acollect(
                astream_with_fallback(
                    get_backend=lambda n: bad,
                    get_backends_by_priority=lambda: [("bad", bad)],
                    backend=None,
                    fallback=False,
                    messages=MSG,
                    model=None,
                    temperature=0.7,
                    max_tokens=None,
                )
            )

    @pytest.mark.asyncio
    async def test_all_unavailable_raises(self) -> None:
        b = _backend(available=False)
        with pytest.raises(LLMBackendUnavailableError):
            await _acollect(
                astream_with_fallback(
                    get_backend=lambda n: b,
                    get_backends_by_priority=lambda: [("openai_compatible", b)],
                    backend=None,
                    fallback=True,
                    messages=MSG,
                    model=None,
                    temperature=0.7,
                    max_tokens=None,
                )
            )
