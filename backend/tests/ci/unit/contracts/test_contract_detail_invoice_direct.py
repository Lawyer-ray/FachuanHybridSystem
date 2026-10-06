"""合同详情页「申请开票」直开注入测试。

律所ID（law_firm_oa_guid）机制下的申请开票：有律所ID → 前端直接拼接
OA 开票页 URL 新标签打开（用户浏览器自带网关会话）；无律所ID → 回退
服务端 Playwright 备用链路。本文件验证 detail 页模板按合同状态正确注入。
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory

from apps.contracts.admin.contract_admin import ContractAdmin
from apps.contracts.models import Contract
from apps.organization.models import Lawyer

User = Lawyer

_GUID = "e2871487-5c3f-463f-98c8-876f3e11c995"


def _make_admin(username: str) -> Lawyer:
    """is_admin（行级豁免）+ view_contract（Django 模块权限）双重满足。"""
    user = Lawyer.objects.create_user(username=username, real_name="管理员", is_staff=True, is_admin=True)
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="contracts", codename="view_contract"),
    )
    return User.objects.get(pk=user.pk)  # type: ignore[no-any-return]


def _render_detail(contract: Contract, user: Lawyer) -> str:
    request = RequestFactory().get(f"/admin/contracts/contract/{contract.pk}/detail/")

    def _get_response(req: Any) -> HttpResponse:
        return HttpResponse()

    SessionMiddleware(_get_response).process_request(request)  # detail_view 读 session（返回列表筛选）
    request.user = user
    response = ContractAdmin(Contract, AdminSite()).detail_view(request, contract.pk)
    content = getattr(response, "content", None)
    if not content:
        # TemplateResponse 未显式渲染时取渲染结果（detail_view 返回类型标注为 HttpResponse）
        render = getattr(response, "render", None)
        content = render().content if callable(render) else b""
    return (content or b"").decode("utf-8")


@pytest.mark.django_db
class TestInvoiceDirectInjection:
    def test_detail_with_guid_injects_direct_url(self):
        """有律所ID：detail 页注入直开 URL（ProjectID=GUID + FINANCE 参数）。"""
        contract = Contract.objects.create(
            name="开票直开合同", case_type="civil", law_firm_oa_case_number="2026TEST0001", law_firm_oa_guid=_GUID
        )
        staff = _make_admin("inv_direct_admin")
        html = _render_detail(contract, staff)

        assert "FapiaoRequestReg.aspx?ProjectID=" in html
        # escapejs 将连字符转义为 \u002D（JS 解析后等价），断言前缀与转义形态
        assert "e2871487" in html
        assert "\\u002D" in html
        assert "FirstModel=FINANCE" in html
        assert "openInvoicePage" in html

    def test_detail_without_guid_keeps_fallback(self):
        """无律所ID：不注入 GUID URL，保留备用链路 fetch 调用。"""
        contract = Contract.objects.create(name="无律所ID合同", case_type="civil")
        staff = _make_admin("inv_fallback_admin")
        html = _render_detail(contract, staff)

        assert "FapiaoRequestReg.aspx?ProjectID=" in html  # URL 模板恒在，由空 GUID 令其失效
        assert "oa-archive/open-invoice" in html  # 备用链路保留
        assert _GUID not in html
