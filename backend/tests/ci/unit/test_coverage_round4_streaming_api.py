"""Coverage round 4: core/llm/streaming.py + core/api/ninja_llm_api.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.llm.exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMBackendUnavailableError,
    LLMNetworkError,
    LLMTimeoutError,
)


# ============================================================
# streaming.py – _resolve_backends
# ============================================================

class TestResolveBackends:
    def test_with_backend_no_fallback(self):
        from apps.core.llm.streaming import _resolve_backends
        mock_backend = MagicMock()
        def get_backend(name):
            return mock_backend
        def get_all():
            return [("b1", mock_backend), ("b2", MagicMock())]
        result = _resolve_backends(get_backend, get_all, "b1", False)
        assert len(result) == 1
        assert result[0][0] == "b1"

    def test_with_backend_and_fallback(self):
        from apps.core.llm.streaming import _resolve_backends
        b1 = MagicMock()
        b2 = MagicMock()
        def get_backend(name):
            return b1 if name == "b1" else b2
        def get_all():
            return [("b1", b1), ("b2", b2)]
        result = _resolve_backends(get_backend, get_all, "b1", True)
        assert len(result) == 2

    def test_no_backend(self):
        from apps.core.llm.streaming import _resolve_backends
        b1 = MagicMock()
        def get_backend(name):
            return b1
        def get_all():
            return [("b1", b1)]
        result = _resolve_backends(get_backend, get_all, None, False)
        assert len(result) == 1


# ============================================================
# streaming.py – _handle_stream_error
# ============================================================

class TestHandleStreamError:
    def test_retriable_error_with_fallback(self):
        from apps.core.llm.streaming import _handle_stream_error
        errors = []
        _handle_stream_error("b1", LLMTimeoutError("timeout"), True, errors)
        assert len(errors) == 1

    def test_retriable_error_no_fallback_raises(self):
        from apps.core.llm.streaming import _handle_stream_error
        errors = []
        try:
            raise LLMTimeoutError("timeout")
        except LLMTimeoutError:
            with pytest.raises(LLMTimeoutError):
                _handle_stream_error("b1", LLMTimeoutError("timeout"), False, errors)

    def test_network_error_with_fallback(self):
        from apps.core.llm.streaming import _handle_stream_error
        errors = []
        _handle_stream_error("b1", LLMNetworkError("net"), True, errors)
        assert len(errors) == 1

    def test_unknown_error_with_fallback(self):
        from apps.core.llm.streaming import _handle_stream_error
        errors = []
        _handle_stream_error("b1", RuntimeError("unknown"), True, errors)
        assert len(errors) == 1

    def test_unknown_error_no_fallback_raises_llm_api(self):
        from apps.core.llm.streaming import _handle_stream_error
        errors = []
        with pytest.raises(LLMAPIError):
            _handle_stream_error("b1", RuntimeError("unknown"), False, errors)


# ============================================================
# streaming.py – _build_stream_kwargs
# ============================================================

class TestBuildStreamKwargs:
    def test_basic(self):
        from apps.core.llm.streaming import _build_stream_kwargs
        result = _build_stream_kwargs([{"role": "user", "content": "hi"}], "model1", 0.7, 100)
        assert result["messages"] == [{"role": "user", "content": "hi"}]
        assert result["model"] == "model1"
        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 100

    def test_with_extra_kwargs(self):
        from apps.core.llm.streaming import _build_stream_kwargs
        result = _build_stream_kwargs([], None, 0.5, None, extra_kwargs={"custom": "val"})
        assert result["custom"] == "val"


# ============================================================
# streaming.py – stream_with_fallback
# ============================================================

class TestStreamWithFallback:
    def test_single_backend_no_fallback(self):
        from apps.core.llm.streaming import stream_with_fallback
        from apps.core.llm.backends import LLMStreamChunk
        mock_backend = MagicMock()
        mock_backend.stream.return_value = iter([LLMStreamChunk(content="hello")])
        def get_backend(name):
            return mock_backend
        def get_all():
            return [("b1", mock_backend)]
        chunks = list(stream_with_fallback(
            get_backend=get_backend, get_backends_by_priority=get_all,
            backend="b1", fallback=False, messages=[], model=None,
            temperature=0.5, max_tokens=None,
        ))
        assert len(chunks) == 1
        assert chunks[0].content == "hello"

    def test_fallback_tries_next(self):
        from apps.core.llm.streaming import stream_with_fallback
        from apps.core.llm.backends import LLMStreamChunk
        b1 = MagicMock()
        b1.is_available.return_value = True
        b1.stream.side_effect = LLMTimeoutError("timeout")
        b2 = MagicMock()
        b2.is_available.return_value = True
        b2.stream.return_value = iter([LLMStreamChunk(content="fallback")])
        def get_backend(name):
            return b1 if name == "b1" else b2
        def get_all():
            return [("b1", b1), ("b2", b2)]
        with patch("apps.core.llm.fallback_policy._diagnose_unavailable", return_value="not ready"):
            chunks = list(stream_with_fallback(
                get_backend=get_backend, get_backends_by_priority=get_all,
                backend="b1", fallback=True, messages=[], model=None,
                temperature=0.5, max_tokens=None,
            ))
        assert len(chunks) == 1
        assert chunks[0].content == "fallback"

    def test_all_backends_fail_raises(self):
        from apps.core.llm.streaming import stream_with_fallback
        b1 = MagicMock()
        b1.is_available.return_value = True
        b1.stream.side_effect = LLMTimeoutError("timeout")
        b2 = MagicMock()
        b2.is_available.return_value = True
        b2.stream.side_effect = LLMNetworkError("net")
        def get_backend(name):
            return b1 if name == "b1" else b2
        def get_all():
            return [("b1", b1), ("b2", b2)]
        with patch("apps.core.llm.fallback_policy._diagnose_unavailable", return_value="not ready"):
            with pytest.raises(LLMBackendUnavailableError):
                list(stream_with_fallback(
                    get_backend=get_backend, get_backends_by_priority=get_all,
                    backend=None, fallback=True, messages=[], model=None,
                    temperature=0.5, max_tokens=None,
                ))

    def test_unavailable_backend_skipped(self):
        from apps.core.llm.streaming import stream_with_fallback
        from apps.core.llm.backends import LLMStreamChunk
        b1 = MagicMock()
        b1.is_available.return_value = False
        b2 = MagicMock()
        b2.is_available.return_value = True
        b2.stream.return_value = iter([LLMStreamChunk(content="ok")])
        def get_backend(name):
            return b1 if name == "b1" else b2
        def get_all():
            return [("b1", b1), ("b2", b2)]
        with patch("apps.core.llm.fallback_policy._diagnose_unavailable", return_value="not ready"):
            chunks = list(stream_with_fallback(
                get_backend=get_backend, get_backends_by_priority=get_all,
                backend=None, fallback=True, messages=[], model=None,
                temperature=0.5, max_tokens=None,
            ))
        assert len(chunks) == 1

    def test_auth_error_reraised(self):
        from apps.core.llm.streaming import stream_with_fallback
        b1 = MagicMock()
        b1.is_available.return_value = True
        b1.stream.side_effect = LLMAuthenticationError("auth fail")
        def get_backend(name):
            return b1
        def get_all():
            return [("b1", b1)]
        with pytest.raises(LLMAuthenticationError):
            list(stream_with_fallback(
                get_backend=get_backend, get_backends_by_priority=get_all,
                backend=None, fallback=True, messages=[], model=None,
                temperature=0.5, max_tokens=None,
            ))

    def test_empty_iterator_returns(self):
        from apps.core.llm.streaming import stream_with_fallback
        b1 = MagicMock()
        b1.is_available.return_value = True
        b1.stream.return_value = iter([])
        def get_backend(name):
            return b1
        def get_all():
            return [("b1", b1)]
        with patch("apps.core.llm.fallback_policy._diagnose_unavailable", return_value="not ready"):
            chunks = list(stream_with_fallback(
                get_backend=get_backend, get_backends_by_priority=get_all,
                backend=None, fallback=True, messages=[], model=None,
                temperature=0.5, max_tokens=None,
            ))
        assert chunks == []


# ============================================================
# ninja_llm_api.py – Schema classes
# ============================================================

class TestNinjaSchemas:
    def test_chat_request(self):
        from apps.core.api.ninja_llm_api import ChatRequest
        req = ChatRequest(message="hello", session_id="s1")
        assert req.message == "hello"
        assert req.session_id == "s1"
        assert req.system_prompt is None

    def test_chat_response(self):
        from apps.core.api.ninja_llm_api import ChatResponse
        resp = ChatResponse(response="hi", session_id="s1")
        assert resp.response == "hi"

    def test_conversation_message(self):
        from apps.core.api.ninja_llm_api import ConversationMessage
        msg = ConversationMessage(role="user", content="hello", created_at="2024-01-01")
        assert msg.role == "user"

    def test_model_info(self):
        from apps.core.api.ninja_llm_api import ModelInfo
        info = ModelInfo(id="gpt-4", name="GPT-4", backend="openai")
        assert info.id == "gpt-4"
        assert info.context_window == 0

    def test_model_list_response(self):
        from apps.core.api.ninja_llm_api import ModelListResponse
        resp = ModelListResponse(models=[])
        assert resp.models == []


# ============================================================
# ninja_llm_api.py – sync_prompt_templates_impl
# ============================================================

class TestSyncPromptTemplatesImpl:
    def test_delegates_to_service(self):
        from apps.core.api.ninja_llm_api import sync_prompt_templates_impl
        with patch("apps.core.services.prompt_template_service.sync_prompt_templates") as mock_sync:
            mock_sync.return_value = {"synced_count": 5}
            result = sync_prompt_templates_impl(overwrite=True)
        assert result["synced_count"] == 5


# ============================================================
# ninja_llm_api.py – endpoint functions
# ============================================================

class TestNinjaLlmEndpoints:
    def test_list_available_models(self):
        from apps.core.api.ninja_llm_api import list_available_models
        mock_request = MagicMock()
        with patch("apps.core.llm.model_list_service.ModelListService") as MockService:
            with patch("apps.core.llm.config.LLMConfig") as MockConfig:
                mock_service = MagicMock()
                mock_service.get_result.return_value = MagicMock(models=[
                    {"id": "model-a", "name": "Model A"},
                    {"id": "model-b", "name": ""},
                ])
                MockService.return_value = mock_service
                MockConfig.get_openai_compatible_model.return_value = "model-a"
                MockConfig.resolve_backend_for_model.return_value = "openai"
                result = list_available_models(mock_request)
        assert len(result.models) >= 1

    def test_list_available_models_no_default(self):
        from apps.core.api.ninja_llm_api import list_available_models
        mock_request = MagicMock()
        with patch("apps.core.llm.model_list_service.ModelListService") as MockService:
            with patch("apps.core.llm.config.LLMConfig") as MockConfig:
                mock_service = MagicMock()
                mock_service.get_result.return_value = MagicMock(models=[
                    {"id": "model-x", "name": "Model X"},
                ])
                MockService.return_value = mock_service
                MockConfig.get_openai_compatible_model.return_value = ""
                MockConfig.resolve_backend_for_model.return_value = "ollama"
                result = list_available_models(mock_request)
        assert len(result.models) >= 1

    def test_test_model_connection_not_admin(self):
        from apps.core.api.ninja_llm_api import test_model_connection
        from apps.core.exceptions import PermissionDenied
        mock_request = MagicMock()
        mock_request.user.is_staff = False
        mock_request.user.is_superuser = False
        with pytest.raises(PermissionDenied):
            test_model_connection(mock_request, model_id="gpt-4")

    def test_test_model_connection_empty_model(self):
        from apps.core.api.ninja_llm_api import test_model_connection
        mock_request = MagicMock()
        mock_request.user.is_staff = True
        mock_request.user.is_superuser = False
        result = test_model_connection(mock_request, model_id="")
        assert result["ok"] is False

    def test_test_model_connection_success(self):
        from apps.core.api.ninja_llm_api import test_model_connection
        mock_request = MagicMock()
        mock_request.user.is_staff = True
        mock_request.user.is_superuser = False
        with patch("apps.core.llm.service.get_llm_service") as mock_get:
            mock_service = MagicMock()
            mock_resp = MagicMock()
            mock_resp.model = "gpt-4"
            mock_resp.backend = "openai"
            mock_service.chat.return_value = mock_resp
            mock_get.return_value = mock_service
            result = test_model_connection(mock_request, model_id="gpt-4")
        assert result["ok"] is True
        assert result["model"] == "gpt-4"

    def test_test_model_connection_failure(self):
        from apps.core.api.ninja_llm_api import test_model_connection
        mock_request = MagicMock()
        mock_request.user.is_staff = True
        mock_request.user.is_superuser = False
        with patch("apps.core.llm.service.get_llm_service") as mock_get:
            mock_service = MagicMock()
            mock_service.chat.side_effect = RuntimeError("connection refused")
            mock_get.return_value = mock_service
            result = test_model_connection(mock_request, model_id="gpt-4")
        assert result["ok"] is False
        assert "connection refused" in result["error"]

    def test_sync_prompt_templates_not_admin(self):
        from apps.core.api.ninja_llm_api import sync_prompt_templates
        from apps.core.exceptions import PermissionDenied
        mock_request = MagicMock()
        mock_request.user = MagicMock()
        mock_request.user.is_authenticated = True
        mock_request.user.is_superuser = False
        mock_request.user.is_staff = False
        mock_request.auth = mock_request.user
        with pytest.raises(PermissionDenied):
            sync_prompt_templates(mock_request)

    def test_conversation_history_admin_path(self):
        from apps.core.api.ninja_llm_api import get_conversation_history
        mock_request = MagicMock()
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 1
        mock_user.is_admin = False
        mock_user.is_superuser = True
        mock_user.is_staff = False
        mock_request.user = mock_user
        mock_request.auth = mock_user
        with patch("apps.core.api.ninja_llm_api.get_conversation_history_impl") as mock_impl:
            mock_impl.return_value = {"messages": [{"role": "user", "content": "hi", "created_at": "2024-01-01", "metadata": {}}]}
            result = get_conversation_history(mock_request, "session1")
        assert result.session_id == "session1"
        mock_impl.assert_called_once_with(session_id="session1", user_id=None, limit=50)

    def test_conversation_history_user_path(self):
        from apps.core.api.ninja_llm_api import get_conversation_history
        mock_request = MagicMock()
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 42
        mock_user.is_admin = False
        mock_user.is_superuser = False
        mock_user.is_staff = False
        mock_request.user = mock_user
        mock_request.auth = mock_user
        with patch("apps.core.api.ninja_llm_api.get_conversation_history_impl") as mock_impl:
            mock_impl.return_value = {"messages": []}
            result = get_conversation_history(mock_request, "session1")
        mock_impl.assert_called_once_with(session_id="session1", user_id="42", limit=50)


# ============================================================
# streaming.py – async stream_with_fallback
# ============================================================

class TestAstreamWithFallback:
    @pytest.mark.asyncio
    async def test_single_backend_no_fallback(self):
        from apps.core.llm.streaming import astream_with_fallback
        from apps.core.llm.backends import LLMStreamChunk

        async def async_gen():
            yield LLMStreamChunk(content="async_hello")

        mock_backend = MagicMock()
        mock_backend.astream.return_value = async_gen()
        def get_backend(name):
            return mock_backend
        def get_all():
            return [("b1", mock_backend)]
        chunks = []
        async for chunk in astream_with_fallback(
            get_backend=get_backend, get_backends_by_priority=get_all,
            backend="b1", fallback=False, messages=[], model=None,
            temperature=0.5, max_tokens=None,
        ):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert chunks[0].content == "async_hello"

    @pytest.mark.asyncio
    async def test_auth_error_reraised_async(self):
        from apps.core.llm.streaming import astream_with_fallback

        async def raise_auth():
            raise LLMAuthenticationError("auth fail")
            yield  # pragma: no cover

        b1 = MagicMock()
        b1.is_available.return_value = True
        b1.astream.return_value = raise_auth()
        def get_backend(name):
            return b1
        def get_all():
            return [("b1", b1)]
        with pytest.raises(LLMAuthenticationError):
            async for _ in astream_with_fallback(
                get_backend=get_backend, get_backends_by_priority=get_all,
                backend=None, fallback=True, messages=[], model=None,
                temperature=0.5, max_tokens=None,
            ):
                pass

    @pytest.mark.asyncio
    async def test_fallback_tries_next_async(self):
        from apps.core.llm.streaming import astream_with_fallback
        from apps.core.llm.backends import LLMStreamChunk

        async def raise_timeout():
            raise LLMTimeoutError("timeout")
            yield  # pragma: no cover

        async def gen_ok():
            yield LLMStreamChunk(content="ok")

        b1 = MagicMock()
        b1.is_available.return_value = True
        b1.astream.return_value = raise_timeout()
        b2 = MagicMock()
        b2.is_available.return_value = True
        b2.astream.return_value = gen_ok()
        def get_backend(name):
            return b1 if name == "b1" else b2
        def get_all():
            return [("b1", b1), ("b2", b2)]
        with patch("apps.core.llm.fallback_policy._diagnose_unavailable", return_value="not ready"):
            chunks = []
            async for chunk in astream_with_fallback(
                get_backend=get_backend, get_backends_by_priority=get_all,
                backend=None, fallback=True, messages=[], model=None,
                temperature=0.5, max_tokens=None,
            ):
                chunks.append(chunk)
        assert len(chunks) == 1
        assert chunks[0].content == "ok"

    @pytest.mark.asyncio
    async def test_empty_async_iterator(self):
        from apps.core.llm.streaming import astream_with_fallback

        async def empty():
            return
            yield  # pragma: no cover

        b1 = MagicMock()
        b1.is_available.return_value = True
        b1.astream.return_value = empty()
        def get_backend(name):
            return b1
        def get_all():
            return [("b1", b1)]
        with patch("apps.core.llm.fallback_policy._diagnose_unavailable", return_value="not ready"):
            chunks = []
            async for chunk in astream_with_fallback(
                get_backend=get_backend, get_backends_by_priority=get_all,
                backend=None, fallback=True, messages=[], model=None,
                temperature=0.5, max_tokens=None,
            ):
                chunks.append(chunk)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_all_fail_async(self):
        from apps.core.llm.streaming import astream_with_fallback

        async def raise_timeout():
            raise LLMTimeoutError("timeout")
            yield  # pragma: no cover

        b1 = MagicMock()
        b1.is_available.return_value = True
        b1.astream.return_value = raise_timeout()
        def get_backend(name):
            return b1
        def get_all():
            return [("b1", b1)]
        with patch("apps.core.llm.fallback_policy._diagnose_unavailable", return_value="not ready"):
            with pytest.raises(LLMBackendUnavailableError):
                async for _ in astream_with_fallback(
                    get_backend=get_backend, get_backends_by_priority=get_all,
                    backend=None, fallback=True, messages=[], model=None,
                    temperature=0.5, max_tokens=None,
                ):
                    pass

    @pytest.mark.asyncio
    async def test_unavailable_skipped_async(self):
        from apps.core.llm.streaming import astream_with_fallback
        from apps.core.llm.backends import LLMStreamChunk

        async def gen_ok():
            yield LLMStreamChunk(content="ok")

        b1 = MagicMock()
        b1.is_available.return_value = False
        b2 = MagicMock()
        b2.is_available.return_value = True
        b2.astream.return_value = gen_ok()
        def get_backend(name):
            return b1 if name == "b1" else b2
        def get_all():
            return [("b1", b1), ("b2", b2)]
        with patch("apps.core.llm.fallback_policy._diagnose_unavailable", return_value="not ready"):
            chunks = []
            async for chunk in astream_with_fallback(
                get_backend=get_backend, get_backends_by_priority=get_all,
                backend=None, fallback=True, messages=[], model=None,
                temperature=0.5, max_tokens=None,
            ):
                chunks.append(chunk)
        assert len(chunks) == 1
