"""folder_binding_api._require_admin 权限口径测试（安全审计 2026-10-19）。

原实现仅校验 is_authenticated（名不副实），收紧为 core 的 ensure_admin_request
（is_admin / is_superuser）。前端 frontend/src 无该组端点的实际调用，无正常用户依赖。
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from apps.contracts.api.folder_binding_api import _require_admin
from apps.core.exceptions import PermissionDenied
from apps.organization.models import Lawyer


def _request_with(user: object) -> object:
    request = RequestFactory().get("/api/v1/contracts/folder-browse")
    request.user = user  # type: ignore[attr-defined]
    return request


def test_anonymous_denied() -> None:
    request = RequestFactory().get("/api/v1/contracts/folder-browse")
    from django.contrib.auth.models import AnonymousUser

    request.user = AnonymousUser()
    with pytest.raises(PermissionDenied):
        _require_admin(request)


def test_authenticated_normal_user_denied() -> None:
    """普通登录用户（非 is_admin / 非 superuser）不再放行——权限口径收紧的核心断言"""
    normal = Lawyer(username="fb_normal", is_active=True, is_admin=False, is_superuser=False)
    with pytest.raises(PermissionDenied):
        _require_admin(_request_with(normal))


def test_admin_user_allowed() -> None:
    admin = Lawyer(username="fb_admin", is_active=True, is_admin=True, is_superuser=False)
    assert _require_admin(_request_with(admin)) is None  # 管理员放行（不抛且显式断言返回值）


def test_superuser_allowed() -> None:
    su = Lawyer(username="fb_su", is_active=True, is_admin=False, is_superuser=True)
    assert _require_admin(_request_with(su)) is None  # superuser 放行
