import json
from types import SimpleNamespace

import pytest
from django.test import AsyncClient
from django.contrib.auth import get_user_model


@pytest.mark.django_db
def test_llm_chat_async_smoke(client, monkeypatch):
    class DummyConversationService:
        session_id = "s1"

        def chat_with_context(self, user_message: str, system_prompt=None):
            return "ok"

    def fake_get_conversation_service(session_id=None, user_id=None):
        return DummyConversationService()

    monkeypatch.setattr(
        "apps.core.interfaces.ServiceLocator.get_conversation_service",
        fake_get_conversation_service,
    )

    user = get_user_model().objects.create_user(username="u1", password="p1")
    client.force_login(user)

    resp = client.post(
        "/api/v1/llm/chat",
        data=json.dumps({"message": "hi"}),
        content_type="application/json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "ok"
    assert data["session_id"] == "s1"


@pytest.mark.django_db
def test_llm_templates_sync_denied_for_non_admin(client, monkeypatch):
    user = get_user_model().objects.create_user(username="u_sync_1", password="p1")
    client.force_login(user)

    resp = client.post(
        "/api/v1/llm/templates/sync",
        data=json.dumps({}),
        content_type="application/json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_llm_templates_sync_allowed_for_admin(client, monkeypatch):
    user = get_user_model().objects.create_user(username="u_sync_2", password="p2", is_staff=True)
    client.force_login(user)

    monkeypatch.setattr(
        "apps.core.api.ninja_llm_api.sync_prompt_templates_impl",
        lambda **kwargs: {"synced_count": 1},
    )

    resp = client.post(
        "/api/v1/llm/templates/sync",
        data=json.dumps({}),
        content_type="application/json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    assert resp.json()["synced_count"] == 1


@pytest.mark.django_db
def test_llm_chat_stream_sse_smoke(client, monkeypatch):
    class DummyConversationService:
        session_id = "s-stream"

        def add_user_message(self, content: str):
            return None

        def get_messages_for_llm(self):
            return [{"role": "user", "content": "hi"}]

        def add_assistant_message(self, content: str, metadata=None):
            return None

    class DummyLLMService:
        async def astream(self, messages, temperature=0.7, max_tokens=None):
            yield SimpleNamespace(content="a", usage=None, model="m1", backend="dummy")
            yield SimpleNamespace(content="b", usage=SimpleNamespace(total_tokens=3), model="m1", backend="dummy")

    def fake_get_conversation_service(session_id=None, user_id=None):
        return DummyConversationService()

    def fake_get_llm_service():
        return DummyLLMService()

    monkeypatch.setattr(
        "apps.core.interfaces.ServiceLocator.get_conversation_service",
        fake_get_conversation_service,
    )
    monkeypatch.setattr(
        "apps.core.interfaces.ServiceLocator.get_llm_service",
        fake_get_llm_service,
    )

    user = get_user_model().objects.create_user(username="u2", password="p2")
    client.force_login(user)

    resp = client.post(
        "/api/v1/llm/chat/stream",
        data=json.dumps({"message": "hi"}),
        content_type="application/json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/event-stream")

    from asgiref.sync import async_to_sync

    async def _collect():
        body = b""
        async for chunk in resp.streaming_content:
            body += chunk
            if b"\"type\": \"done\"" in body:
                break
        return body

    body = async_to_sync(_collect)()

    text = body.decode("utf-8")
    assert "\"type\": \"meta\"" in text
    assert "\"session_id\": \"s-stream\"" in text
    assert "\"type\": \"delta\"" in text
    assert "\"content\": \"a\"" in text
    assert "\"content\": \"b\"" in text
    assert "\"type\": \"done\"" in text
