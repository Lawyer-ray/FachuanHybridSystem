from __future__ import annotations

from unittest.mock import Mock

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.cases.admin.case_admin import CaseAdmin
from apps.cases.models import Case
from apps.core.models.enums import ChatPlatform


def test_create_feishu_chat_action_passes_request_access_context(monkeypatch) -> None:
    case = Mock(spec=Case)
    case.id = 123
    case.name = "案件A"
    case.chats.filter.return_value.first.return_value = None

    admin = CaseAdmin(Case, AdminSite())
    service = Mock()
    service.create_chat_for_case.return_value = Mock(name="群聊A")
    monkeypatch.setattr(admin, "_get_case_chat_service", lambda: service)

    request = RequestFactory().post("/admin/cases/case/")
    request.user = Mock()
    request.org_access = {"extra_cases": {123}}
    request.perm_open_access = False
    setattr(request, "session", {})
    setattr(request, "_messages", FallbackStorage(request))

    admin.create_feishu_chat_for_selected_cases(request, [case])

    service.create_chat_for_case.assert_called_once_with(
        123,
        ChatPlatform.FEISHU,
        user=request.user,
        org_access=request.org_access,
        perm_open_access=False,
    )
