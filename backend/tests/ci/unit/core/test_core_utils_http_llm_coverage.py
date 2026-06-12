"""
Tests for core/utils/path.py, core/http/httpx_clients.py, core/llm/fallback_policy.py,
core/exceptions/error_codes.py.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path as StdPath
from unittest.mock import MagicMock, patch

import pytest

from apps.core.utils.path import Path


class TestCorePath:
    def test_abspath(self, tmp_path):
        p = Path(str(tmp_path / "file.txt"))
        result = p.abspath()
        assert os.path.isabs(result)

    def test_ext(self):
        p = Path("/tmp/test.txt")
        assert p.ext == ".txt"

    def test_ext_no_extension(self):
        p = Path("/tmp/noext")
        assert p.ext == ""

    def test_dirname(self):
        p = Path("/tmp/subdir/file.txt")
        d = p.dirname()
        assert str(d).endswith("subdir")

    def test_isdir(self, tmp_path):
        p = Path(str(tmp_path))
        assert p.isdir() is True
        f = tmp_path / "file.txt"
        f.write_bytes(b"x")
        assert Path(str(f)).isdir() is False

    def test_makedirs_p(self, tmp_path):
        target = tmp_path / "a" / "b" / "c"
        p = Path(str(target))
        result = p.makedirs_p()
        assert target.exists()
        assert result is p

    def test_remove_p_existing(self, tmp_path):
        f = tmp_path / "to_delete.txt"
        f.write_bytes(b"delete me")
        p = Path(str(f))
        result = p.remove_p()
        assert not f.exists()
        assert result is p

    def test_remove_p_nonexistent(self, tmp_path):
        p = Path(str(tmp_path / "nonexistent.txt"))
        result = p.remove_p()  # Should not raise
        assert result is p

    def test_text(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        p = Path(str(f))
        assert p.text() == "hello world"

    def test_write_text(self, tmp_path):
        f = tmp_path / "write_test.txt"
        p = Path(str(f))
        result = p.write_text("content")
        assert result is p
        assert f.read_text() == "content"

    def test_write_bytes(self, tmp_path):
        f = tmp_path / "write_bytes.bin"
        p = Path(str(f))
        result = p.write_bytes(b"\x00\x01\x02")
        assert result is p
        assert f.read_bytes() == b"\x00\x01\x02"

    def test_bytes(self, tmp_path):
        f = tmp_path / "read_bytes.bin"
        f.write_bytes(b"\xff\xfe")
        p = Path(str(f))
        assert p.bytes() == b"\xff\xfe"

    def test_walkfiles(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.txt").write_text("c")
        p = Path(str(tmp_path))
        files = list(p.walkfiles("*.txt"))
        names = {f.name for f in files}
        assert "a.txt" in names
        assert "c.txt" in names

    def test_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.pdf").write_bytes(b"%PDF")
        p = Path(str(tmp_path))
        txt_files = p.files("*.txt")
        assert len(txt_files) == 1
        assert txt_files[0].name == "a.txt"

    def test_dirs(self, tmp_path):
        (tmp_path / "d1").mkdir()
        (tmp_path / "d2").mkdir()
        (tmp_path / "f.txt").write_text("x")
        p = Path(str(tmp_path))
        dirs = p.dirs()
        dir_names = {d.name for d in dirs}
        assert "d1" in dir_names
        assert "d2" in dir_names


class TestHttpxClients:
    def test_get_sync_http_client(self):
        from apps.core.http.httpx_clients import get_sync_http_client

        client = get_sync_http_client()
        assert client is not None
        # Verify it's cached (same instance)
        client2 = get_sync_http_client()
        assert client is client2

    def test_get_async_http_client(self):
        from apps.core.http.httpx_clients import get_async_http_client

        client = get_async_http_client()
        assert client is not None
        client2 = get_async_http_client()
        assert client is client2

    def test_httpx_event_hooks_disabled(self):
        from apps.core.http.httpx_clients import _httpx_event_hooks

        with patch.dict(os.environ, {"DJANGO_HTTPX_METRICS": ""}):
            # Clear the lru_cache to pick up env change
            from apps.core.http.httpx_clients import get_sync_http_client

            result = _httpx_event_hooks()
            assert result is None

    def test_httpx_event_hooks_enabled(self):
        from apps.core.http.httpx_clients import _httpx_event_hooks

        with patch.dict(os.environ, {"DJANGO_HTTPX_METRICS": "true"}):
            result = _httpx_event_hooks()
            assert result is not None
            assert "request" in result
            assert "response" in result
            assert len(result["request"]) == 1
            assert len(result["response"]) == 1


class TestFallbackPolicy:
    def _make_backend(self, available=True, name="test"):
        backend = MagicMock()
        backend.is_available.return_value = available
        backend.api_key = "key"
        backend.base_url = "http://localhost"
        backend.default_model = "model"
        return backend

    def test_execute_specific_backend_no_fallback(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.router import LLMBackendRouter

        backend = self._make_backend()
        router = MagicMock(spec=LLMBackendRouter)
        router.get_backend.return_value = backend

        policy = LLMFallbackPolicy(router=router)
        op = MagicMock(return_value="result")
        result = policy.execute(operation=op, backend="test", fallback=False)
        assert result == "result"
        op.assert_called_once_with(backend)

    def test_execute_with_fallback_first_succeeds(self):
        from apps.core.llm.exceptions import LLMBackendUnavailableError
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.router import LLMBackendRouter

        b1 = self._make_backend(available=True, name="b1")
        b2 = self._make_backend(available=True, name="b2")
        router = MagicMock(spec=LLMBackendRouter)
        router.get_backend.return_value = b1
        router.get_backends_by_priority.return_value = [("b1", b1), ("b2", b2)]

        policy = LLMFallbackPolicy(router=router)
        op = MagicMock(return_value="ok")
        result = policy.execute(operation=op, backend="b1", fallback=True)
        assert result == "ok"

    def test_execute_all_unavailable_raises(self):
        from apps.core.llm.exceptions import LLMBackendUnavailableError
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.router import LLMBackendRouter

        b1 = self._make_backend(available=False)
        router = MagicMock(spec=LLMBackendRouter)
        router.get_backends_by_priority.return_value = [("b1", b1)]

        policy = LLMFallbackPolicy(router=router)
        op = MagicMock()
        with pytest.raises(LLMBackendUnavailableError):
            policy.execute(operation=op)

    def test_execute_auth_error_propagates(self):
        from apps.core.llm.exceptions import LLMAuthenticationError
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.router import LLMBackendRouter

        b1 = self._make_backend(available=True)
        router = MagicMock(spec=LLMBackendRouter)
        router.get_backends_by_priority.return_value = [("b1", b1)]

        policy = LLMFallbackPolicy(router=router)
        op = MagicMock(side_effect=LLMAuthenticationError(message="auth fail"))
        with pytest.raises(LLMAuthenticationError):
            policy.execute(operation=op)

    def test_diagnose_unavailable_openai_compatible_no_key(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = ""
        backend.default_model = "model"
        result = _diagnose_unavailable("openai_compatible", backend)
        assert "API Key" in result

    def test_diagnose_unavailable_openai_compatible_no_model(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = "key"
        backend.default_model = ""
        result = _diagnose_unavailable("openai_compatible", backend)
        assert "默认模型" in result

    def test_diagnose_unavailable_openai_compatible_ok(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = "key"
        backend.default_model = "model"
        result = _diagnose_unavailable("openai_compatible", backend)
        assert "is_available" in result

    def test_diagnose_unavailable_ollama_no_url(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.base_url = ""
        result = _diagnose_unavailable("ollama", backend)
        assert "Base URL" in result

    def test_diagnose_unavailable_ollama_ok(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.base_url = "http://localhost:11434"
        result = _diagnose_unavailable("ollama", backend)
        assert "is_available" in result

    def test_diagnose_unavailable_openai_compatible(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = "key"
        backend.base_url = "http://localhost"
        backend.default_model = "gpt-4"
        result = _diagnose_unavailable("openai", backend)
        assert "is_available" in result

    def test_diagnose_unavailable_openai_no_key(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock()
        backend.api_key = ""
        backend.base_url = "http://localhost"
        backend.default_model = "gpt-4"
        result = _diagnose_unavailable("openai", backend)
        assert "API Key" in result

    def test_diagnose_unavailable_generic_no_key(self):
        from apps.core.llm.fallback_policy import _diagnose_unavailable

        backend = MagicMock(spec=[])  # No api_key attr
        result = _diagnose_unavailable("custom_backend", backend)
        assert "API Key" in result

    def test_handle_call_error_retriable_no_fallback_raises(self):
        from apps.core.llm.exceptions import LLMAPIError
        from apps.core.llm.fallback_policy import _handle_call_error

        errors = []
        with pytest.raises((LLMAPIError, Exception)):
            _handle_call_error("b1", LLMAPIError(message="api err"), fallback=False, errors=errors)

    def test_handle_call_error_non_retriable_no_fallback_raises(self):
        from apps.core.llm.exceptions import LLMAPIError
        from apps.core.llm.fallback_policy import _handle_call_error

        errors = []
        with pytest.raises(LLMAPIError):
            _handle_call_error("b1", RuntimeError("unknown"), fallback=False, errors=errors)

    def test_handle_call_error_with_fallback_continues(self):
        from apps.core.llm.exceptions import LLMTimeoutError
        from apps.core.llm.fallback_policy import _handle_call_error

        errors = []
        _handle_call_error("b1", LLMTimeoutError(message="timeout"), fallback=True, errors=errors)
        assert len(errors) == 1

    def test_raise_all_unavailable_with_skipped(self):
        from apps.core.llm.exceptions import LLMBackendUnavailableError
        from apps.core.llm.fallback_policy import _raise_all_unavailable

        errors = [("b1", RuntimeError("err"))]
        skipped = [("b2", "no api key")]
        with pytest.raises(LLMBackendUnavailableError):
            _raise_all_unavailable(errors, skipped)

    def test_resolve_backends_no_backend_no_fallback(self):
        from apps.core.llm.fallback_policy import _resolve_backends_from_router
        from apps.core.llm.router import LLMBackendRouter

        router = MagicMock(spec=LLMBackendRouter)
        router.get_backends_by_priority.return_value = [("b1", MagicMock())]
        result = _resolve_backends_from_router(router, backend=None, fallback=False)
        assert len(result) == 1

    def test_resolve_backends_specific_with_fallback(self):
        from apps.core.llm.fallback_policy import _resolve_backends_from_router
        from apps.core.llm.router import LLMBackendRouter

        b1 = MagicMock()
        b2 = MagicMock()
        router = MagicMock(spec=LLMBackendRouter)
        router.get_backend.return_value = b1
        router.get_backends_by_priority.return_value = [("b1", b1), ("b2", b2)]
        result = _resolve_backends_from_router(router, backend="b1", fallback=True)
        assert len(result) == 2


class TestErrorCodes:
    def test_error_codes_exist(self):
        from apps.core.exceptions.error_codes import (
            CASE_NOT_FOUND,
            CHAT_CREATION_FAILED,
            CONTRACT_GENERATION_FAILED,
            FILE_CONVERSION_FAILED,
            FILING_NUMBER_GENERATION_FAILED,
            MESSAGE_SEND_FAILED,
            PDF_MERGE_FAILED,
            REQUEST_ERROR,
            SMS_SUBMIT_FAILED,
            SYSTEM_ERROR,
            TEMPLATE_RENDER_ERROR,
            TEXT_EXTRACTION_FAILED,
        )

        # Verify they are all non-empty strings
        for code in [
            TEMPLATE_RENDER_ERROR,
            PDF_MERGE_FAILED,
            FILE_CONVERSION_FAILED,
            CONTRACT_GENERATION_FAILED,
            FILING_NUMBER_GENERATION_FAILED,
            CHAT_CREATION_FAILED,
            MESSAGE_SEND_FAILED,
            SYSTEM_ERROR,
            SMS_SUBMIT_FAILED,
            CASE_NOT_FOUND,
            TEXT_EXTRACTION_FAILED,
            REQUEST_ERROR,
        ]:
            assert isinstance(code, str)
            assert len(code) > 0
