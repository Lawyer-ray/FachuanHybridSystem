from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS
from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReference
from apps.cases.models import Case, CaseLog, CaseLogAttachment
from apps.organization.models import LawFirm, Lawyer


@pytest.mark.django_db
def test_court_sms_list_endpoint_returns_paged_contract(authenticated_client) -> None:
    initial_count = CourtSMS.objects.count()
    now = timezone.now()
    CourtSMS.objects.create(content="法院短信A", received_at=now)
    CourtSMS.objects.create(content="法院短信B", received_at=now + timedelta(seconds=1))

    response = authenticated_client.get("/api/v1/automation/court-sms")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"items", "count"}
    assert data["count"] == initial_count + 2
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 2
    assert [item["content"] for item in data["items"]] == ["法院短信B", "法院短信A"]
    assert set(data["items"][0].keys()) >= {
        "id",
        "content",
        "received_at",
        "status",
        "has_documents",
        "feishu_sent",
        "created_at",
    }


@pytest.mark.django_db
def test_court_sms_detail_endpoint_exposes_archive_diagnostics(authenticated_client) -> None:
    sms = CourtSMS.objects.create(
        content="法院送达短信",
        received_at=timezone.now(),
        status="matching",
    )

    references = [
        CourtSMSDocumentReference(
            display_name="（2026）粤0101民初123号-判决书.pdf",
            file_path="D:/mock/judgment.pdf",
            source="case_log_attachment",
            original_name="判决书.pdf",
            archived_subdir="4-法院送达材料/5-其他材料",
            recommended_subdir="4-法院送达材料/4-裁定书、判决书、通知书",
            recommendation_reason="court_sms_judgment_notice_match",
        )
    ]

    with patch(
        "apps.automation.schemas.court_sms.CourtSMSDocumentReferenceService.collect",
        return_value=references,
    ):
        response = authenticated_client.get(f"/api/v1/automation/court-sms/{sms.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sms.id
    assert len(data["documents"]) == 1
    assert data["documents"][0] == {
        "id": None,
        "name": "（2026）粤0101民初123号-判决书.pdf",
        "source": "case_log_attachment",
        "download_url": None,
        "original_name": "判决书.pdf",
        "archived_subdir": "4-法院送达材料/5-其他材料",
        "recommended_subdir": "4-法院送达材料/4-裁定书、判决书、通知书",
        "recommendation_reason": "court_sms_judgment_notice_match",
    }


def test_court_sms_openapi_contract_matches_runtime_schema() -> None:
    from apiSystem.api import api_v1

    schema = api_v1.get_openapi_schema()

    submit_in = schema["components"]["schemas"]["CourtSMSSubmitIn"]
    submit_props = submit_in["properties"]
    assert "sender" not in submit_props

    detail_out = schema["components"]["schemas"]["CourtSMSDetailOut"]
    assert "sender" not in detail_out["properties"]
    documents_schema = detail_out["properties"]["documents"]
    assert documents_schema["type"] == "array"
    assert documents_schema["items"]["type"] == "object"
    assert documents_schema["items"]["additionalProperties"] is True

    form_props = (
        schema["paths"]["/api/v1/automation/court-sms/form"]["post"]["requestBody"]["content"][
            "application/x-www-form-urlencoded"
        ]["schema"]["properties"]
    )
    assert "sender" not in form_props

    list_response_schema = schema["paths"]["/api/v1/automation/court-sms"]["get"]["responses"][200]["content"][
        "application/json"
    ]["schema"]
    assert list_response_schema["$ref"] == "#/components/schemas/PagedCourtSMSListOut"

    paged_schema = schema["components"]["schemas"]["PagedCourtSMSListOut"]
    assert set(paged_schema["required"]) == {"items", "count"}
    assert "page" not in paged_schema["properties"]
    assert "page_size" not in paged_schema["properties"]


@pytest.mark.django_db
def test_court_sms_detail_endpoint_recognizes_case_folder_attachment_archive_diagnostics(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    firm = LawFirm.objects.create(name="测试律所")
    actor = Lawyer.objects.create_user(
        username="court-sms-detail-case-folder",
        password="testpass123",
        law_firm=firm,
        is_admin=True,
    )
    case = Case.objects.create(name="测试案件", case_type="civil", current_stage="first_trial")
    log = CaseLog.objects.create(case=case, actor=actor, content="法院短信日志")
    sms = CourtSMS.objects.create(
        content="法院送达短信",
        received_at=timezone.now(),
        status="matching",
        case=case,
        case_log=log,
        document_file_paths=[],
    )

    business_root = tmp_path / "case-root"
    archived_dir = business_root / "一审" / "法院送达材料" / "受理通知书"
    archived_dir.mkdir(parents=True)
    archived_file = archived_dir / "案件受理通知书.pdf"
    archived_file.write_bytes(b"pdf-bytes")

    CaseLogAttachment.objects.create(
        log=log,
        file="一审/法院送达材料/受理通知书/案件受理通知书.pdf",
        storage_root_type="case_folder",
        subdir_path="一审/法院送达材料/受理通知书",
        relative_file_path="一审/法院送达材料/受理通知书/案件受理通知书.pdf",
        original_filename="案件受理通知书.pdf",
    )

    monkeypatch.setattr(
        "apps.core.services.business_file_storage_service.BusinessFileStorageService._get_case_folder_root",
        lambda self, *, case_id, require_writable: business_root,
    )

    with patch(
        "apps.automation.services.sms.court_sms_document_reference_service.CaseLogAttachmentStorageService.recommend_attachment_subdir",
        return_value={
            "recommended_subdir": "一审/法院送达材料/受理通知书",
            "reason": "court_sms_acceptance_match",
        },
    ):
        response = authenticated_client.get(f"/api/v1/automation/court-sms/{sms.id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data["documents"]) == 1
    assert data["documents"][0] == {
        "id": None,
        "name": "案件受理通知书.pdf",
        "source": "case_log_attachment",
        "download_url": None,
        "original_name": "案件受理通知书.pdf",
        "archived_subdir": "一审/法院送达材料/受理通知书",
        "recommended_subdir": "一审/法院送达材料/受理通知书",
        "recommendation_reason": "court_sms_acceptance_match",
    }
