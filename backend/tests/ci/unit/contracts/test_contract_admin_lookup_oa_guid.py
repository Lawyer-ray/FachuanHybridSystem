"""ContractAdmin.lookup_oa_guid_view 单测（案号查 GUID 的 admin 端点）。

覆盖：方法限制、权限、参数校验、调度结果透传与 OA 错误返回。
调度器本身打桩（见 test_jtn_case_guid.py 的执行器层单测）。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.contracts.admin.contract_admin import ContractAdmin
from apps.contracts.models import Contract
from apps.organization.models import Lawyer

_CASE_NO = "2026TEST0001"
_GUID = "b0219b56-3968-48a8-8e12-3ca86bf160ce"


def _make_superuser() -> Lawyer:
    return Lawyer.objects.create_user(username="guid_lookup_admin", real_name="查询管理员", is_superuser=True)  # type: ignore[no-any-return]


def _make_staff_no_perm() -> Lawyer:
    return Lawyer.objects.create_user(username="guid_lookup_staff", real_name="无权限员工", is_staff=True)  # type: ignore[no-any-return]


def _post_request(user: Lawyer, contract_id: int, body: Any) -> Any:
    request = RequestFactory().post(
        f"/admin/contracts/contract/{contract_id}/lookup-oa-guid/",
        data=json.dumps(body),
        content_type="application/json",
    )
    request.user = user
    return request


@pytest.mark.django_db
class TestLookupOaGuidView:
    def _view(self) -> ContractAdmin:
        return ContractAdmin(Contract, AdminSite())

    def test_get_not_allowed(self):
        request = RequestFactory().get("/admin/contracts/contract/1/lookup-oa-guid/")
        request.user = _make_superuser()
        resp = self._view().lookup_oa_guid_view(request, 1)
        assert resp.status_code == 405
        assert json.loads(resp.content) == {"ok": False, "error": "Method not allowed"}

    def test_permission_denied_for_staff_without_change_perm(self):
        request = _post_request(_make_staff_no_perm(), 1, {"case_no": _CASE_NO})
        resp = self._view().lookup_oa_guid_view(request, 1)
        assert resp.status_code == 403
        assert json.loads(resp.content) == {"ok": False, "error": "Permission denied"}

    def test_missing_case_no_rejected(self):
        contract = Contract.objects.create(name="利冲合同", case_type="civil")
        request = _post_request(_make_superuser(), contract.pk, {"case_no": "  "})
        resp = self._view().lookup_oa_guid_view(request, contract.pk)
        assert resp.status_code == 400
        assert json.loads(resp.content) == {"ok": False, "error": "请先填写律所OA案件编号"}

    def test_invalid_json_rejected(self):
        request = RequestFactory().post(
            "/admin/contracts/contract/1/lookup-oa-guid/",
            data="not-json",
            content_type="application/json",
        )
        request.user = _make_superuser()
        resp = self._view().lookup_oa_guid_view(request, 1)
        assert resp.status_code == 400
        assert json.loads(resp.content) == {"ok": False, "error": "请求体不是合法 JSON"}

    def test_success_returns_guids(self):
        contract = Contract.objects.create(name="利冲合同2", case_type="civil")
        request = _post_request(_make_superuser(), contract.pk, {"case_no": _CASE_NO})

        with patch(
            "apps.oa_filing.services.script_executor_service.ScriptExecutorService.lookup_oa_case_guid",
            return_value=[_GUID],
        ) as mock_lookup:
            resp = self._view().lookup_oa_guid_view(request, contract.pk)

        payload = json.loads(resp.content)
        assert payload == {"ok": True, "guids": [_GUID]}
        mock_lookup.assert_called_once_with(case_no=_CASE_NO, user=request.user)

    def test_runtime_error_returned_as_business_failure(self):
        contract = Contract.objects.create(name="利冲合同3", case_type="civil")
        request = _post_request(_make_superuser(), contract.pk, {"case_no": _CASE_NO})

        with patch(
            "apps.oa_filing.services.script_executor_service.ScriptExecutorService.lookup_oa_case_guid",
            side_effect=RuntimeError("连接 OA 系统超时，请检查 VPN 是否已连接后重试"),
        ):
            resp = self._view().lookup_oa_guid_view(request, contract.pk)

        payload = json.loads(resp.content)
        assert payload["ok"] is False
        assert "VPN" in payload["error"]

    def test_zero_hit_is_ok_with_empty_list(self):
        contract = Contract.objects.create(name="利冲合同4", case_type="civil")
        request = _post_request(_make_superuser(), contract.pk, {"case_no": _CASE_NO})

        with patch(
            "apps.oa_filing.services.script_executor_service.ScriptExecutorService.lookup_oa_case_guid",
            return_value=[],
        ):
            resp = self._view().lookup_oa_guid_view(request, contract.pk)

        payload = json.loads(resp.content)
        assert payload == {"ok": True, "guids": []}
