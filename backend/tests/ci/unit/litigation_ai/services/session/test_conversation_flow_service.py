"""Tests for litigation_ai.services.session.conversation_flow_service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.services.session.conversation_flow_service import ConversationFlowService
from apps.litigation_ai.services.flow.types import ConversationStep


class TestConversationFlowService:
    def setup_method(self):
        self.service = ConversationFlowService()

    def test_choose_primary_document_type_complaint(self):
        assert self.service._choose_primary_document_type(["complaint", "defense"]) == "complaint"

    def test_choose_primary_document_type_defense(self):
        assert self.service._choose_primary_document_type(["defense", "counterclaim"]) == "defense"

    def test_choose_primary_document_type_fallback(self):
        assert self.service._choose_primary_document_type(["counterclaim"]) == "counterclaim"

    def test_choose_primary_document_type_empty(self):
        assert self.service._choose_primary_document_type([]) == "complaint"

    def test_lazy_properties(self):
        svc = ConversationFlowService()
        assert svc.session_repo is not None
        svc2 = ConversationFlowService()
        assert svc2.state_machine is not None


class TestConversationFlowServiceHandleDocumentTypeSelection:
    @pytest.mark.asyncio
    async def test_invalid_type(self):
        svc = ConversationFlowService()
        send_cb = AsyncMock()
        svc._session_repo = MagicMock()
        context = MagicMock()
        context.session_id = "s1"
        await svc.handle_document_type_selection(context, "invalid_type", send_cb)
        send_cb.assert_called_once()
        assert "error" in send_cb.call_args[0][0]["type"]
