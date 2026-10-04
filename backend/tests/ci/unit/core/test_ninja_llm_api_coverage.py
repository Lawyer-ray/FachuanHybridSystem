"""apps/core/api/ninja_llm_api.py 端点单元测试。

通过 RequestFactory 构造请求并直接调用端点函数（绕过 HTTP 层与鉴权装饰器），
符合 tests/ci/unit/test_cloud_storage_auth_api.py 的既有范式。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import async_to_sync
from django.test import RequestFactory

from apps.core.api.ninja_llm_api import (
    ChatRequest,
    chat_with_context,
    chat_with_context_stream,
    get_conversation_history,
    list_available_models,
    sync_prompt_templates,
)
from apps.core.api.ninja_llm_api import test_model_connection as llm_model_connection
from apps.core.exceptions import PermissionDenied

_REQUEST_FACTORY = RequestFactory()
_USER_SEQ = iter(range(910_000, 999_999))


class _FakeUser:
    """轻量用户对象：满足限流 key 与端点内 getattr 访问。"""

    def __init__(self, *, is_admin: bool = False, is_superuser: bool = False) -> None:
        self.id = next(_USER_SEQ)
        self.is_authenticated = True
        self.is_admin = is_admin
        self.is_superuser = is_superuser


def _post_request(user: Any = None, path: str = "/api/v1/core/llm/chat") -> Any:
    request = _REQUEST_FACTORY.post(path, data="{}", content_type="application/json")
    request.user = user
    return request


def _get_request(user: Any = None, path: str = "/api/v1/core/llm/models") -> Any:
    request = _REQUEST_FACTORY.get(path)
    request.user = user
    return request


class TestChatWithContext:
    @pytest.mark.django_db
    def test_returns_response_and_session(self) -> None:
        user = _FakeUser()
        request = _post_request(user)
        payload = ChatRequest(message="你好", session_id="s-1", system_prompt="sp")

        with patch(
            "apps.core.api.ninja_llm_api.achat_with_context_impl",
            new_callable=AsyncMock,
            return_value={"response": "回答内容", "session_id": "s-1"},
        ) as mock_impl:
            result = async_to_sync(chat_with_context)(request, payload)

        assert result.response == "回答内容"
        assert result.session_id == "s-1"
        mock_impl.assert_awaited_once()
        kwargs = mock_impl.await_args.kwargs
        assert kwargs["message"] == "你好"
        assert kwargs["session_id"] == "s-1"
        assert kwargs["user_id"] == str(user.id)
        assert kwargs["system_prompt"] == "sp"

    @pytest.mark.django_db
    def test_fallback_to_request_auth_user(self) -> None:
        """request.user 未认证时回退 request.auth 取 user_id。"""
        anon = MagicMock()
        anon.is_authenticated = False
        request = _post_request(anon)
        auth_user = _FakeUser()
        request.auth = auth_user

        payload = ChatRequest(message="hi")

        with patch(
            "apps.core.api.ninja_llm_api.achat_with_context_impl",
            new_callable=AsyncMock,
            return_value={"response": "r", "session_id": "s-2"},
        ) as mock_impl:
            result = async_to_sync(chat_with_context)(request, payload)

        assert result.session_id == "s-2"
        assert mock_impl.await_args.kwargs["user_id"] == str(auth_user.id)

    @pytest.mark.django_db
    def test_user_without_id_yields_empty_string(self) -> None:
        anon = MagicMock()
        anon.is_authenticated = False
        request = _post_request(anon)
        request.auth = None  # type: ignore[assignment]

        payload = ChatRequest(message="hi")

        with patch(
            "apps.core.api.ninja_llm_api.achat_with_context_impl",
            new_callable=AsyncMock,
            return_value={"response": "r", "session_id": "s-3"},
        ) as mock_impl:
            result = async_to_sync(chat_with_context)(request, payload)

        assert result.session_id == "s-3"
        assert mock_impl.await_args.kwargs["user_id"] == ""


class TestChatWithContextStream:
    @pytest.mark.django_db
    def test_streaming_response_headers_and_content(self) -> None:
        request = _post_request(_FakeUser(), path="/api/v1/core/llm/chat/stream")
        payload = ChatRequest(message="流式问题")

        fake_stream = iter([b"data: chunk1\n\n", b"data: chunk2\n\n"])

        def _factory(**kwargs: Any):
            # build_chat_stream 的工厂参数应原样传递
            assert kwargs["message"] == "流式问题"
            return fake_stream

        with patch("apps.core.services.llm_stream_service.build_chat_stream", side_effect=_factory):
            resp = async_to_sync(chat_with_context_stream)(request, payload)

        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/event-stream"
        assert resp["Cache-Control"] == "no-cache"
        assert resp["X-Accel-Buffering"] == "no"
        assert b"".join(resp.streaming_content) == b"data: chunk1\n\ndata: chunk2\n\n"

    @pytest.mark.django_db
    def test_unauthenticated_user_falls_back_to_auth(self) -> None:
        anon = MagicMock()
        anon.is_authenticated = False
        request = _post_request(anon, path="/api/v1/core/llm/chat/stream")
        request.auth = _FakeUser()
        payload = ChatRequest(message="m")

        captured: dict[str, Any] = {}

        def _factory(**kwargs: Any):
            captured.update(kwargs)
            return iter([])

        with patch("apps.core.services.llm_stream_service.build_chat_stream", side_effect=_factory):
            resp = async_to_sync(chat_with_context_stream)(request, payload)

        assert resp.status_code == 200
        assert captured["user_id"] == str(request.auth.id)


class TestGetConversationHistory:
    @pytest.mark.django_db
    def test_regular_user_passes_user_id(self) -> None:
        user = _FakeUser()
        request = _get_request(user, path="/api/v1/core/llm/chat/abc/history")

        with patch(
            "apps.core.api.ninja_llm_api.aget_conversation_history_impl",
            new_callable=AsyncMock,
            return_value={
                "session_id": "abc",
                "messages": [
                    {"role": "user", "content": "q", "created_at": "2026-01-01T00:00:00Z", "metadata": {"k": "v"}},
                    {"role": "assistant", "content": "a", "created_at": "2026-01-01T00:00:01Z"},
                ],
            },
        ) as mock_impl:
            result = async_to_sync(get_conversation_history)(request, "abc")

        assert result.session_id == "abc"
        assert len(result.messages) == 2
        assert result.messages[0].role == "user"
        assert result.messages[0].content == "q"
        # 普通用户：查询被限制在自己的 user_id 下
        assert mock_impl.await_args.kwargs["user_id"] == str(user.id)
        assert mock_impl.await_args.kwargs["limit"] == 50

    @pytest.mark.django_db
    def test_admin_user_gets_unfiltered_history(self) -> None:
        request = _get_request(_FakeUser(is_superuser=True), path="/api/v1/core/llm/x/history")

        with patch(
            "apps.core.api.ninja_llm_api.aget_conversation_history_impl",
            new_callable=AsyncMock,
            return_value={"session_id": "x", "messages": []},
        ) as mock_impl:
            result = async_to_sync(get_conversation_history)(request, "x")

        assert result.messages == []
        # 管理员：不按 user_id 过滤
        assert mock_impl.await_args.kwargs["user_id"] is None

    @pytest.mark.django_db
    def test_is_admin_flag_also_grants_unfiltered(self) -> None:
        request = _get_request(_FakeUser(is_admin=True), path="/api/v1/core/llm/y/history")

        with patch(
            "apps.core.api.ninja_llm_api.aget_conversation_history_impl",
            new_callable=AsyncMock,
            return_value={"session_id": "y", "messages": []},
        ) as mock_impl:
            async_to_sync(get_conversation_history)(request, "y")

        assert mock_impl.await_args.kwargs["user_id"] is None

    @pytest.mark.django_db
    def test_unauthenticated_user_falls_back_to_auth(self) -> None:
        anon = MagicMock()
        anon.is_authenticated = False
        request = _get_request(anon, path="/api/v1/core/llm/z/history")
        auth_user = _FakeUser()
        request.auth = auth_user

        with patch(
            "apps.core.api.ninja_llm_api.aget_conversation_history_impl",
            new_callable=AsyncMock,
            return_value={"session_id": "z", "messages": []},
        ) as mock_impl:
            async_to_sync(get_conversation_history)(request, "z")

        assert mock_impl.await_args.kwargs["user_id"] == str(auth_user.id)


class TestSyncPromptTemplates:
    @pytest.mark.django_db
    def test_non_admin_denied(self) -> None:
        request = _post_request(_FakeUser(), path="/api/v1/core/llm/templates/sync")
        with pytest.raises(PermissionDenied):
            sync_prompt_templates(request)

    @pytest.mark.django_db
    def test_superuser_syncs(self) -> None:
        request = _post_request(_FakeUser(is_superuser=True), path="/api/v1/core/llm/templates/sync")
        with patch(
            "apps.core.api.ninja_llm_api.sync_prompt_templates_impl",
            return_value={"synced_count": 4},
        ) as mock_impl:
            result = sync_prompt_templates(request)

        assert result.synced_count == 4
        mock_impl.assert_called_once_with(overwrite=True)

    @pytest.mark.django_db
    def test_missing_count_defaults_to_zero(self) -> None:
        request = _post_request(_FakeUser(is_admin=True), path="/api/v1/core/llm/templates/sync")
        with patch("apps.core.api.ninja_llm_api.sync_prompt_templates_impl", return_value={}):
            result = sync_prompt_templates(request)
        assert result.synced_count == 0

    @pytest.mark.django_db
    def test_unauthenticated_user_falls_back_to_auth_admin(self) -> None:
        anon = MagicMock()
        anon.is_authenticated = False
        request = _post_request(anon, path="/api/v1/core/llm/templates/sync")
        request.auth = _FakeUser(is_superuser=True)

        with patch(
            "apps.core.api.ninja_llm_api.sync_prompt_templates_impl",
            return_value={"synced_count": 1},
        ) as mock_impl:
            result = sync_prompt_templates(request)

        assert result.synced_count == 1
        mock_impl.assert_called_once_with(overwrite=True)

    def test_impl_delegates_to_service(self) -> None:
        from apps.core.api.ninja_llm_api import sync_prompt_templates_impl

        with patch("apps.core.services.prompt_template_service.sync_prompt_templates") as mock_sync:
            mock_sync.return_value = {"synced_count": 2}
            result = sync_prompt_templates_impl(overwrite=False)
        assert result == {"synced_count": 2}
        mock_sync.assert_called_once_with(overwrite=False)


class TestListAvailableModels:
    @pytest.mark.django_db
    def test_default_model_first_and_dedup(self) -> None:
        request = _get_request(_FakeUser())

        service = MagicMock()
        service.aget_result = AsyncMock(
            return_value=MagicMock(models=[{"id": "m2", "name": "m2name"}, {"id": "m2"}, {"id": ""}])
        )
        cfg = MagicMock()
        cfg.get_openai_compatible_model.return_value = "default-m"
        cfg.resolve_backend_for_model.return_value = "openai_compatible"

        with (
            patch("apps.core.llm.model_list_service.ModelListService", return_value=service),
            patch("apps.core.llm.config.LLMConfig", cfg),
        ):
            result = async_to_sync(list_available_models)(request)

        assert [m.id for m in result.models] == ["default-m", "m2"]
        assert result.models[0].name == "default-m（默认）"
        assert result.models[1].name == "m2name"
        assert result.models[0].backend == "openai_compatible"

    @pytest.mark.django_db
    def test_model_name_falls_back_to_id(self) -> None:
        request = _get_request(_FakeUser())

        service = MagicMock()
        service.aget_result = AsyncMock(return_value=MagicMock(models=[{"id": "m3", "name": "m3"}]))
        cfg = MagicMock()
        cfg.get_openai_compatible_model.return_value = ""
        cfg.resolve_backend_for_model.return_value = "openai_compatible"

        with (
            patch("apps.core.llm.model_list_service.ModelListService", return_value=service),
            patch("apps.core.llm.config.LLMConfig", cfg),
        ):
            result = async_to_sync(list_available_models)(request)

        assert len(result.models) == 1
        assert result.models[0].id == "m3"
        # name 与 id 相同时展示 id 本身
        assert result.models[0].name == "m3"


class TestTestModelConnection:
    @pytest.mark.django_db
    def test_non_admin_denied(self) -> None:
        request = _post_request(_FakeUser(), path="/api/v1/core/llm/test-connection")
        with pytest.raises(PermissionDenied):
            async_to_sync(llm_model_connection)(request, model_id="m")

    @pytest.mark.django_db
    def test_no_user_denied(self) -> None:
        request = _post_request(None, path="/api/v1/core/llm/test-connection")
        with pytest.raises(PermissionDenied):
            async_to_sync(llm_model_connection)(request, model_id="m")

    @pytest.mark.django_db
    def test_empty_model_id_returns_error(self) -> None:
        request = _post_request(_FakeUser(is_superuser=True), path="/api/v1/core/llm/test-connection")
        result = async_to_sync(llm_model_connection)(request, model_id="   ")
        assert result == {"ok": False, "error": "请指定模型 ID"}

    @pytest.mark.django_db
    def test_success_returns_model_and_backend(self) -> None:
        request = _post_request(_FakeUser(is_admin=True), path="/api/v1/core/llm/test-connection")

        llm_service = MagicMock()
        llm_service.achat = AsyncMock()
        llm_service.achat.return_value = MagicMock(model="target-m", backend="openai_compatible")

        with patch("apps.core.llm.service.get_llm_service", return_value=llm_service):
            result = async_to_sync(llm_model_connection)(request, model_id=" target-m ")

        assert result == {"ok": True, "model": "target-m", "backend": "openai_compatible"}
        call_kwargs = llm_service.achat.await_args.kwargs
        assert call_kwargs["model"] == "target-m"
        assert call_kwargs["fallback"] is False
        assert call_kwargs["max_tokens"] == 5

    @pytest.mark.django_db
    def test_failure_returns_error_payload(self) -> None:
        request = _post_request(_FakeUser(is_superuser=True), path="/api/v1/core/llm/test-connection")

        llm_service = MagicMock()
        llm_service.achat = AsyncMock(side_effect=RuntimeError("conn refused"))

        with patch("apps.core.llm.service.get_llm_service", return_value=llm_service):
            result = async_to_sync(llm_model_connection)(request, model_id="m")

        assert result["ok"] is False
        assert "conn refused" in result["error"]
