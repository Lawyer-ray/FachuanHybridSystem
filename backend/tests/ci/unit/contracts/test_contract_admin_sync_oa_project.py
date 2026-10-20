"""ContractAdmin.sync_oa_project_view 单测（律所ID「同步」按钮的 admin 端点）。

覆盖：方法限制、权限、参数校验（空 / 非 JSON / 非 UUID）、GUID 规范化透传、
调度结果经 build_sync_payload 整形后返回、OA 业务错误按 ok=false 返回、URL 解析。
调度器本身打桩（见 test_jtn_case_guid.py 的脚本层与执行器层单测）。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.client.models import Client
from apps.contracts.admin.contract_admin import ContractAdmin
from apps.contracts.models import Contract
from apps.oa_filing.services.oa_data_models import OACaseCustomerData, OACaseData, OACaseInfoData, OAConflictData
from apps.organization.models import Lawyer

_URL = "/admin/contracts/contract/sync-oa-project/"
_GUID = "b0219b56-3968-48a8-8e12-3ca86bf160ce"
_EXECUTOR_PATH = "apps.oa_filing.services.script_executor_service.ScriptExecutorService.fetch_oa_project_detail"


def _make_superuser() -> Lawyer:
    return Lawyer.objects.create_user(username="oa_sync_admin", real_name="同步管理员", is_superuser=True)  # type: ignore[no-any-return]


def _make_staff_no_perm() -> Lawyer:
    return Lawyer.objects.create_user(username="oa_sync_staff", real_name="无权限员工", is_staff=True)  # type: ignore[no-any-return]


def _post_request(user: Lawyer, body: Any) -> Any:
    request = RequestFactory().post(_URL, data=json.dumps(body), content_type="application/json")
    request.user = user
    return request


def _oa_detail() -> OACaseData:
    return OACaseData(
        case_no="",
        keyid=_GUID,
        customers=[OACaseCustomerData(name="甲公司", customer_type="legal")],
        case_info=OACaseInfoData(
            case_no="CASE-2026-0001",
            case_name="甲公司诉乙某合同纠纷案",
            case_stage="一审",
            acceptance_date="2026/10/19",
            case_category="民商事",
            case_type="合同纠纷",
            responsible_lawyer="测试律师",
            client_side="原告",
        ),
        conflicts=[OAConflictData(name="乙某", conflict_type="被告")],
    )


@pytest.mark.django_db
class TestSyncOaProjectView:
    def _view(self) -> ContractAdmin:
        return ContractAdmin(Contract, AdminSite())

    def test_url_resolves_add_route(self):
        from django.urls import reverse

        assert reverse("admin:contracts_contract_sync_oa_project_add").endswith("/contract/sync-oa-project/")

    def test_get_not_allowed(self):
        request = RequestFactory().get(_URL)
        request.user = _make_superuser()
        resp = self._view().sync_oa_project_view(request)
        assert resp.status_code == 405
        assert json.loads(resp.content) == {"ok": False, "error": "Method not allowed"}

    def test_permission_denied_for_staff_without_change_perm(self):
        resp = self._view().sync_oa_project_view(_post_request(_make_staff_no_perm(), {"guid": _GUID}))
        assert resp.status_code == 403
        assert json.loads(resp.content) == {"ok": False, "error": "Permission denied"}

    def test_invalid_json_rejected(self):
        request = RequestFactory().post(_URL, data="not-json", content_type="application/json")
        request.user = _make_superuser()
        resp = self._view().sync_oa_project_view(request)
        assert resp.status_code == 400
        assert json.loads(resp.content) == {"ok": False, "error": "请求体不是合法 JSON"}

    @pytest.mark.parametrize("body", [{}, {"guid": ""}, {"guid": "   "}])
    def test_missing_guid_rejected(self, body):
        resp = self._view().sync_oa_project_view(_post_request(_make_superuser(), body))
        assert resp.status_code == 400
        assert json.loads(resp.content)["ok"] is False
        assert "请先填写律所ID" in json.loads(resp.content)["error"]

    @pytest.mark.parametrize("bad", ["not-a-guid", "CASE-2026-0001", "b0219b56-3968-48a8-8e12", "<script>"])
    def test_non_uuid_guid_rejected_before_reaching_oa(self, bad):
        """格式不对直接 400，不打到 OA（keyid 要拼 URL，这是体验层的第一道闸）。"""
        with patch(_EXECUTOR_PATH) as mock_fetch:
            resp = self._view().sync_oa_project_view(_post_request(_make_superuser(), {"guid": bad}))
        assert resp.status_code == 400
        assert json.loads(resp.content) == {"ok": False, "error": "律所ID 格式不正确，应为 OA 案件 GUID"}
        mock_fetch.assert_not_called()

    def test_success_returns_form_payload(self):
        request = _post_request(_make_superuser(), {"guid": _GUID})
        with patch(_EXECUTOR_PATH, return_value=_oa_detail()) as mock_fetch:
            resp = self._view().sync_oa_project_view(request)

        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload["ok"] is True
        data = payload["data"]
        assert data["guid"] == _GUID
        assert data["name"] == "甲公司诉乙某合同纠纷案"
        assert data["case_type"] == "civil"
        assert data["start_date"] == "2026-10-19"
        assert data["case_number"] == "CASE-2026-0001"
        assert data["detail_url"].endswith(f"projectView.aspx?keyid={_GUID}&FirstModel=PROJECT&SecondModel=PROJECT002")
        assert data["responsible_lawyer"] == "测试律师"
        assert [c["name"] for c in data["clients"]] == ["甲公司"]
        assert [c["name"] for c in data["opponents"]] == ["乙某"]
        assert data["auto_create_allowed"] is True
        mock_fetch.assert_called_once_with(keyid=_GUID, user=request.user)

    def test_missing_parties_are_created_with_correct_flags(self):
        """OA 有、本地没有的当事人自动建库：委托人＝我方，利冲相关方＝非我方。"""
        detail = OACaseData(
            case_no="",
            keyid=_GUID,
            customers=[OACaseCustomerData(name="甲公司", customer_type="legal")],
            case_info=OACaseInfoData(case_no="CASE-2026-0001", client_side="被告"),
            conflicts=[
                OAConflictData(name="乙公司", conflict_type="原告"),
                OAConflictData(name="同案被告丙", conflict_type="被告"),
            ],
        )
        with patch(_EXECUTOR_PATH, return_value=detail):
            resp = self._view().sync_oa_project_view(_post_request(_make_superuser(), {"guid": _GUID}))

        assert resp.status_code == 200
        data = json.loads(resp.content)["data"]
        our_client = Client.objects.get(pk=data["clients"][0]["client_id"])
        opponent = Client.objects.get(pk=data["opponents"][0]["client_id"])
        co_party = Client.objects.get(pk=data["co_parties"][0]["client_id"])
        assert our_client.is_our_client is True
        assert opponent.is_our_client is False
        assert co_party.is_our_client is False
        assert data["co_parties"][0]["created"] is True

    def test_without_add_client_permission_does_not_create_parties(self):
        """有合同修改权但没有当事人新增权：同步照常返回名单，只是不落库。"""
        from django.contrib.auth.models import Permission

        user = Lawyer.objects.create_user(username="oa_sync_editor", real_name="合同编辑", is_staff=True)  # type: ignore[no-any-return]
        user.user_permissions.add(Permission.objects.get(codename="change_contract"))

        with patch(_EXECUTOR_PATH, return_value=_oa_detail()):
            resp = self._view().sync_oa_project_view(_post_request(user, {"guid": _GUID}))

        assert resp.status_code == 200
        data = json.loads(resp.content)["data"]
        assert data["auto_create_allowed"] is False
        assert data["clients"][0]["client_id"] is None
        assert data["opponents"][0]["client_id"] is None
        assert Client.objects.count() == 0

    def test_guid_normalized_before_dispatch(self):
        """大写 / 花括号 / 空白的 GUID 规范化成标准小写再交给调度器。"""
        request = _post_request(_make_superuser(), {"guid": "  {" + _GUID.upper() + "}  "})
        with patch(_EXECUTOR_PATH, return_value=_oa_detail()) as mock_fetch:
            resp = self._view().sync_oa_project_view(request)

        assert json.loads(resp.content)["ok"] is True
        mock_fetch.assert_called_once_with(keyid=_GUID, user=request.user)

    def test_runtime_error_returned_as_business_failure(self):
        request = _post_request(_make_superuser(), {"guid": _GUID})
        with patch(
            _EXECUTOR_PATH, side_effect=RuntimeError("未读到 OA 案件详情：律所ID 无效，或当前 OA 账号无权查看该案件")
        ):
            resp = self._view().sync_oa_project_view(request)

        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload["ok"] is False
        assert "无权查看" in payload["error"]
