"""Tests for LLM streaming and fallback policy - targeting uncovered branches."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.llm.backends.base import BackendConfig, LLMResponse, LLMStreamChunk, LLMUsage
from apps.core.llm.exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMBackendUnavailableError,
    LLMNetworkError,
    LLMTimeoutError,
)


def _make_backend(name="test", available=True, stream_chunks=None):
    """Create a mock backend."""
    backend = MagicMock()
    backend.is_available.return_value = available
    backend.api_key = "test-key"
    backend.base_url = "http://test"
    backend.default_model = "test-model"
    if stream_chunks is not None:
        backend.stream.return_value = iter(stream_chunks)
    return backend


# ==================== streaming.py ====================


class TestResolveBackends:
    """Test _resolve_backends."""

    def test_with_backend_no_fallback(self):
        from apps.core.llm.streaming import _resolve_backends

        get_backend = MagicMock(return_value="backend_instance")
        get_backends_by_priority = MagicMock(return_value=[("primary", "pi"), ("secondary", "si")])

        result = _resolve_backends(get_backend, get_backends_by_priority, "primary", fallback=False)
        assert len(result) == 1
        assert result[0] == ("primary", "backend_instance")

    def test_with_backend_and_fallback(self):
        from apps.core.llm.streaming import _resolve_backends

        get_backend = MagicMock(return_value="backend_instance")
        get_backends_by_priority = MagicMock(return_value=[("primary", "pi"), ("secondary", "si")])

        result = _resolve_backends(get_backend, get_backends_by_priority, "primary", fallback=True)
        assert len(result) == 2

    def test_without_backend(self):
        from apps.core.llm.streaming import _resolve_backends

        get_backend = MagicMock()
        get_backends_by_priority = MagicMock(return_value=[("a", "ai"), ("b", "bi")])

        result = _resolve_backends(get_backend, get_backends_by_priority, None, fallback=True)
        assert result == [("a", "ai"), ("b", "bi")]


class TestHandleStreamError:
    """Test _handle_stream_error."""

    def test_retriable_error_with_fallback(self):
        from apps.core.llm.streaming import _handle_stream_error

        errors = []
        _handle_stream_error("test", LLMTimeoutError(message="timeout", timeout_seconds=30), True, errors)
        assert len(errors) == 1

    def test_retriable_error_without_fallback_raises(self):
        """Test that _handle_stream_error re-raises the active exception when fallback=False."""
        from apps.core.llm.streaming import _handle_stream_error

        errors = []
        exc = LLMTimeoutError(message="timeout", timeout_seconds=30)
        # Simulate the normal call pattern: _handle_stream_error is called inside except block,
        # bare `raise` re-raises the currently active exception.
        try:
            try:
                raise exc
            except LLMTimeoutError:
                _handle_stream_error("test", exc, False, errors)
                pytest.fail("Should have re-raised")
        except LLMTimeoutError:
            pass  # Expected

    def test_unknown_error_with_fallback(self):
        from apps.core.llm.streaming import _handle_stream_error

        errors = []
        _handle_stream_error("test", ValueError("unknown"), True, errors)
        assert len(errors) == 1

    def test_unknown_error_without_fallback_raises_llm_api_error(self):
        from apps.core.llm.streaming import _handle_stream_error

        errors = []
        with pytest.raises(LLMAPIError):
            _handle_stream_error("test", ValueError("unknown"), False, errors)


class TestBuildStreamKwargs:
    """Test _build_stream_kwargs."""

    def test_basic(self):
        from apps.core.llm.streaming import _build_stream_kwargs

        result = _build_stream_kwargs([{"role": "user", "content": "hi"}], "model", 0.7, 100)
        assert result["messages"] == [{"role": "user", "content": "hi"}]
        assert result["model"] == "model"
        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 100

    def test_with_extra_kwargs(self):
        from apps.core.llm.streaming import _build_stream_kwargs

        result = _build_stream_kwargs([], None, 0.5, None, extra_kwargs={"think": True})
        assert result["think"] is True

    def test_no_extra_kwargs(self):
        from apps.core.llm.streaming import _build_stream_kwargs

        result = _build_stream_kwargs([], None, 0.5, None)
        assert "think" not in result


class TestStreamWithFallback:
    """Test stream_with_fallback."""

    def test_single_backend_no_fallback(self):
        from apps.core.llm.streaming import stream_with_fallback

        chunks = [LLMStreamChunk(content="hello"), LLMStreamChunk(content=" world")]
        backend = _make_backend(stream_chunks=chunks)

        get_backend = MagicMock(return_value=backend)
        get_backends_by_priority = MagicMock(return_value=[("test", backend)])

        result = list(stream_with_fallback(
            get_backend=get_backend,
            get_backends_by_priority=get_backends_by_priority,
            backend="test",
            fallback=False,
            messages=[],
            model=None,
            temperature=0.7,
            max_tokens=None,
        ))
        assert len(result) == 2
        assert result[0].content == "hello"

    def test_unavailable_backend_raises(self):
        from apps.core.llm.streaming import stream_with_fallback

        backend = _make_backend(available=False)
        get_backend = MagicMock(return_value=backend)
        get_backends_by_priority = MagicMock(return_value=[("test", backend)])

        with pytest.raises(LLMBackendUnavailableError):
            list(stream_with_fallback(
                get_backend=get_backend,
                get_backends_by_priority=get_backends_by_priority,
                backend="test",
                fallback=True,
                messages=[],
                model=None,
                temperature=0.7,
                max_tokens=None,
            ))

    def test_stop_iteration_returns_empty(self):
        from apps.core.llm.streaming import stream_with_fallback

        backend = _make_backend(stream_chunks=[])
        # iter of empty list will raise StopIteration on next()
        backend.stream.return_value = iter([])

        get_backend = MagicMock(return_value=backend)
        get_backends_by_priority = MagicMock(return_value=[("test", backend)])

        result = list(stream_with_fallback(
            get_backend=get_backend,
            get_backends_by_priority=get_backends_by_priority,
            backend="test",
            fallback=True,
            messages=[],
            model=None,
            temperature=0.7,
            max_tokens=None,
        ))
        assert result == []

    def test_auth_error_raises_immediately(self):
        from apps.core.llm.streaming import stream_with_fallback

        backend = _make_backend()
        backend.stream.side_effect = LLMAuthenticationError(message="auth failed")

        get_backend = MagicMock(return_value=backend)
        get_backends_by_priority = MagicMock(return_value=[("test", backend)])

        with pytest.raises(LLMAuthenticationError):
            list(stream_with_fallback(
                get_backend=get_backend,
                get_backends_by_priority=get_backends_by_priority,
                backend="test",
                fallback=True,
                messages=[],
                model=None,
                temperature=0.7,
                max_tokens=None,
            ))


# ==================== fallback_policy.py ====================


class TestDiagnoseUnavailable:
    """Test _diagnose_unavailable."""

    def test_siliconflow_no_api_key(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = ""
        backend.default_model = "model"

        result = _diagnose_unavailable("siliconflow", backend)
        assert "API Key" in result

    def test_siliconflow_no_model(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = "key"
        backend.default_model = ""

        result = _diagnose_unavailable("siliconflow", backend)
        assert "默认模型" in result

    def test_siliconflow_both_present(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = "key"
        backend.default_model = "model"

        result = _diagnose_unavailable("siliconflow", backend)
        assert "is_available()" in result

    def test_ollama_no_base_url(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.base_url = ""

        result = _diagnose_unavailable("ollama", backend)
        assert "Base URL" in result

    def test_ollama_with_base_url(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.base_url = "http://localhost:11434"

        result = _diagnose_unavailable("ollama", backend)
        assert "is_available()" in result

    def test_openai_compatible_no_api_key(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = ""

        result = _diagnose_unavailable("openai_compatible", backend)
        assert "API Key" in result

    def test_openai_compatible_no_base_url(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = "key"
        backend.base_url = ""

        result = _diagnose_unavailable("openai_compatible", backend)
        assert "Base URL" in result

    def test_openai_compatible_no_model(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = "key"
        backend.base_url = "http://test"
        backend.default_model = ""

        result = _diagnose_unavailable("openai_compatible", backend)
        assert "默认模型" in result

    def test_openai_compatible_all_present(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = "key"
        backend.base_url = "http://test"
        backend.default_model = "model"

        result = _diagnose_unavailable("openai_compatible", backend)
        assert "is_available()" in result


class TestHandleCallError:
    """Test _handle_call_error."""

    def test_retriable_with_fallback(self):
        from apps.core.llm.fallback_policy import _handle_call_error

        errors = []
        _handle_call_error("test", LLMNetworkError(message="net"), True, errors)
        assert len(errors) == 1

    def test_retriable_without_fallback_raises(self):
        from apps.core.llm.fallback_policy import _handle_call_error

        errors = []
        exc = LLMNetworkError(message="net")
        try:
            try:
                raise exc
            except LLMNetworkError:
                _handle_call_error("test", exc, False, errors)
                pytest.fail("Should have re-raised")
        except LLMNetworkError:
            pass  # Expected

    def test_unknown_with_fallback(self):
        from apps.core.llm.fallback_policy import _handle_call_error

        errors = []
        _handle_call_error("test", RuntimeError("oops"), True, errors)
        assert len(errors) == 1

    def test_unknown_without_fallback_raises_api_error(self):
        from apps.core.llm.fallback_policy import _handle_call_error

        errors = []
        with pytest.raises(LLMAPIError):
            _handle_call_error("test", RuntimeError("oops"), False, errors)


class TestRaiseAllUnavailable:
    """Test _raise_all_unavailable."""

    def test_raises_backend_unavailable(self):
        from apps.core.llm.fallback_policy import _raise_all_unavailable

        errors = [("a", LLMAPIError(message="err"))]
        with pytest.raises(LLMBackendUnavailableError):
            _raise_all_unavailable(errors)

    def test_with_skipped(self):
        from apps.core.llm.fallback_policy import _raise_all_unavailable

        errors = [("a", LLMAPIError(message="err"))]
        skipped = [("b", "not available")]
        with pytest.raises(LLMBackendUnavailableError) as exc_info:
            _raise_all_unavailable(errors, skipped)
        assert "skipped" in str(exc_info.value.errors)


class TestResolveBackendsFromRouter:
    """Test _resolve_backends_from_router."""

    def test_with_specific_backend_no_fallback(self):
        from apps.core.llm.fallback_policy import _resolve_backends_from_router

        router = MagicMock()
        router.get_backend.return_value = "be"
        router.get_backends_by_priority.return_value = [("a", "ai"), ("b", "bi")]

        result = _resolve_backends_from_router(router, "a", False)
        assert result == [("a", "be")]

    def test_with_specific_backend_and_fallback(self):
        from apps.core.llm.fallback_policy import _resolve_backends_from_router

        router = MagicMock()
        router.get_backend.return_value = "be"
        router.get_backends_by_priority.return_value = [("a", "ai"), ("b", "bi")]

        result = _resolve_backends_from_router(router, "a", True)
        assert len(result) == 2

    def test_no_specific_backend(self):
        from apps.core.llm.fallback_policy import _resolve_backends_from_router

        router = MagicMock()
        router.get_backends_by_priority.return_value = [("a", "ai"), ("b", "bi")]

        result = _resolve_backends_from_router(router, None, True)
        assert result == [("a", "ai"), ("b", "bi")]


class TestLLMFallbackPolicyExecute:
    """Test LLMFallbackPolicy.execute."""

    def test_direct_backend_no_fallback(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        router = MagicMock()
        backend = MagicMock()
        router.get_backend.return_value = backend
        op = MagicMock(return_value="result")

        policy = LLMFallbackPolicy(router=router)
        result = policy.execute(operation=op, backend="test", fallback=False)
        assert result == "result"
        op.assert_called_once_with(backend)

    def test_fallback_to_second_backend(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b1 = MagicMock()
        b1.is_available.return_value = True
        b2 = MagicMock()
        b2.is_available.return_value = True

        router = MagicMock()
        router.get_backend.return_value = b1
        router.get_backends_by_priority.return_value = [("b1", b1), ("b2", b2)]

        op = MagicMock()
        op.side_effect = [LLMTimeoutError(message="timeout", timeout_seconds=30), "success"]

        policy = LLMFallbackPolicy(router=router)
        result = policy.execute(operation=op, backend="b1", fallback=True)
        assert result == "success"

    def test_all_backends_fail_raises(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b1 = MagicMock()
        b1.is_available.return_value = True

        router = MagicMock()
        router.get_backend.return_value = b1
        router.get_backends_by_priority.return_value = [("b1", b1)]

        op = MagicMock(side_effect=LLMNetworkError(message="net"))

        policy = LLMFallbackPolicy(router=router)
        with pytest.raises(LLMBackendUnavailableError):
            policy.execute(operation=op, backend="b1", fallback=True)

    def test_auth_error_propagates(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b1 = MagicMock()
        b1.is_available.return_value = True

        router = MagicMock()
        router.get_backend.return_value = b1
        router.get_backends_by_priority.return_value = [("b1", b1)]

        op = MagicMock(side_effect=LLMAuthenticationError(message="auth"))

        policy = LLMFallbackPolicy(router=router)
        with pytest.raises(LLMAuthenticationError):
            policy.execute(operation=op, backend="b1", fallback=True)

    def test_skipped_backend_not_tried(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b1 = MagicMock()
        b1.is_available.return_value = False
        b1.api_key = ""
        b1.base_url = "http://test"

        router = MagicMock()
        router.get_backend.return_value = b1
        router.get_backends_by_priority.return_value = [("b1", b1)]

        op = MagicMock()

        policy = LLMFallbackPolicy(router=router)
        with pytest.raises(LLMBackendUnavailableError):
            policy.execute(operation=op, backend="b1", fallback=True)
        op.assert_not_called()
