"""Legal Research Admin 律所隔离测试（审计五-2 专项）.

覆盖：CaseDownloadTaskAdmin 列表的律所隔离、retry 视图的 has_change_permission 校验。
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.legal_research.admin.case_download_admin import CaseDownloadTaskAdmin
from apps.legal_research.models import CaseDownloadTask
from apps.organization.models import AccountCredential, LawFirm, Lawyer

User = get_user_model()


def _make_firm_lawyer(suffix: str) -> tuple[LawFirm, Lawyer]:
    firm = LawFirm.objects.create(name=f"隔离测试律所{suffix}")
    lawyer = Lawyer.objects.create_user(username=f"iso_{suffix}", real_name=f"隔离律师{suffix}", law_firm=firm)
    return firm, lawyer


def _make_task(owner: Lawyer, credential: AccountCredential, number: str) -> CaseDownloadTask:
    return CaseDownloadTask.objects.create(
        created_by=owner,
        credential=credential,
        case_numbers=number,
    )


def _make_request(path: str, user: Any) -> Any:
    request = RequestFactory().get(path)
    request.user = user
    request.session = "session"
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
class TestCaseDownloadTaskAdminLawFirmIsolation:
    """CaseDownloadTaskAdmin 的律所隔离"""

    def test_get_queryset_isolated_by_law_firm(self) -> None:
        """非 superuser 仅可见本所（创建人/凭证归属）任务"""
        _, lawyer_a = _make_firm_lawyer("a")
        _, lawyer_b = _make_firm_lawyer("b")
        cred_a = AccountCredential.objects.create(lawyer=lawyer_a, site_name="wkxx", account="a", password="x")
        cred_b = AccountCredential.objects.create(lawyer=lawyer_b, site_name="wkxx", account="b", password="x")
        mine = _make_task(lawyer_a, cred_a, "(2026)京01民初1号")
        _make_task(lawyer_b, cred_b, "(2026)京01民初2号")

        request = _make_request("/admin/legal_research/casedownloadtask/", lawyer_a)

        qs = CaseDownloadTaskAdmin(CaseDownloadTask, AdminSite()).get_queryset(request)
        assert set(qs.values_list("id", flat=True)) == {mine.pk}

    def test_get_queryset_superuser_sees_all(self) -> None:
        """superuser 不受律所隔离限制"""
        _, lawyer_a = _make_firm_lawyer("c")
        _, lawyer_b = _make_firm_lawyer("d")
        cred_a = AccountCredential.objects.create(lawyer=lawyer_a, site_name="wkxx", account="c", password="x")
        cred_b = AccountCredential.objects.create(lawyer=lawyer_b, site_name="wkxx", account="d", password="x")
        _make_task(lawyer_a, cred_a, "(2026)京01民初3号")
        _make_task(lawyer_b, cred_b, "(2026)京01民初4号")

        request = _make_request(
            "/admin/legal_research/casedownloadtask/",
            User(is_superuser=True, is_staff=True),
        )

        qs = CaseDownloadTaskAdmin(CaseDownloadTask, AdminSite()).get_queryset(request)
        assert qs.count() == 2

    def test_retry_view_denies_without_change_permission(self) -> None:
        """无 change 权限的用户访问 retry 视图 → 跳回列表（拒绝执行）"""
        _, lawyer_a = _make_firm_lawyer("e")
        cred_a = AccountCredential.objects.create(lawyer=lawyer_a, site_name="wkxx", account="e", password="x")
        task = _make_task(lawyer_a, cred_a, "(2026)京01民初5号")

        request = _make_request(f"/admin/legal_research/casedownloadtask/{task.pk}/retry/", lawyer_a)

        response = CaseDownloadTaskAdmin(CaseDownloadTask, AdminSite()).retry_view(request, str(task.pk))
        assert response.status_code == 302
        assert response.url.endswith("/admin/legal_research/casedownloadtask/")
