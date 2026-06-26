"""Tests for async conversation service and repository methods."""

from __future__ import annotations

import pytest


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestConversationRepositoryAsync:
    async def test_acreate_persists_record(self):
        from apps.core.repositories.conversation_repository import ConversationHistoryRepository

        repo = ConversationHistoryRepository()
        record = await repo.acreate(
            session_id="test_session_async_001",
            user_id="user1",
            role="user",
            content="hello async",
            metadata={"test": True},
        )
        assert record.pk is not None
        assert record.session_id == "test_session_async_001"
        assert record.content == "hello async"
        assert record.role == "user"

    async def test_adelete_by_session_id(self):
        from apps.core.repositories.conversation_repository import ConversationHistoryRepository

        repo = ConversationHistoryRepository()
        await repo.acreate(
            session_id="to_delete_async", user_id="u1",
            role="user", content="msg", metadata={},
        )
        count, _ = await repo.adelete_by_session_id("to_delete_async")
        assert count == 1

    async def test_adelete_nonexistent_session(self):
        from apps.core.repositories.conversation_repository import ConversationHistoryRepository

        repo = ConversationHistoryRepository()
        count, _ = await repo.adelete_by_session_id("nonexistent_session_xyz")
        assert count == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestConversationServiceAsync:
    async def test_aadd_user_message(self):
        from apps.core.services.conversation_service import ConversationService

        svc = ConversationService(session_id="async_user_msg_test", user_id="u1")
        record = await svc.aadd_user_message("async hello")
        assert record.role == "user"
        assert record.content == "async hello"

    async def test_aadd_assistant_message(self):
        from apps.core.services.conversation_service import ConversationService

        svc = ConversationService(session_id="async_assist_msg_test", user_id="u1")
        record = await svc.aadd_assistant_message("async reply")
        assert record.role == "assistant"
        assert record.content == "async reply"

    async def test_multiple_messages_in_session(self):
        from apps.core.repositories.conversation_repository import ConversationHistoryRepository

        repo = ConversationHistoryRepository()
        await repo.acreate(session_id="multi_msg", user_id="u1", role="user", content="q1", metadata={})
        await repo.acreate(session_id="multi_msg", user_id="u1", role="assistant", content="a1", metadata={})
        await repo.acreate(session_id="multi_msg", user_id="u1", role="user", content="q2", metadata={})

        count, _ = await repo.adelete_by_session_id("multi_msg")
        assert count == 3
