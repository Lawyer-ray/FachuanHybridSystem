from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client, RequestFactory
from django.utils import timezone

from apps.automation.admin.sms.court_sms_admin import CourtSMSAdmin
from apps.automation.models import CourtSMS
from apps.cases.models import Case
from apps.organization.models import LawFirm, Lawyer


@pytest.mark.django_db
def test_court_sms_admin_add_starts_processing_task(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = CourtSMSAdmin(CourtSMS, AdminSite())
    firm = LawFirm.objects.create(name="娴嬭瘯寰嬫墍")
    user = Lawyer.objects.create_user(
        username="courtsms-admin",
        password="placeholder-password",
        law_firm=firm,
        is_admin=True,
    )

    request = RequestFactory().post(
        "/admin/automation/courtsms/add/",
        data={"content": "娴嬭瘯娉曢櫌鐭俊", "received_at": timezone.now().isoformat()},
    )
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)

    monkeypatch.setattr(
        "apps.automation.admin.sms.court_sms_admin_actions.submit_task",
        lambda *args, **kwargs: "task-courtsms-001",
        raising=False,
    )
    obj = CourtSMS(content="娴嬭瘯娉曢櫌鐭俊", received_at=timezone.now())
    admin.save_model(request, obj, form=None, change=False)

    messages = [message.message for message in get_messages(request)]
    assert messages


@pytest.mark.django_db
def test_court_sms_admin_change_view_uses_open_access_for_archive_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firm = LawFirm.objects.create(name="娴嬭瘯寰嬫墍")
    user = Lawyer.objects.create_user(
        username="courtsms-admin-change",
        password="placeholder-password",
        law_firm=firm,
        is_admin=True,
        is_staff=True,
        is_superuser=True,
    )
    case = Case.objects.create(name="娴嬭瘯妗堜欢", case_type="civil", current_stage="first_trial")
    document_path = tmp_path / "acceptance_notice.pdf"
    document_path.write_bytes(b"pdf-bytes")
    sms = CourtSMS.objects.create(
        content="娉曢櫌閫佽揪鐭俊",
        received_at=timezone.now(),
        status="matching",
        case=case,
        document_file_paths=[str(document_path)],
    )

    captured_kwargs: dict[str, object] = {}

    def fake_recommend_attachment_subdir(self, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return {
            "recommended_subdir": "涓€瀹?/娉曢櫌閫佽揪鏉愭枡/鍙楃悊閫氱煡涔?",
            "reason": "court_sms_acceptance_match",
        }

    monkeypatch.setattr(
        "apps.automation.services.sms.court_sms_document_reference_service.CaseLogAttachmentStorageService.recommend_attachment_subdir",
        fake_recommend_attachment_subdir,
    )

    client = Client()
    client.force_login(user)
    response = client.get(f"/admin/automation/courtsms/{sms.id}/change/")

    assert response.status_code == 200
    assert captured_kwargs["case_id"] == case.id
    assert captured_kwargs["source_scene"] == "court_sms_attachment"
    assert captured_kwargs["perm_open_access"] is True
