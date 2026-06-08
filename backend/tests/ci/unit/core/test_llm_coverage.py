"""core/llm 模块单元测试（fallback_policy, streaming）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from apps.core.llm.fallback_policy import (
    LLMFallbackPolicy,
    _diagnose_unavailable,
    _handle_call_error,
    _raise_all_unavailable,
    _resolve_backends_from_router,
)
from apps.core.llm.streaming import (
    _build_stream_kwargs,
    _handle_stream_error,
    _resolve_backends,
)
from apps.core.llm.exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMBackendUnavailableError,
    LLMNetworkError,
    LLMTimeoutError,
)


class TestResolveBackendsFromRouter:
    def test_with_backend_no_fallback(self) -> None:
        router = MagicMock()
        backend_mock = MagicMock()
        router.get_backend.return_value = backend_mock
        result = _resolve_backends_from_router(router, "a", fallback=False)
        assert len(result) == 1
        assert result[0] == ("a", backend_mock)

    def test_with_backend_and_fallback(self) -> None:
        router = MagicMock()
        b1, b2 = MagicMock(), MagicMock()
        router.get_backend.return_value = b1
        router.get_backends_by_priority.return_value = [("a", b1), ("b", b2)]
        result = _resolve_backends_from_router(router, "a", fallback=True)
        assert len(result) == 2
        assert result[1] == ("b", b2)

    def test_no_backend(self) -> None:
        router = MagicMock()
        router.get_backends_by_priority.return_value = [("a", MagicMock())]
        result = _resolve_backends_from_router(router, None, fallback=True)
        assert len(result) == 1


class TestHandleCallError:
    def test_retriable_error_with_fallback(self) -> None:
        errors: list = []
        _handle_call_error("a", LLMTimeoutError("timeout"), True, errors)
        assert len(errors) == 1

    def test_retriable_error_without_fallback_raises(self) -> None:
        errors: list = []
        with pytest.raises(LLMTimeoutError):
            try:
                raise LLMTimeoutError("timeout")
            except LLMTimeoutError as e:
                _handle_call_error("a", e, False, errors)

    def test_non_retriable_without_fallback_raises_api_error(self) -> None:
        errors: list = []
        with pytest.raises(LLMAPIError):
            _handle_call_error("a", ValueError("oops"), False, errors)


class TestRaiseAllUnavailable:
    def test_raises_backend_unavailable(self) -> None:
        with pytest.raises(LLMBackendUnavailableError):
            _raise_all_unavailable([("a", Exception("e"))])


class TestDiagnoseUnavailable:
    def test_siliconflow_no_api_key(self) -> None:
        backend = MagicMock()
        backend.api_key = ""
        result = _diagnose_unavailable("siliconflow", backend)
        assert "API Key" in result

    def test_siliconflow_with_key_no_model(self) -> None:
        backend = MagicMock()
        backend.api_key = "key123"  # allowlist secret
        backend.default_model = ""
        result = _diagnose_unavailable("siliconflow", backend)
        assert "默认模型" in result

    def test_ollama_no_base_url(self) -> None:
        backend = MagicMock()
        backend.base_url = ""
        result = _diagnose_unavailable("ollama", backend)
        assert "Base URL" in result

    def test_generic_no_api_key(self) -> None:
        backend = MagicMock(spec=[])
        backend.api_key = None
        result = _diagnose_unavailable("openai", backend)
        assert "API Key" in result


class TestLLMFallbackPolicy:
    def test_execute_no_fallback(self) -> None:
        router = MagicMock()
        backend_mock = MagicMock()
        router.get_backend.return_value = backend_mock
        policy = LLMFallbackPolicy(router=router)
        op = MagicMock(return_value="result")
        result = policy.execute(operation=op, backend="a", fallback=False)
        assert result == "result"
        op.assert_called_once_with(backend_mock)

    def test_execute_with_fallback_success(self) -> None:
        router = MagicMock()
        b1 = MagicMock()
        b1.is_available.return_value = True
        router.get_backends_by_priority.return_value = [("a", b1)]
        policy = LLMFallbackPolicy(router=router)
        op = MagicMock(return_value="ok")
        result = policy.execute(operation=op, fallback=True)
        assert result == "ok"

    def test_execute_skips_unavailable(self) -> None:
        router = MagicMock()
        b1 = MagicMock()
        b1.is_available.return_value = False
        b1.api_key = "k"
        b1.default_model = "m"
        b2 = MagicMock()
        b2.is_available.return_value = True
        router.get_backends_by_priority.return_value = [("a", b1), ("b", b2)]
        policy = LLMFallbackPolicy(router=router)
        op = MagicMock(return_value="ok")
        result = policy.execute(operation=op, fallback=True)
        assert result == "ok"


class TestStreamingHelpers:
    def test_resolve_backends_with_backend(self) -> None:
        get_backend = MagicMock(return_value=MagicMock())
        get_backends = MagicMock(return_value=[("a", MagicMock())])
        result = _resolve_backends(get_backend, get_backends, "a", fallback=False)
        assert len(result) == 1

    def test_resolve_backends_no_backend(self) -> None:
        get_backend = MagicMock()
        get_backends = MagicMock(return_value=[("a", MagicMock())])
        result = _resolve_backends(get_backend, get_backends, None, fallback=True)
        assert len(result) == 1

    def test_build_stream_kwargs_basic(self) -> None:
        result = _build_stream_kwargs(["msg"], "model", 0.7, 100)
        assert result["messages"] == ["msg"]
        assert result["model"] == "model"
        assert result["temperature"] == 0.7

    def test_build_stream_kwargs_with_extra(self) -> None:
        result = _build_stream_kwargs(["msg"], "m", 0.5, 50, {"extra": "val"})
        assert result["extra"] == "val"

    def test_handle_stream_error_retriable_with_fallback(self) -> None:
        errors: list = []
        _handle_stream_error("a", LLMTimeoutError("t"), True, errors)
        assert len(errors) == 1

    def test_handle_stream_error_non_retriable_no_fallback(self) -> None:
        errors: list = []
        with pytest.raises(LLMAPIError):
            _handle_stream_error("a", ValueError("v"), False, errors)

    def test_handle_stream_error_retriable_no_fallback_raises(self) -> None:
        errors: list = []
        with pytest.raises(LLMTimeoutError):
            try:
                raise LLMTimeoutError("timeout")
            except LLMTimeoutError as e:
                _handle_stream_error("a", e, False, errors)
