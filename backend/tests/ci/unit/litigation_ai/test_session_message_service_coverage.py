"""Tests for session_message_service — coverage for uncovered branches."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.litigation_ai.services.session.session_message_service import SessionMessageService


def _make_msg(
    id: int = 1,
    session_id: str = "sess1",
    role: str = "user",
    content: str = "hello",
    metadata: dict | None = None,
    created_at: str = "2025-01-01T00:00:00Z",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        session_id=session_id,
        role=role,
        content=content,
        metadata=metadata or {},
        created_at=created_at,
    )


def _make_session(
    id: int = 1,
    session_id: str = "sess1",
    user_id: int = 10,
    metadata: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        session_id=session_id,
        user_id=user_id,
        metadata=metadata or {},
    )


@pytest.fixture()
def svc() -> SessionMessageService:
    with (
        patch("apps.litigation_ai.services.flow.session_repository.LitigationSessionRepository") as mock_repo_cls,
        patch("apps.litigation_ai.services.wiring.get_conversation_history_service") as mock_wiring,
    ):
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_ch = MagicMock()
        mock_wiring.return_value = mock_ch
        s = SessionMessageService()
        s._mock_repo = mock_repo
        s._mock_ch = mock_ch
        return s


@pytest.mark.django_db()
class TestAddMessage:
    def test_session_not_found(self, svc: SessionMessageService) -> None:
        svc._mock_repo.get_session_sync.return_value = None
        with pytest.raises(NotFoundError, match="会话不存在"):
            svc.add_message("sess1", "user", "hello")

    def test_session_found(self, svc: SessionMessageService) -> None:
        svc._mock_repo.get_session_sync.return_value = _make_session()
        mock_msg = _make_msg()
        svc._mock_ch.create_message_internal.return_value = mock_msg
        result = svc.add_message("sess1", "user", "hello", metadata={"step": "s1"})
        assert result.content == "hello"
        svc._mock_ch.create_message_internal.assert_called_once()

    def test_no_metadata(self, svc: SessionMessageService) -> None:
        svc._mock_repo.get_session_sync.return_value = _make_session()
        svc._mock_ch.create_message_internal.return_value = _make_msg(role="assistant")
        result = svc.add_message("sess1", "assistant", "world")
        assert result.role == "assistant"


class TestGetMessages:
    def test_session_not_found(self, svc: SessionMessageService) -> None:
        svc._mock_repo.get_session_sync.return_value = None
        with pytest.raises(NotFoundError, match="会话不存在"):
            svc.get_messages("sess1")

    def test_session_found(self, svc: SessionMessageService) -> None:
        svc._mock_repo.get_session_sync.return_value = _make_session()
        svc._mock_ch.list_messages_internal.return_value = [_make_msg(id=1), _make_msg(id=2)]
        result = svc.get_messages("sess1", limit=10, offset=0)
        assert len(result) == 2

    def test_empty_messages(self, svc: SessionMessageService) -> None:
        svc._mock_repo.get_session_sync.return_value = _make_session()
        svc._mock_ch.list_messages_internal.return_value = []
        result = svc.get_messages("sess1")
        assert result == []


class TestGetMessageCount:
    def test_session_not_found(self, svc: SessionMessageService) -> None:
        svc._mock_repo.get_session_sync.return_value = None
        with pytest.raises(NotFoundError, match="会话不存在"):
            svc.get_message_count("sess1")

    def test_session_found(self, svc: SessionMessageService) -> None:
        svc._mock_repo.get_session_sync.return_value = _make_session()
        svc._mock_ch.count_messages_internal.return_value = 42
        assert svc.get_message_count("sess1") == 42


class TestGetMessagesBatch:
    def test_session_not_found(self, svc: SessionMessageService) -> None:
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError, match="会话不存在"):
                svc.get_messages_batch("sess1")

    def test_session_found(self, svc: SessionMessageService) -> None:
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = _make_session()
            svc._mock_ch.list_messages_internal.return_value = [_make_msg(id=2), _make_msg(id=1)]
            result = svc.get_messages_batch("sess1", limit=10)
            assert len(result) == 2
            # items should be reversed to ascending order
            assert result[0].id == 1
            assert result[1].id == 2

    def test_with_before_id(self, svc: SessionMessageService) -> None:
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = _make_session()
            svc._mock_ch.list_messages_internal.return_value = []
            result = svc.get_messages_batch("sess1", limit=5, before_id=10)
            assert result == []


@pytest.mark.django_db()
class TestSaveConversationSummary:
    def test_session_not_found(self, svc: SessionMessageService) -> None:
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError, match="会话不存在"):
                svc.save_conversation_summary("sess1", "summary text")

    def test_session_found(self, svc: SessionMessageService) -> None:
        mock_session = _make_session(metadata={"existing": "data"})
        mock_session.save = MagicMock()
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = mock_session
            svc.save_conversation_summary("sess1", "new summary")
            assert mock_session.metadata["conversation_summary"] == "new summary"
            mock_session.save.assert_called_once_with(update_fields=["metadata"])

    def test_session_with_none_metadata(self, svc: SessionMessageService) -> None:
        mock_session = _make_session(metadata=None)
        mock_session.save = MagicMock()
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = mock_session
            svc.save_conversation_summary("sess1", "summary")
            assert mock_session.metadata["conversation_summary"] == "summary"


class TestGetConversationSummary:
    def test_session_not_found(self, svc: SessionMessageService) -> None:
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = None
            assert svc.get_conversation_summary("sess1") is None

    def test_session_with_summary(self, svc: SessionMessageService) -> None:
        mock_session = _make_session(metadata={"conversation_summary": "the summary"})
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = mock_session
            assert svc.get_conversation_summary("sess1") == "the summary"

    def test_session_without_summary(self, svc: SessionMessageService) -> None:
        mock_session = _make_session(metadata={"other_key": "value"})
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = mock_session
            assert svc.get_conversation_summary("sess1") is None

    def test_session_with_none_metadata(self, svc: SessionMessageService) -> None:
        mock_session = _make_session(metadata=None)
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = mock_session
            assert svc.get_conversation_summary("sess1") is None


@pytest.mark.django_db()
class TestAddMessagesBatch:
    def test_session_not_found(self, svc: SessionMessageService) -> None:
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError, match="会话不存在"):
                svc.add_messages_batch("sess1", [{"role": "user", "content": "hi"}])

    def test_batch_creates_messages(self, svc: SessionMessageService) -> None:
        mock_session = _make_session()
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = mock_session
            svc._mock_ch.create_message_internal.return_value = _make_msg()
            messages = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world", "metadata": {"step": "s2"}},
            ]
            result = svc.add_messages_batch("sess1", messages)
            assert len(result) == 2
            assert svc._mock_ch.create_message_internal.call_count == 2

    def test_batch_empty_messages(self, svc: SessionMessageService) -> None:
        mock_session = _make_session()
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = mock_session
            result = svc.add_messages_batch("sess1", [])
            assert result == []


class TestToMessageDto:
    def test_conversion(self, svc: SessionMessageService) -> None:
        msg = _make_msg()
        result = svc._to_message_dto(msg)
        assert result.id == 1
        assert result.role == "user"
        assert result.content == "hello"
