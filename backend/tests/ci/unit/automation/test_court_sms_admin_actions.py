from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.utils import timezone

from apps.automation.admin.sms.court_sms_admin import CourtSMSAdmin
from apps.automation.models import CourtSMS
from apps.organization.models import LawFirm, Lawyer


@pytest.mark.django_db
def test_court_sms_admin_add_warns_when_qcluster_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = CourtSMSAdmin(CourtSMS, AdminSite())
    firm = LawFirm.objects.create(name="测试律所")
    user = Lawyer.objects.create_user(username="courtsms-admin", password="testpass123", law_firm=firm, is_admin=True)

    request = RequestFactory().post(
        "/admin/automation/courtsms/add/",
        data={"content": "测试法院短信", "received_at": timezone.now().isoformat()},
    )
    request.user = user
    setattr(request, "session", {})
    setattr(request, "_messages", FallbackStorage(request))

    monkeypatch.setattr(
        "apps.automation.admin.sms.court_sms_admin_actions.submit_task",
        lambda *args, **kwargs: "task-courtsms-001",
        raising=False,
    )
    monkeypatch.setattr(
        "apps.automation.admin.sms.court_sms_admin_actions._task_query_service.has_active_cluster",
        lambda: False,
    )

    obj = CourtSMS(content="测试法院短信", received_at=timezone.now())
    admin.save_model(request, obj, form=None, change=False)

    messages = [message.message for message in get_messages(request)]
    assert any("短信已保存并开始处理" in message for message in messages)
    assert any("未检测到正在运行的 qcluster" in message for message in messages)
