"""litigation_ai session_lifecycle_service 补充覆盖测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


# ── _to_session_dto ───────────────────────────────────────────────

class TestToSessionDTO:
    def _make_service(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService
        with patch.object(SessionLifecycleService, "__init__", lambda self: None):
            svc = SessionLifecycleService()
            svc.case_service = MagicMock()
            svc.conversation_history_service = MagicMock()
            svc.session_repo = MagicMock()
            return svc

    def test_basic_dto(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = 1
        session.session_id = "abc-123"
        session.case_id = 42
        session.user_id = 10
        session.document_type = "complaint"
        session.status = "active"
        session.metadata = {"key": "value"}
        session.created_at = "2026-01-01T00:00:00Z"
        session.updated_at = "2026-01-01T00:00:00Z"
        session.case = MagicMock()
        session.case.name = "Test Case"

        dto = svc._to_session_dto(session)
        assert dto.id == 1
        assert dto.session_id == "abc-123"
        assert dto.case_name == "Test Case"

    def test_no_case_object(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = 1
        session.session_id = "abc-123"
        session.case_id = 42
        session.user_id = 10
        session.document_type = ""
        session.status = "active"
        session.metadata = {}
        session.created_at = None
        session.updated_at = None
        session.case = None

        dto = svc._to_session_dto(session)
        assert dto.case_name == ""

    def test_case_name_exception(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = 1
        session.session_id = "abc-123"
        session.case_id = 42
        session.user_id = 10
        session.document_type = ""
        session.status = "active"
        session.metadata = None
        session.created_at = None
        session.updated_at = None
        # Simulate exception when accessing case
        type(session).case = PropertyMock(side_effect=RuntimeError("DB error"))

        dto = svc._to_session_dto(session)
        assert dto.case_name == ""


# ── create_session ────────────────────────────────────────────────

class TestCreateSession:
    def _make_service(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService
        with patch.object(SessionLifecycleService, "__init__", lambda self: None):
            svc = SessionLifecycleService()
            svc.case_service = MagicMock()
            svc.conversation_history_service = MagicMock()
            svc.session_repo = MagicMock()
            return svc

    @patch("apps.litigation_ai.models.LitigationSession")
    def test_create_basic(self, mock_model):
        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.id = 1
        mock_session.session_id = "abc-123"
        mock_session.case_id = 1
        mock_session.case = None
        mock_session.document_type = ""
        mock_session.status = "active"
        mock_session.metadata = {}
        mock_session.created_at = None
        mock_session.updated_at = None
        mock_session.user_id = None
        mock_model.objects.create.return_value = mock_session

        with patch.object(svc, "_to_session_dto") as mock_dto:
            mock_dto.return_value = MagicMock()
            svc.create_session(case_id=1, user_id=None, session_type=None)
            mock_model.objects.create.assert_called_once()

    @patch("apps.litigation_ai.models.LitigationSession")
    def test_create_with_session_type(self, mock_model):
        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.id = 1
        mock_session.session_id = "abc-123"
        mock_session.case_id = 1
        mock_session.case = None
        mock_session.document_type = ""
        mock_session.status = "active"
        mock_session.metadata = {}
        mock_session.created_at = None
        mock_session.updated_at = None
        mock_session.user_id = 5
        mock_model.objects.create.return_value = mock_session

        with patch.object(svc, "_to_session_dto") as mock_dto:
            mock_dto.return_value = MagicMock()
            svc.create_session(case_id=1, user_id=5, session_type="mock_trial")
            call_kwargs = mock_model.objects.create.call_args[1]
            assert call_kwargs["session_type"] == "mock_trial"
            assert call_kwargs["user_id"] == 5


# ── get_session ───────────────────────────────────────────────────

class TestGetSession:
    def _make_service(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService
        with patch.object(SessionLifecycleService, "__init__", lambda self: None):
            svc = SessionLifecycleService()
            svc.case_service = MagicMock()
            svc.conversation_history_service = MagicMock()
            svc.session_repo = MagicMock()
            return svc

    def test_not_found_raises(self):
        svc = self._make_service()
        svc.session_repo.get_session_with_case_sync.return_value = None
        with pytest.raises(NotFoundError):
            svc.get_session("nonexistent-id")

    def test_found(self):
        svc = self._make_service()
        mock_session = MagicMock()
        svc.session_repo.get_session_with_case_sync.return_value = mock_session
        with patch.object(svc, "_to_session_dto") as mock_dto:
            mock_dto.return_value = MagicMock()
            svc.get_session("abc-123")
            mock_dto.assert_called_once_with(mock_session)


# ── update_session_status ─────────────────────────────────────────

class TestUpdateSessionStatus:
    def _make_service(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService
        with patch.object(SessionLifecycleService, "__init__", lambda self: None):
            svc = SessionLifecycleService()
            svc.case_service = MagicMock()
            svc.conversation_history_service = MagicMock()
            svc.session_repo = MagicMock()
            return svc

    @pytest.mark.django_db
    def test_not_found_raises(self):
        svc = self._make_service()
        svc.session_repo.get_session_sync.return_value = None
        with pytest.raises(NotFoundError):
            svc.update_session_status("abc-123", "closed")

    @pytest.mark.django_db
    @patch("apps.litigation_ai.models.choices.SessionStatus")
    def test_invalid_status_raises(self, mock_status):
        svc = self._make_service()
        mock_session = MagicMock()
        svc.session_repo.get_session_sync.return_value = mock_session
        mock_status.choices = [("active", "Active"), ("closed", "Closed")]
        with pytest.raises(ValidationException, match="无效"):
            svc.update_session_status("abc-123", "invalid_status")

    @pytest.mark.django_db
    @patch("apps.litigation_ai.models.choices.SessionStatus")
    def test_valid_status_update(self, mock_status):
        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.metadata = {}
        svc.session_repo.get_session_sync.return_value = mock_session
        mock_status.choices = [("active", "Active"), ("closed", "Closed")]

        with patch.object(svc, "_to_session_dto") as mock_dto:
            mock_dto.return_value = MagicMock()
            svc.update_session_status("abc-123", "closed", metadata_updates={"reason": "done"})
            assert mock_session.status == "closed"
            mock_session.save.assert_called_once()

    @pytest.mark.django_db
    @patch("apps.litigation_ai.models.choices.SessionStatus")
    def test_update_without_metadata(self, mock_status):
        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.metadata = {}
        svc.session_repo.get_session_sync.return_value = mock_session
        mock_status.choices = [("active", "Active"), ("closed", "Closed")]

        with patch.object(svc, "_to_session_dto") as mock_dto:
            mock_dto.return_value = MagicMock()
            svc.update_session_status("abc-123", "active")
            mock_session.save.assert_called_once()


# ── delete_session ────────────────────────────────────────────────

class TestDeleteSession:
    def _make_service(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService
        with patch.object(SessionLifecycleService, "__init__", lambda self: None):
            svc = SessionLifecycleService()
            svc.case_service = MagicMock()
            svc.conversation_history_service = MagicMock()
            svc.session_repo = MagicMock()
            return svc

    @pytest.mark.django_db
    def test_not_found_raises(self):
        svc = self._make_service()
        svc.session_repo.get_session_for_update_sync.return_value = None
        with pytest.raises(NotFoundError):
            svc.delete_session("abc-123")

    @pytest.mark.django_db
    def test_permission_denied(self):
        from apps.core.exceptions import PermissionDenied

        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.user_id = 1
        svc.session_repo.get_session_for_update_sync.return_value = mock_session

        user = MagicMock()
        user.id = 2
        with pytest.raises(PermissionDenied):
            svc.delete_session("abc-123", user=user)

    @pytest.mark.django_db
    def test_successful_delete(self):
        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.user_id = 1
        mock_session._meta = MagicMock()
        mock_session._meta.related_objects = []
        svc.session_repo.get_session_for_update_sync.return_value = mock_session

        with patch.object(svc, "_detach_related_rows"):
            svc.delete_session("abc-123")
            mock_session.delete.assert_called_once()


# ── list_sessions ─────────────────────────────────────────────────

class TestListSessions:
    def _make_service(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService
        with patch.object(SessionLifecycleService, "__init__", lambda self: None):
            svc = SessionLifecycleService()
            svc.case_service = MagicMock()
            svc.conversation_history_service = MagicMock()
            svc.session_repo = MagicMock()
            return svc

    def test_empty_list(self):
        svc = self._make_service()
        svc.session_repo.list_sessions_sync.return_value = (0, [])
        svc.conversation_history_service.count_messages_by_litigation_session_ids_internal.return_value = {}
        result = svc.list_sessions()
        assert result["total"] == 0
        assert result["sessions"] == []

    def test_with_sessions(self):
        svc = self._make_service()
        mock_s1 = MagicMock()
        mock_s1.id = 1
        mock_s1.session_id = "s1"
        mock_s1.case_id = 10
        mock_s1.document_type = "complaint"
        mock_s1.status = "active"
        mock_s1.metadata = {}
        mock_s1.created_at = None
        mock_s1.updated_at = None

        svc.session_repo.list_sessions_sync.return_value = (1, [mock_s1])
        svc.conversation_history_service.count_messages_by_litigation_session_ids_internal.return_value = {1: 5}

        result = svc.list_sessions(user_id=1, case_id=10, status="active", session_type="litigation")
        assert result["total"] == 1
        assert len(result["sessions"]) == 1
        assert result["sessions"][0]["message_count"] == 5


# ── _detach_legacy_tables ─────────────────────────────────────────

class TestDetachLegacyTables:
    def _make_service(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService
        with patch.object(SessionLifecycleService, "__init__", lambda self: None):
            svc = SessionLifecycleService()
            svc.case_service = MagicMock()
            svc.conversation_history_service = MagicMock()
            svc.session_repo = MagicMock()
            return svc

    @patch("django.db.connection")
    def test_non_sqlite_returns(self, mock_conn):
        svc = self._make_service()
        mock_conn.vendor = "postgresql"
        session = MagicMock()
        svc._detach_legacy_tables(session)
        # Should return without doing anything

    @patch("django.db.connection")
    def test_table_not_exists(self, mock_conn):
        svc = self._make_service()
        mock_conn.vendor = "sqlite"
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        session = MagicMock()
        svc._detach_legacy_tables(session)
        mock_cursor.execute.assert_called_once()


# ── get_recommended_document_types ────────────────────────────────

class TestGetRecommendedDocumentTypes:
    def _make_service(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService
        with patch.object(SessionLifecycleService, "__init__", lambda self: None):
            svc = SessionLifecycleService()
            svc.case_service = MagicMock()
            svc.conversation_history_service = MagicMock()
            svc.session_repo = MagicMock()
            return svc

    def test_case_not_found(self):
        svc = self._make_service()
        svc.case_service.get_case_internal.return_value = None
        with pytest.raises(NotFoundError):
            svc.get_recommended_document_types(999)

    @patch("apps.litigation_ai.services.session.session_lifecycle_service.get_court_pleading_signals_service")
    @patch("apps.core.models.enums.LegalStatus")
    @patch("apps.litigation_ai.models.choices.DocumentType")
    def test_plaintiff_recommendations(self, mock_doc_type, mock_legal_status, mock_signals):
        svc = self._make_service()
        svc.case_service.get_case_internal.return_value = MagicMock()
        party = MagicMock()
        party.legal_status = "plaintiff"
        svc.case_service.get_case_parties_internal.return_value = [party]

        mock_signals_svc = MagicMock()
        mock_signals_svc.get_signals_internal.return_value = MagicMock(has_counterclaim=False)
        mock_signals.return_value = mock_signals_svc

        mock_legal_status.PLAINTIFF = "plaintiff"
        mock_legal_status.APPLICANT = "applicant"
        mock_legal_status.APPELLANT = "appellant"
        mock_legal_status.ORIGINAL_PLAINTIFF = "original_plaintiff"
        mock_legal_status.DEFENDANT = "defendant"
        mock_legal_status.RESPONDENT = "respondent"
        mock_legal_status.APPELLEE = "appellee"
        mock_legal_status.ORIGINAL_DEFENDANT = "original_defendant"
        mock_legal_status.CRIMINAL_DEFENDANT = "criminal_defendant"

        mock_doc_type.COMPLAINT = "complaint"
        mock_doc_type.DEFENSE = "defense"
        mock_doc_type.COUNTERCLAIM = "counterclaim"
        mock_doc_type.COUNTERCLAIM_DEFENSE = "counterclaim_defense"

        result = svc.get_recommended_document_types(1)
        assert "complaint" in result

    @patch("apps.litigation_ai.services.session.session_lifecycle_service.get_court_pleading_signals_service")
    @patch("apps.core.models.enums.LegalStatus")
    @patch("apps.litigation_ai.models.choices.DocumentType")
    def test_defendant_recommendations(self, mock_doc_type, mock_legal_status, mock_signals):
        svc = self._make_service()
        svc.case_service.get_case_internal.return_value = MagicMock()
        party = MagicMock()
        party.legal_status = "defendant"
        svc.case_service.get_case_parties_internal.return_value = [party]

        mock_signals_svc = MagicMock()
        mock_signals_svc.get_signals_internal.return_value = MagicMock(has_counterclaim=False)
        mock_signals.return_value = mock_signals_svc

        mock_legal_status.PLAINTIFF = "plaintiff"
        mock_legal_status.APPLICANT = "applicant"
        mock_legal_status.APPELLANT = "appellant"
        mock_legal_status.ORIGINAL_PLAINTIFF = "original_plaintiff"
        mock_legal_status.DEFENDANT = "defendant"
        mock_legal_status.RESPONDENT = "respondent"
        mock_legal_status.APPELLEE = "appellee"
        mock_legal_status.ORIGINAL_DEFENDANT = "original_defendant"
        mock_legal_status.CRIMINAL_DEFENDANT = "criminal_defendant"

        mock_doc_type.COMPLAINT = "complaint"
        mock_doc_type.DEFENSE = "defense"
        mock_doc_type.COUNTERCLAIM = "counterclaim"
        mock_doc_type.COUNTERCLAIM_DEFENSE = "counterclaim_defense"

        result = svc.get_recommended_document_types(1)
        assert "defense" in result
        assert "counterclaim" in result
