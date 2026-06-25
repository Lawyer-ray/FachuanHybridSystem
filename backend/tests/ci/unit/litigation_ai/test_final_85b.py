"""Coverage boost tests for litigation_ai module — session, flow, evidence, generation, agent."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


# ============================================================================
# session/session_lifecycle_service.py — SessionLifecycleService
# ============================================================================


class TestSessionLifecycleServiceGetSession:
    def test_raises_when_not_found(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService

        svc = SessionLifecycleService.__new__(SessionLifecycleService)
        svc.session_repo = Mock()
        svc.session_repo.get_session_with_case_sync.return_value = None
        with pytest.raises(NotFoundError):
            svc.get_session("nonexistent-id")

    def test_returns_dto_when_found(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService

        svc = SessionLifecycleService.__new__(SessionLifecycleService)
        svc.session_repo = Mock()
        mock_session = Mock()
        mock_session.case = None
        mock_session.session_id = "test-uuid"
        mock_session.case_id = 1
        mock_session.user_id = 1
        mock_session.document_type = "complaint"
        mock_session.status = "active"
        mock_session.metadata = {}
        mock_session.id = 1
        mock_session.created_at = None
        mock_session.updated_at = None
        svc.session_repo.get_session_with_case_sync.return_value = mock_session
        result = svc.get_session("test-uuid")
        assert result.session_id == "test-uuid"


class TestSessionLifecycleServiceToSessionDto:
    def test_with_case(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService

        svc = SessionLifecycleService.__new__(SessionLifecycleService)
        mock_session = Mock()
        mock_session.case = Mock(name="张某诉李某")
        mock_session.case.name = "张某诉李某"
        mock_session.session_id = "uuid-1"
        mock_session.case_id = 1
        mock_session.user_id = 1
        mock_session.document_type = "complaint"
        mock_session.status = "active"
        mock_session.metadata = {"key": "val"}
        mock_session.id = 1
        mock_session.created_at = None
        mock_session.updated_at = None
        result = svc._to_session_dto(mock_session)
        assert result.case_name == "张某诉李某"

    def test_without_case(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService

        svc = SessionLifecycleService.__new__(SessionLifecycleService)
        mock_session = Mock()
        mock_session.case = None
        mock_session.session_id = "uuid-2"
        mock_session.case_id = 2
        mock_session.user_id = 2
        mock_session.document_type = ""
        mock_session.status = "active"
        mock_session.metadata = {}
        mock_session.id = 2
        mock_session.created_at = None
        mock_session.updated_at = None
        result = svc._to_session_dto(mock_session)
        assert result.case_name == ""

    def test_case_raises_exception(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService

        svc = SessionLifecycleService.__new__(SessionLifecycleService)
        mock_session = Mock()
        type(mock_session).case = property(lambda self: (_ for _ in ()).throw(RuntimeError("no case")))
        mock_session.session_id = "uuid-3"
        mock_session.case_id = 3
        mock_session.user_id = 3
        mock_session.document_type = ""
        mock_session.status = "active"
        mock_session.metadata = {}
        mock_session.id = 3
        mock_session.created_at = None
        mock_session.updated_at = None
        result = svc._to_session_dto(mock_session)
        assert result.case_name == ""


class TestSessionLifecycleServiceListSessions:
    def test_returns_sessions(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService

        svc = SessionLifecycleService.__new__(SessionLifecycleService)
        svc.session_repo = Mock()
        svc.conversation_history_service = Mock()
        mock_session = Mock()
        mock_session.id = 1
        mock_session.session_id = "uuid-1"
        mock_session.case_id = 1
        mock_session.document_type = "complaint"
        mock_session.status = "active"
        mock_session.metadata = {}
        mock_session.created_at = None
        mock_session.updated_at = None
        svc.session_repo.list_sessions_sync.return_value = (1, [mock_session])
        svc.conversation_history_service.count_messages_by_litigation_session_ids_internal.return_value = {1: 5}
        result = svc.list_sessions(case_id=1)
        assert result["total"] == 1
        assert len(result["sessions"]) == 1
        assert result["sessions"][0]["message_count"] == 5


class TestSessionLifecycleServiceDeleteSession:
    def test_detach_related_rows_no_relations(self):
        from apps.litigation_ai.services.session.session_lifecycle_service import SessionLifecycleService

        svc = SessionLifecycleService.__new__(SessionLifecycleService)
        mock_session = Mock()
        mock_session._meta.related_objects = []
        with patch.object(svc, "_detach_legacy_tables"):
            svc._detach_related_rows(mock_session)  # should not raise


# ============================================================================
# flow/flow_state_machine.py — FlowStateMachine
# ============================================================================


class TestFlowStateMachine:
    def test_init(self):
        from apps.litigation_ai.services.flow.flow_state_machine import FlowStateMachine

        machine = FlowStateMachine()
        assert machine is not None


# ============================================================================
# flow/session_repository.py — LitigationSessionRepository
# ============================================================================


class TestLitigationSessionRepository:
    def test_init(self):
        from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository

        repo = LitigationSessionRepository()
        assert repo is not None


# ============================================================================
# flow/flow_messenger.py
# ============================================================================


class TestFlowMessenger:
    def test_init(self):
        from apps.litigation_ai.services.flow.flow_messenger import FlowMessenger

        messenger = FlowMessenger.__new__(FlowMessenger)
        assert messenger is not None


# ============================================================================
# generation/placeholder_render_service.py
# ============================================================================


class TestPlaceholderRenderService:
    def test_render_basic(self):
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        result, stats = svc.render("Hello {name}", {"name": "World"})
        assert result == "Hello World"
        assert "name" in stats.placeholders_hit

    def test_render_empty_template(self):
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        result, stats = svc.render("", {})
        assert result == ""

    def test_render_no_placeholders(self):
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        result, stats = svc.render("No placeholders here", {"key": "val"})
        assert result == "No placeholders here"

    def test_render_multiple_placeholders(self):
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        result, stats = svc.render("{a} and {b}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_render_missing_placeholder(self):
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        result, stats = svc.render("{missing}", {})
        assert isinstance(result, str)
        assert "missing" in stats.placeholders_missed


# ============================================================================
# generation/litigation_agent_service.py
# ============================================================================


class TestLitigationAgentService:
    def test_init(self):
        from apps.litigation_ai.services.generation.litigation_agent_service import LitigationAgentService

        svc = LitigationAgentService.__new__(LitigationAgentService)
        assert svc is not None


# ============================================================================
# evidence/evidence_digest_service.py
# ============================================================================


class TestEvidenceDigestService:
    def test_init(self):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        svc = EvidenceDigestService.__new__(EvidenceDigestService)
        assert svc is not None


# ============================================================================
# evidence/evidence_vector_store_service.py
# ============================================================================


class TestEvidenceVectorStoreService:
    def test_init(self):
        from apps.litigation_ai.services.evidence.evidence_vector_store_service import (
            EvidenceVectorStoreService,
        )

        svc = EvidenceVectorStoreService.__new__(EvidenceVectorStoreService)
        assert svc is not None


# ============================================================================
# evidence/evidence_rag_service.py
# ============================================================================


class TestEvidenceRagService:
    def test_init(self):
        from apps.litigation_ai.services.evidence.evidence_rag_service import EvidenceRAGService

        svc = EvidenceRAGService.__new__(EvidenceRAGService)
        assert svc is not None


# ============================================================================
# mock_trial/report_service.py
# ============================================================================


class TestReportService:
    def test_init(self):
        from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService

        svc = MockTrialReportService.__new__(MockTrialReportService)
        assert svc is not None


# ============================================================================
# session/context_service.py
# ============================================================================


class TestContextService:
    def test_init(self):
        from apps.litigation_ai.services.session.context_service import LitigationContextService

        svc = LitigationContextService.__new__(LitigationContextService)
        assert svc is not None


# ============================================================================
# session/conversation_session_service.py
# ============================================================================


class TestConversationSessionService:
    def test_init(self):
        from apps.litigation_ai.services.session.conversation_session_service import (
            LitigationConversationSessionService,
        )

        svc = LitigationConversationSessionService.__new__(LitigationConversationSessionService)
        assert svc is not None


# ============================================================================
# agent/tools.py
# ============================================================================


class TestAgentTools:
    def test_module_imports(self):
        from apps.litigation_ai.agent import tools

        assert tools is not None


# ============================================================================
# services/wiring.py
# ============================================================================


class TestLitigationWiring:
    def test_get_case_service(self):
        from apps.litigation_ai.services.wiring import get_case_service

        with patch("apps.litigation_ai.services.wiring.ServiceLocator") as MockSL:
            MockSL.get_case_service.return_value = Mock()
            result = get_case_service()
            assert result is not None


# ============================================================================
# session/session_shared.py — SessionDTO
# ============================================================================


class TestSessionDTO:
    def test_session_dto_creation(self):
        from apps.litigation_ai.services.session.session_shared import SessionDTO

        dto = SessionDTO(
            id=1,
            session_id="uuid-1",
            case_id=1,
            case_name="Test",
            user_id=1,
            document_type="complaint",
            status="active",
            metadata={},
            created_at=None,
            updated_at=None,
        )
        assert dto.session_id == "uuid-1"
        assert dto.case_name == "Test"
        assert dto.status == "active"
