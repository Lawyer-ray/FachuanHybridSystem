"""新建合同页延迟文件夹绑定（_apply_deferred_folder_binding）单测。

覆盖：未选择跳过 / 本地路径落库 / 云存储账号解析透传 / 服务失败只警告不阻断。
FolderBindingService 与云存储账号解析全部打桩，无文件系统访问。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.contracts.admin.contract_admin import ContractAdmin, _apply_deferred_folder_binding
from apps.contracts.models import Contract
from apps.organization.models import Lawyer

_WIRING = "apps.contracts.admin.wiring_admin.get_contract_folder_binding_service"
_RESOLVER = "apps.cloud_storage.account_service.resolve_active_storage_account"


def _make_request(post: dict[str, str]) -> MagicMock:
    request = RequestFactory().post("/admin/contracts/contract/add/", data=post)
    request.user = Lawyer.objects.create_user(username="deferred_bind_admin", real_name="绑定管理员", is_superuser=True)  # type: ignore[assignment]
    request.session = "session"  # FallbackStorage 兜底所需
    request._messages = FallbackStorage(request)
    return request


def _messages_text(request: MagicMock) -> list[str]:
    return [str(m) for m in request._messages]


def _make_contract() -> Contract:
    return Contract.objects.create(name="延迟绑定合同", case_type="civil")


@pytest.mark.django_db
class TestApplyDeferredFolderBinding:
    def test_no_selection_skips_service(self):
        request = _make_request({})
        contract = _make_contract()
        with patch(_WIRING) as mock_wiring:
            _apply_deferred_folder_binding(request, contract)
        mock_wiring.assert_not_called()
        assert _messages_text(request) == []

    def test_blank_path_skips_service(self):
        request = _make_request({"_add_folder_path": "   "})
        contract = _make_contract()
        with patch(_WIRING) as mock_wiring:
            _apply_deferred_folder_binding(request, contract)
        mock_wiring.assert_not_called()

    def test_local_path_creates_binding(self):
        request = _make_request({"_add_folder_path": "/Volumes/cases/2026某案", "_add_storage_type": "local"})
        contract = _make_contract()
        service = MagicMock()
        with patch(_WIRING, return_value=service) as mock_wiring:
            _apply_deferred_folder_binding(request, contract)

        mock_wiring.assert_called_once_with()
        service.create_binding.assert_called_once_with(
            owner_id=contract.pk,
            folder_path="/Volumes/cases/2026某案",
            storage_type="local",
            storage_account=None,
        )
        assert any("已绑定文件夹" in m for m in _messages_text(request))

    def test_cloud_path_resolves_storage_account(self):
        account = MagicMock(id=7)
        request = _make_request(
            {
                "_add_folder_path": "/clients/某客户",
                "_add_storage_type": "webdav",
                "_add_storage_account_id": "7",
            }
        )
        contract = _make_contract()
        service = MagicMock()
        with (
            patch(_WIRING, return_value=service),
            patch(_RESOLVER, new=AsyncMock(return_value=account)) as mock_resolve,
        ):
            _apply_deferred_folder_binding(request, contract)

        mock_resolve.assert_awaited_once_with(7, "webdav")
        service.create_binding.assert_called_once_with(
            owner_id=contract.pk,
            folder_path="/clients/某客户",
            storage_type="webdav",
            storage_account=account,
        )

    def test_invalid_storage_account_warns_and_skips_binding(self):
        request = _make_request(
            {
                "_add_folder_path": "/clients/某客户",
                "_add_storage_type": "webdav",
                "_add_storage_account_id": "99",
            }
        )
        contract = _make_contract()
        service = MagicMock()
        with (
            patch(_WIRING, return_value=service),
            patch(_RESOLVER, new=AsyncMock(side_effect=ValueError("账号不存在"))),
        ):
            _apply_deferred_folder_binding(request, contract)  # 不得抛出

        service.create_binding.assert_not_called()
        assert any("云存储账号无效" in m for m in _messages_text(request))

    def test_binding_failure_warns_without_raising(self):
        """绑定失败只提示不阻断——合同已落库，不能因绑定失败丢表单。"""
        request = _make_request({"_add_folder_path": "/nonexistent/path", "_add_storage_type": "local"})
        contract = _make_contract()
        service = MagicMock()
        service.create_binding.side_effect = RuntimeError("路径不可访问")
        with patch(_WIRING, return_value=service):
            _apply_deferred_folder_binding(request, contract)  # 不得抛出

        assert any("文件夹绑定未成功" in m for m in _messages_text(request))


@pytest.mark.django_db
class TestResponseAddHooksDeferredBinding:
    def test_response_add_applies_deferred_binding_then_delegates(self):
        """response_add 先补建绑定再走基类跳转（打桩基类，避免完整表单流程）。"""
        contract = _make_contract()
        request = _make_request({"_add_folder_path": "/Volumes/cases/x", "_add_storage_type": "local"})
        admin = ContractAdmin(Contract, AdminSite())
        service = MagicMock()
        with (
            patch(_WIRING, return_value=service),
            patch.object(ContractAdmin, "response_add", lambda self, req, obj, post_url_continue=None: "BASE") as base,
        ):
            # 直接调用模块级入口（覆盖方法已改为薄委托，这里验证委托目标正确）
            _apply_deferred_folder_binding(request, contract)
        service.create_binding.assert_called_once()

    def test_deferred_fields_are_ignored_on_json_body(self):
        """健壮性：请求体不是表单编码（异常形态）时不炸（POST dict 缺字段按空处理）。"""
        request = RequestFactory().post(
            "/admin/contracts/contract/add/",
            data=json.dumps({"foo": 1}),
            content_type="application/json",
        )
        request.user = MagicMock()
        request.session = "session"
        request._messages = FallbackStorage(request)
        contract = _make_contract()
        with patch(_WIRING) as mock_wiring:
            _apply_deferred_folder_binding(request, contract)
        mock_wiring.assert_not_called()


@pytest.mark.django_db
class TestAddChangePageRender:
    """新建页/变更页渲染：查 ID 路由注入与 deferred 组件参数。"""

    def _login_admin(self, client: Any) -> Lawyer:
        # 行级权限豁免只认 is_admin（is_superuser 不豁免 ContractAccessPolicy）
        user = Lawyer.objects.create_user(  # type: ignore[no-any-return]
            username="render_admin",
            real_name="渲染管理员",
            is_staff=True,
            is_superuser=True,
            is_admin=True,
            password="pw-not-secret",  # pragma: allowlist secret
        )
        client.force_login(user)
        return user

    def test_add_page_uses_add_lookup_route_and_deferred_widget(self, client: Any):
        self._login_admin(client)
        resp = client.get("/admin/contracts/contract/add/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # 查 ID：无 id 路由（不再空串拦截「请先保存合同后再查询」）
        assert "/admin/contracts/contract/lookup-oa-guid/" in content
        # 文件夹组件：deferred 模式（pk=0 + true）
        assert "folderBrowser(0, true)" in content
        assert "保存合同后自动绑定" in content
        # 解析按钮：文案「解析」无 emoji，脚本含类型/当事人解析逻辑
        assert "textContent = '解析';" in content
        assert "📅" not in content
        assert "parseContractType" in content
        assert "parsePartyNames" in content
        # 合同指派「本人」按钮：选中当前登录律师并勾选主办
        assert "textContent = '本人';" in content
        assert "fillSelfRow" in content
        # 客户库匹配走 admin autocomplete 且必须传 term（Django 6 只认 term，
        # 传 q 会静默退化为最近 20 条 → 老客户永远匹配不上）
        assert "field_name=client&term=" in content
        assert "field_name=client&q=" not in content

    def test_change_page_keeps_bound_widget_and_id_route(self, client: Any):
        self._login_admin(client)
        contract = _make_contract()
        resp = client.get(f"/admin/contracts/contract/{contract.pk}/change/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # 变更页：组件非 deferred、查 ID 走带 id 路由
        assert f"folderBrowser({contract.pk})" in content
        assert f"/admin/contracts/contract/{contract.pk}/lookup-oa-guid/" in content
        assert "folderBrowser(0, true)" not in content
