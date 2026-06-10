"""Extended tests for litigation_ai services - wiring, flow, mock_trial."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestLitigationWiring:
    """Test the wiring module's service locator calls."""

    @patch("apps.litigation_ai.services.wiring.ServiceLocator")
    def test_get_document_service(self, mock_locator):
        from apps.litigation_ai.services.wiring import get_document_service

        mock_locator.get_document_service.return_value = MagicMock()
        result = get_document_service()
        assert result is not None

    @patch("apps.litigation_ai.services.wiring.ServiceLocator")
    def test_get_case_service(self, mock_locator):
        from apps.litigation_ai.services.wiring import get_case_service

        mock_locator.get_case_service.return_value = MagicMock()
        result = get_case_service()
        assert result is not None

    @patch("apps.litigation_ai.services.wiring.ServiceLocator")
    def test_get_evidence_service(self, mock_locator):
        from apps.litigation_ai.services.wiring import get_evidence_service

        mock_locator.get_evidence_service.return_value = MagicMock()
        result = get_evidence_service()
        assert result is not None

    @patch("apps.litigation_ai.services.wiring.ServiceLocator")
    def test_get_evidence_query_service(self, mock_locator):
        from apps.litigation_ai.services.wiring import get_evidence_query_service

        mock_locator.get_evidence_query_service.return_value = MagicMock()
        result = get_evidence_query_service()
        assert result is not None

    @patch("apps.litigation_ai.services.wiring.ServiceLocator")
    def test_get_conversation_history_service(self, mock_locator):
        from apps.litigation_ai.services.wiring import get_conversation_history_service

        mock_locator.get_conversation_history_service.return_value = MagicMock()
        result = get_conversation_history_service()
        assert result is not None

    @patch("apps.litigation_ai.services.wiring.ServiceLocator")
    def test_get_court_pleading_signals_service(self, mock_locator):
        from apps.litigation_ai.services.wiring import get_court_pleading_signals_service

        mock_locator.get_court_pleading_signals_service.return_value = MagicMock()
        result = get_court_pleading_signals_service()
        assert result is not None

    @patch("apps.litigation_ai.services.wiring.ServiceLocator")
    def test_get_generation_task_service(self, mock_locator):
        from apps.litigation_ai.services.wiring import get_generation_task_service

        mock_locator.get_generation_task_service.return_value = MagicMock()
        result = get_generation_task_service()
        assert result is not None

    @patch("apps.litigation_ai.services.wiring.ServiceLocator")
    def test_get_llm_service(self, mock_locator):
        from apps.litigation_ai.services.wiring import get_llm_service

        mock_locator.get_llm_service.return_value = MagicMock()
        result = get_llm_service()
        assert result is not None


class TestLitigationFlowState:
    """Test flow state machine logic if accessible."""

    def test_import_flow_module(self):
        """Verify the flow module is importable."""
        from apps.litigation_ai.services import flow

        assert flow is not None


class TestLitigationSession:
    """Test session management."""

    def test_import_session_module(self):
        from apps.litigation_ai.services import session

        assert session is not None


class TestLitigationGeneration:
    """Test generation module."""

    def test_import_generation_module(self):
        from apps.litigation_ai.services import generation

        assert generation is not None


class TestLitigationMockTrial:
    """Test mock trial module."""

    def test_import_mock_trial_module(self):
        from apps.litigation_ai.services import mock_trial

        assert mock_trial is not None
