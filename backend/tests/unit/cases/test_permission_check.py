"""单元测试：权限检查迁移后行为不变

验证 `_require_admin` 从 folder_binding_api.py 迁移至
FolderBindingService.require_admin 后，权限检查行为一致。

验证: 需求 3.4
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from apps.core.exceptions import PermissionDenied
from apps.core.security.access_context import AccessContext


def _make_user(*, is_authenticated: bool = True, is_admin: bool = False) -> Any:
    """构造一个简单的用户对象用于测试。"""

    @dataclass
    class _FakeUser:
        is_authenticated: bool
        is_admin: bool
        id: int = 1

    return _FakeUser(is_authenticated=is_authenticated, is_admin=is_admin)


def _build_service() -> Any:
    """通过工厂函数获取 FolderBindingService 实例。"""
    from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

    class _Stub:
        """提供 Service 构造所需的最小桩对象。"""

    return CaseFolderBindingService(
        document_service=_Stub(),  # type: ignore[arg-type]
        case_service=_Stub(),  # type: ignore[arg-type]
    )


class TestRequireAdmin:
    """FolderBindingService.require_admin 权限检查测试。"""

    def test_admin_user_passes(self) -> None:
        """admin 用户应通过权限检查，不抛异常。"""
        service = _build_service()
        ctx = AccessContext(
            user=_make_user(is_authenticated=True, is_admin=True),
            org_access=None,
        )
        # 不应抛出异常
        service.require_admin(ctx)

    def test_non_admin_user_rejected(self) -> None:
        """非 admin 用户应被拒绝，抛出 PermissionDenied。"""
        service = _build_service()
        ctx = AccessContext(
            user=_make_user(is_authenticated=True, is_admin=False),
            org_access=None,
        )
        with pytest.raises(PermissionDenied):
            service.require_admin(ctx)

    def test_none_user_rejected(self) -> None:
        """user 为 None 时应被拒绝，抛出 PermissionDenied。"""
        service = _build_service()
        ctx = AccessContext(user=None, org_access=None)
        with pytest.raises(PermissionDenied):
            service.require_admin(ctx)

    def test_unauthenticated_admin_rejected(self) -> None:
        """未认证但 is_admin=True 的用户仍应被拒绝。"""
        service = _build_service()
        ctx = AccessContext(
            user=_make_user(is_authenticated=False, is_admin=True),
            org_access=None,
        )
        with pytest.raises(PermissionDenied):
            service.require_admin(ctx)
