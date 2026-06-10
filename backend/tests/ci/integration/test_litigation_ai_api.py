"""Litigation AI API integration tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.models import Case
from apps.contracts.models import Contract
from apps.litigation_ai.models.session import LitigationSession


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_contract():
    return Contract.objects.create(name="测试合同", case_type="civil")


def _make_case(**kwargs):
    return Case.objects.create(
        name=kwargs.get("name", "测试案件"),
        contract=kwargs.get("contract", _make_contract()),
    )


# ===================================================================
# Litigation sessions (doc_gen)
# ===================================================================


@pytest.mark.django_db
@patch("apps.litigation_ai.api.litigation_api._get_conversation_service")
def test_create_litigation_session(mock_get_svc, authenticated_client):
    case = _make_case()
    mock_session = MagicMock()
    mock_session.session_id = "test-uuid-1234"
    mock_session.case_id = case.id
    mock_session.document_type = ""
    mock_session.status = "active"
    mock_session.metadata = {}
    mock_session.created_at = "2026-01-01T00:00:00Z"
    mock_session.updated_at = "2026-01-01T00:00:00Z"

    mock_svc = MagicMock()
    mock_svc.create_session.return_value = mock_session
    mock_svc.get_recommended_document_types.return_value = []
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/litigation/sessions",
        data=json.dumps({"case_id": case.id}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "test-uuid-1234"
    assert data["case_id"] == case.id


@pytest.mark.django_db
@patch("apps.litigation_ai.api.litigation_api._get_conversation_service")
def test_list_litigation_sessions(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.list_sessions.return_value = {"total": 0, "sessions": []}
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/litigation/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


@pytest.mark.django_db
@patch("apps.litigation_ai.api.litigation_api._get_conversation_service")
def test_get_litigation_session(mock_get_svc, authenticated_client):
    mock_session = MagicMock()
    mock_session.session_id = "test-uuid"
    mock_session.case_id = 1
    mock_session.document_type = "complaint"
    mock_session.status = "active"
    mock_session.metadata = {}
    mock_session.created_at = "2026-01-01T00:00:00Z"
    mock_session.updated_at = "2026-01-01T00:00:00Z"

    mock_svc = MagicMock()
    mock_svc.get_session.return_value = mock_session
    mock_svc.get_messages.return_value = []
    mock_svc.get_recommended_document_types.return_value = []
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/litigation/sessions/test-uuid")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "test-uuid"


@pytest.mark.django_db
@patch("apps.litigation_ai.api.litigation_api._get_conversation_service")
def test_get_litigation_messages(mock_get_svc, authenticated_client):
    mock_msg = MagicMock()
    mock_msg.id = 1
    mock_msg.role = "user"
    mock_msg.content = "test message"
    mock_msg.metadata = {}
    mock_msg.created_at = "2026-01-01T00:00:00Z"

    mock_svc = MagicMock()
    mock_svc.get_messages.return_value = [mock_msg]
    mock_svc.get_message_count.return_value = 1
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/litigation/sessions/test-uuid/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["messages"]) == 1


@pytest.mark.django_db
@patch("apps.litigation_ai.api.litigation_api._get_conversation_service")
def test_update_litigation_session_status(mock_get_svc, authenticated_client):
    mock_session = MagicMock()
    mock_session.session_id = "test-uuid"
    mock_session.case_id = 1
    mock_session.document_type = ""
    mock_session.status = "completed"
    mock_session.metadata = {}
    mock_session.created_at = "2026-01-01T00:00:00Z"
    mock_session.updated_at = "2026-01-01T00:00:00Z"

    mock_svc = MagicMock()
    mock_svc.update_session_status.return_value = mock_session
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.patch(
        "/api/v1/litigation/sessions/test-uuid",
        data=json.dumps({"status": "completed"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.django_db
@patch("apps.litigation_ai.api.litigation_api._get_conversation_service")
def test_delete_litigation_session(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.delete_session.return_value = None
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.delete("/api/v1/litigation/sessions/test-uuid")
    assert resp.status_code == 204


# ===================================================================
# Litigation document generation
# ===================================================================


@pytest.mark.django_db
@patch("apps.litigation_ai.api.litigation_api._get_document_generator_service")
@patch("apps.litigation_ai.api.litigation_api._get_conversation_service")
def test_generate_document(mock_get_conv, mock_get_doc, authenticated_client):
    mock_conv_svc = MagicMock()
    mock_conv_svc.get_session.return_value = MagicMock()
    mock_get_conv.return_value = mock_conv_svc

    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.document_name = "起诉状.docx"
    mock_task.document_url = "http://example.com/doc.docx"
    mock_task.status = "completed"
    mock_task.created_at = "2026-01-01T00:00:00Z"
    mock_doc_svc = MagicMock()
    mock_doc_svc.generate_document.return_value = mock_task
    mock_get_doc.return_value = mock_doc_svc

    resp = authenticated_client.post(
        "/api/v1/litigation/sessions/test-uuid/generate",
        data=json.dumps({"template_id": 1}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == 1


# ===================================================================
# Mock trial sessions
# ===================================================================


@pytest.mark.django_db
@patch("apps.litigation_ai.api.mock_trial_api._get_service")
def test_create_mock_trial_session(mock_get_svc, authenticated_client):
    case = _make_case()
    mock_session = MagicMock()
    mock_session.session_id = "mock-uuid-1234"
    mock_session.case_id = case.id
    mock_session.status = "active"
    mock_session.metadata = {}
    mock_session.created_at = "2026-01-01T00:00:00Z"
    mock_session.updated_at = "2026-01-01T00:00:00Z"

    mock_svc = MagicMock()
    mock_svc.create_session.return_value = mock_session
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/mock-trial/sessions",
        data=json.dumps({"case_id": case.id}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_type"] == "mock_trial"


@pytest.mark.django_db
@patch("apps.litigation_ai.api.mock_trial_api._get_service")
def test_list_mock_trial_sessions(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.list_sessions.return_value = {"total": 0, "sessions": []}
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/mock-trial/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


@pytest.mark.django_db
@patch("apps.litigation_ai.api.mock_trial_api._get_service")
def test_get_mock_trial_session(mock_get_svc, authenticated_client):
    mock_session = MagicMock()
    mock_session.session_id = "mock-uuid"
    mock_session.case_id = 1
    mock_session.status = "active"
    mock_session.metadata = {}
    mock_session.created_at = "2026-01-01T00:00:00Z"
    mock_session.updated_at = "2026-01-01T00:00:00Z"

    mock_svc = MagicMock()
    mock_svc.get_session.return_value = mock_session
    mock_svc.get_messages.return_value = []
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/mock-trial/sessions/mock-uuid")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_type"] == "mock_trial"


@pytest.mark.django_db
@patch("apps.litigation_ai.api.mock_trial_api._get_service")
def test_delete_mock_trial_session(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.delete_session.return_value = None
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.delete("/api/v1/mock-trial/sessions/mock-uuid")
    assert resp.status_code == 204
