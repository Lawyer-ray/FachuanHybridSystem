"""「其他工具」导航页的接线测试。

这一页是**纯导航**，没有业务逻辑，所以它出问题的形态只有一种：「卡片点了没反应」——
URL 名字写错、或者它指向的 admin 被从菜单里收起后权限判定把页面挡了。
两种都不会报错，只在人点进去时才发现（而那时通常正是要用它救火）。

同时锁住「文档快照」的两条硬约束：它被收纳到这一页（不在主菜单），
且**只读**（快照不可编辑、不可删改，这是它能被信任的前提）。
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib import admin as django_admin
from django.test import RequestFactory
from django.urls import reverse

# 别名导入：这两个类名以 Test 开头，直接留在模块命名空间里会让 pytest 反复报
# 「cannot collect test class」的噪声警告（它们本来就不是测试）。
from apps.automation.admin.tools_hub_admin.test_tools_hub_admin import TestToolsHubAdmin as _HubAdmin
from apps.automation.models import TestToolsHub as _HubModel
from apps.doc_workspace.admin import DocSnapshotAdmin as _SnapshotAdmin
from apps.doc_workspace.models.snapshot import DocSnapshot


class _StubUser:
    """够用的 admin 用户替身：只要有全部权限即可，不落库。"""

    is_active = True
    is_staff = True
    is_superuser = True
    pk = 1

    def has_perm(self, *_args: Any, **_kwargs: Any) -> bool:
        return True

    def has_module_perms(self, *_args: Any, **_kwargs: Any) -> bool:
        return True


def _hub_cards() -> list[dict[str, Any]]:
    request = RequestFactory().get("/admin/automation/testtoolshub/")
    request.user = _StubUser()
    admin_view = _HubAdmin(_HubModel, django_admin.site)
    response = admin_view.changelist_view(request)
    # 必须真渲染一次：`{% url %}`/模板里的字段名只有在渲染阶段才会出错，
    # 只读 context_data 会让「名字写错」的卡片照样通过。
    response.render()
    return list(response.context_data["test_tools"])


class TestToolsHubCards:
    def test_每张卡片字段齐全(self) -> None:
        cards = _hub_cards()
        assert cards, "导航页至少要有一张卡片"
        for card in cards:
            assert card["name"].strip(), f"卡片缺名字: {card}"
            assert card["description"].strip(), f"卡片缺说明: {card['name']}"
            assert card["icon"].strip().startswith("<svg"), f"卡片缺图标: {card['name']}"
            assert card["color"] in {"primary", "secondary", "success", "warning", "info"}
            assert card.get("cta", "").strip(), f"卡片缺按钮文案: {card['name']}"

    def test_每张卡片的地址都能反解(self) -> None:
        """URL 名字写错时页面照常渲染（`{% url %}` 才会炸，而且只在渲染时）。"""
        for card in _hub_cards():
            url = reverse(f"admin:{card['url']}")
            assert url.startswith("/admin/"), f"{card['name']} 指向了非 admin 地址: {url}"

    def test_文档快照被收纳进其他工具(self) -> None:
        urls = {card["url"] for card in _hub_cards()}
        assert "doc_workspace_docsnapshot_changelist" in urls
        card = next(card for card in _hub_cards() if card["url"].endswith("docsnapshot_changelist"))
        # 这一页不是「测试工具」，按钮文案不能写「进入测试」
        assert "测试" not in card["cta"]


class TestDocSnapshotAdminScope:
    def test_不在主菜单出现(self) -> None:
        """收纳的判据：主菜单里没有它，但 URL 仍然可达。"""
        request = RequestFactory().get("/admin/")
        request.user = _StubUser()
        assert _SnapshotAdmin(DocSnapshot, django_admin.site).has_module_permission(request) is False

    @pytest.mark.parametrize("permission", ["has_add_permission", "has_change_permission", "has_delete_permission"])
    def test_快照只读(self, permission: str) -> None:
        """快照只追加：能改一条就能把「改坏可回滚」这件事本身改坏。"""
        request = RequestFactory().get("/admin/")
        request.user = _StubUser()
        admin_view = _SnapshotAdmin(DocSnapshot, django_admin.site)
        assert getattr(admin_view, permission)(request) is False

    def test_全部字段只读(self) -> None:
        request = RequestFactory().get("/admin/")
        request.user = _StubUser()
        admin_view = _SnapshotAdmin(DocSnapshot, django_admin.site)
        readonly = set(admin_view.get_readonly_fields(request))
        assert readonly == {field.name for field in DocSnapshot._meta.fields}
