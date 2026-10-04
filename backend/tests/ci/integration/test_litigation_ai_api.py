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
    mock_svc.list_sessions.return_value = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "total_pages": 1,
    }
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/litigation/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.django_db
def test_list_litigation_sessions_envelope_and_page_size_cap(authenticated_client):
    """真实 DB：标准信封结构 + page_size cap（>100 收敛到 100）。"""
    from apps.organization.models import Lawyer

    user = Lawyer.objects.get(username="testuser")
    contract = Contract.objects.create(name="分页上限合同", case_type="civil")
    case = Case.objects.create(name="分页上限案件", contract=contract)
    for _ in range(3):
        LitigationSession.objects.create(case=case, user=user)

    resp = authenticated_client.get("/api/v1/litigation/sessions?page=1&page_size=999")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 3
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 100  # cap 生效
    assert data["total_pages"] == 1


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
    # 服务层按 URL 中的 session_id 与当前用户执行删除
    args = mock_svc.delete_session.call_args.args
    assert args[0] == "test-uuid"


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
    mock_svc.list_sessions.return_value = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "total_pages": 1,
    }
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/mock-trial/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page_size"] == 20
    assert data["total_pages"] == 1


@pytest.mark.django_db
def test_list_mock_trial_sessions_envelope_and_page_size_cap(authenticated_client):
    """真实 DB：标准信封结构 + page_size cap（>100 收敛到 100），且仅返回 mock_trial 会话。"""
    from apps.organization.models import Lawyer

    user = Lawyer.objects.get(username="testuser")
    contract = Contract.objects.create(name="庭审上限合同", case_type="civil")
    case = Case.objects.create(name="庭审上限案件", contract=contract)
    for _ in range(2):
        LitigationSession.objects.create(case=case, user=user, session_type="mock_trial")
    LitigationSession.objects.create(case=case, user=user)  # doc_gen 会话不应混入

    resp = authenticated_client.get("/api/v1/mock-trial/sessions?page=1&page_size=999")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 2
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 100  # cap 生效
    assert data["total_pages"] == 1


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
    args = mock_svc.delete_session.call_args.args
    assert args[0] == "mock-uuid"


# ===================================================================
# 会话创建案件归属校验（安全审计）
# ===================================================================


def _login_lawyer(username: str):
    """以普通（非 admin）律师身份登录的客户端。"""
    from django.test import Client

    from apps.organization.models import Lawyer

    user = Lawyer.objects.create_user(username=username, password="pass12345")
    client = Client()
    client.force_login(user)
    return client, user


def _make_assigned_case(owner):
    """建一个仅 owner 被指派的案件。"""
    from apps.cases.models import CaseAssignment

    case = _make_case()
    CaseAssignment.objects.create(case=case, lawyer=owner)
    return case


@pytest.mark.django_db
@patch("apps.litigation_ai.api.litigation_api._get_conversation_service")
def test_create_litigation_session_denied_for_others_case(mock_get_svc):
    """律师 A 对他人案件创建诉讼会话被拒（403）。"""
    owner_client, owner = _login_lawyer("lit_owner")
    case = _make_assigned_case(owner)
    intruder_client, _ = _login_lawyer("lit_intruder")

    resp = intruder_client.post(
        "/api/v1/litigation/sessions",
        data=json.dumps({"case_id": case.id}),
        content_type="application/json",
    )
    assert resp.status_code == 403
    mock_get_svc.assert_not_called()


@pytest.mark.django_db
@patch("apps.litigation_ai.api.litigation_api._get_conversation_service")
def test_create_litigation_session_allowed_for_assigned_lawyer(mock_get_svc):
    """被指派律师对案件创建诉讼会话不受影响。"""
    owner_client, owner = _login_lawyer("lit_owner2")
    case = _make_assigned_case(owner)

    mock_session = MagicMock()
    mock_session.session_id = "sid-ok"
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

    resp = owner_client.post(
        "/api/v1/litigation/sessions",
        data=json.dumps({"case_id": case.id}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "sid-ok"


@pytest.mark.django_db
@patch("apps.litigation_ai.api.mock_trial_api._get_service")
def test_create_mock_trial_session_denied_for_others_case(mock_get_svc):
    """律师 A 对他人案件创建模拟庭审会话被拒（403）。"""
    owner_client, owner = _login_lawyer("mt_owner")
    case = _make_assigned_case(owner)
    intruder_client, _ = _login_lawyer("mt_intruder")

    resp = intruder_client.post(
        "/api/v1/mock-trial/sessions",
        data=json.dumps({"case_id": case.id}),
        content_type="application/json",
    )
    assert resp.status_code == 403
    mock_get_svc.assert_not_called()


# ===================================================================
# 模拟庭审导出：案件归属 + 文件名编码（安全审计）
# ===================================================================


@pytest.mark.django_db
@patch("apps.litigation_ai.api.mock_trial_api._get_service")
def test_export_report_denied_for_others_case(mock_get_svc):
    """会话属主校验之外：对他人案件的会话导出被拒（403）。"""
    owner_client, owner = _login_lawyer("mt_export_owner")
    case = _make_assigned_case(owner)
    intruder_client, _ = _login_lawyer("mt_export_intruder")

    mock_session = MagicMock()
    mock_session.case_id = case.id
    mock_svc = MagicMock()
    mock_svc.get_session.return_value = mock_session
    mock_get_svc.return_value = mock_svc

    resp = intruder_client.get("/api/v1/mock-trial/sessions/mock-uuid/export")
    assert resp.status_code == 403
    # 越权请求在报告生成前被拒，不得触达导出逻辑
    mock_svc.get_session.assert_called_once()


@pytest.mark.django_db
@patch("apps.litigation_ai.api.mock_trial_api._get_service")
def test_export_report_filename_quoted(mock_get_svc, authenticated_client, tmp_path):
    """案件名含引号/非 ASCII 时 Content-Disposition 正确百分号编码，不炸头。"""
    from types import SimpleNamespace

    contract = Contract.objects.create(name="导出合同", case_type="civil")
    case = Case.objects.create(name="案件X", contract=contract)

    mock_session = MagicMock()
    mock_session.case_id = case.id
    mock_svc = MagicMock()
    mock_svc.get_session.return_value = mock_session
    mock_get_svc.return_value = mock_svc

    docx = tmp_path / "report.docx"
    docx.write_bytes(b"PK-fake-docx")

    case_dto = SimpleNamespace(name='案件"引号"测试', cause_of_action="合同纠纷")
    with (
        patch(
            "apps.litigation_ai.services.mock_trial.report_service.MockTrialReportService.get_report",
            return_value={"mode": "standard"},
        ),
        patch(
            "apps.litigation_ai.services.flow.session_repository.LitigationSessionRepository.get_session_sync",
            return_value=MagicMock(case_id=case.id),
        ),
        patch(
            "apps.litigation_ai.services.wiring.get_case_service",
            return_value=MagicMock(get_case=MagicMock(return_value=case_dto)),
        ),
        patch(
            "apps.litigation_ai.services.mock_trial.export_service.MockTrialExportService.export_to_docx",
            return_value=str(docx),
        ),
    ):
        resp = authenticated_client.get("/api/v1/mock-trial/sessions/mock-uuid/export")

    assert resp.status_code == 200
    disposition = resp["Content-Disposition"]
    # 引号被百分号编码（%22），不再破坏头结构；同时提供 RFC 5987 filename* 形式
    assert "%22" in disposition
    assert "filename*=UTF-8''" in disposition
