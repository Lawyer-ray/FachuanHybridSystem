"""Coverage tests for core.services.conversation_history_service."""

from unittest.mock import MagicMock, patch

import pytest


class TestConversationHistoryService:
    def _make(self):
        from apps.core.services.conversation_history_service import ConversationHistoryService

        repo = MagicMock()
        return ConversationHistoryService(repository=repo), repo

    def test_create_message(self):
        svc, repo = self._make()
        mock_record = MagicMock()
        mock_record.pk = 1
        mock_record.session_id = "s1"
        mock_record.user_id = "u1"
        mock_record.role = "user"
        mock_record.content = "hello"
        mock_record.metadata = {}
        mock_record.created_at = MagicMock()
        mock_record.litigation_session_id = None
        mock_record.step = ""
        repo.create.return_value = mock_record
        result = svc.create_message_internal(
            session_id="s1", user_id="u1", role="user", content="hello", metadata={}
        )
        assert result.id == 1

    def test_list_messages_empty(self):
        svc, repo = self._make()
        result = svc.list_messages_internal()
        assert result == []

    def test_list_messages_with_session(self):
        svc, repo = self._make()
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        repo.get_all.return_value = mock_qs
        result = svc.list_messages_internal(session_id="s1")
        assert isinstance(result, list)

    def test_count_messages_empty(self):
        svc, repo = self._make()
        result = svc.count_messages_internal()
        assert result == 0

    def test_count_messages_with_session(self):
        svc, repo = self._make()
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.count.return_value = 5
        repo.get_all.return_value = mock_qs
        result = svc.count_messages_internal(session_id="s1")
        assert result == 5

    def test_count_messages_by_litigation_session_ids_empty(self):
        svc, repo = self._make()
        result = svc.count_messages_by_litigation_session_ids_internal(litigation_session_ids=[])
        assert result == {}

    def test_list_messages_desc(self):
        svc, repo = self._make()
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        repo.get_all.return_value = mock_qs
        result = svc.list_messages_internal(session_id="s1", order="desc")
        assert isinstance(result, list)
