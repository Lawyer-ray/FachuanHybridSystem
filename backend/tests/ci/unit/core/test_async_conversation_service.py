"""Tests for async conversation service and repository methods."""

from __future__ import annotations

from unittest.mock import MagicMock

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


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_aget_conversation_history_messages_returns_ordered_list():
    from apps.core.services.conversation_history_service import ConversationHistoryService

    record1 = MagicMock()
    record1.role = "user"
    record1.content = "hello"
    record1.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    record1.metadata = {}

    record2 = MagicMock()
    record2.role = "assistant"
    record2.content = "hi"
    record2.created_at.isoformat.return_value = "2026-01-01T00:00:01"
    record2.metadata = {}

    mock_repo = MagicMock()
    mock_qs = MagicMock()
    mock_qs.filter.return_value = mock_qs
    mock_qs.order_by.return_value.__getitem__ = MagicMock(return_value=[record2, record1])
    mock_repo.get_by_session_id.return_value = mock_qs

    service = ConversationHistoryService(repository=mock_repo)
    result = await service.aget_conversation_history_messages(session_id="test", limit=50)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "hello"
    assert result[1]["role"] == "assistant"
