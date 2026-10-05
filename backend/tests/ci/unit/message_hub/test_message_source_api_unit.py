"""message_source_api.py 单元测试：凭证属主校验（安全审计 B-28）与 Schema resolver.

端点函数本体是 pragma no cover 的薄壳，这里聚焦可单测的纯逻辑：
_request_user / _ensure_credential_usable / _ensure_source_manageable
与 MessageSourceOut 的各 resolve_* 方法。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from apps.core.exceptions import PermissionDenied
from apps.message_hub.api.message_source_api import (
    MessageSourceOut,
    _ensure_credential_usable,
    _ensure_source_manageable,
    _request_user,
)


def _request(user: Any = None, auth: Any = None) -> SimpleNamespace:
    return SimpleNamespace(user=user, auth=auth)


def _user(uid: int = 1, **flags: bool) -> SimpleNamespace:
    return SimpleNamespace(id=uid, is_authenticated=True, **flags)


class TestRequestUser:
    def test_authenticated_user_returned(self) -> None:
        user = _user()
        assert _request_user(_request(user=user)) is user

    def test_anonymous_falls_back_to_auth(self) -> None:
        auth = _user(uid=2)
        request = _request(user=SimpleNamespace(is_authenticated=False), auth=auth)
        assert _request_user(request) is auth

    def test_none_user_falls_back_to_auth(self) -> None:
        auth = _user(uid=3)
        assert _request_user(_request(user=None, auth=auth)) is auth

    def test_no_user_no_auth(self) -> None:
        assert _request_user(_request()) is None


class TestEnsureCredentialUsable:
    def _credential(self, lawyer_id: int | None) -> SimpleNamespace:
        return SimpleNamespace(lawyer_id=lawyer_id)

    def test_owner_allowed(self) -> None:
        user = _user(uid=7)
        result = _ensure_credential_usable(_request(user=user), self._credential(lawyer_id=7))
        assert result is None  # 属主凭证放行

    def test_superuser_bypasses(self) -> None:
        admin = _user(uid=1, is_superuser=True)
        assert _ensure_credential_usable(_request(user=admin), self._credential(lawyer_id=99)) is None

    def test_other_lawyers_credential_denied(self) -> None:
        user = _user(uid=7)
        with pytest.raises(PermissionDenied, match="只能使用本人的账号凭证"):
            _ensure_credential_usable(_request(user=user), self._credential(lawyer_id=8))

    def test_no_login_denied(self) -> None:
        with pytest.raises(PermissionDenied, match="请先登录"):
            _ensure_credential_usable(_request(), self._credential(lawyer_id=1))


class TestEnsureSourceManageable:
    def test_credential_source_delegates_to_owner_check(self) -> None:
        user = _user(uid=7)
        source = SimpleNamespace(credential=SimpleNamespace(lawyer_id=7))
        assert _ensure_source_manageable(_request(user=user), source) is None  # 本人凭证 → 放行

    def test_credential_source_other_owner_denied(self) -> None:
        user = _user(uid=7)
        source = SimpleNamespace(credential=SimpleNamespace(lawyer_id=8))
        with pytest.raises(PermissionDenied, match="只能使用本人的账号凭证"):
            _ensure_source_manageable(_request(user=user), source)

    def test_credentialless_source_superuser_allowed(self) -> None:
        admin = _user(uid=1, is_superuser=False, is_admin=True)
        source = SimpleNamespace(credential=None)
        assert _ensure_source_manageable(_request(user=admin), source) is None  # is_admin → 放行

    def test_credentialless_source_super_flag_allowed(self) -> None:
        admin = _user(uid=1, is_superuser=True)
        assert _ensure_source_manageable(_request(user=admin), SimpleNamespace(credential=None)) is None

    def test_credentialless_source_plain_user_denied(self) -> None:
        user = _user(uid=5)
        with pytest.raises(PermissionDenied, match="无权管理该消息来源"):
            _ensure_source_manageable(_request(user=user), SimpleNamespace(credential=None))

    def test_credentialless_source_staff_only_denied(self) -> None:
        """2026Q4 审计收紧：is_staff 不再视为系统管理员。"""
        staff = _user(uid=5, is_staff=True)
        with pytest.raises(PermissionDenied, match="无权管理该消息来源"):
            _ensure_source_manageable(_request(user=staff), SimpleNamespace(credential=None))

    def test_credentialless_source_no_user_denied(self) -> None:
        with pytest.raises(PermissionDenied, match="无权管理该消息来源"):
            _ensure_source_manageable(_request(), SimpleNamespace(credential=None))


class TestMessageSourceOutResolvers:
    def _source(
        self,
        credential: Any = None,
        sync_since: datetime | None = None,
        last_sync_at: datetime | None = None,
        last_sync_status: str = "",
        created_at: datetime | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            credential=credential,
            sync_since=sync_since,
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
            created_at=created_at,
        )

    def test_credential_account(self) -> None:
        src = self._source(credential=SimpleNamespace(account="lit@firm.cn"))
        assert MessageSourceOut.resolve_credential_account(src) == "lit@firm.cn"

    def test_credential_account_none(self) -> None:
        assert MessageSourceOut.resolve_credential_account(self._source()) == ""

    def test_sync_since_iso(self) -> None:
        dt = datetime(2026, 1, 2, 3, 4, 5)
        assert MessageSourceOut.resolve_sync_since(self._source(sync_since=dt)) == "2026-01-02T03:04:05"

    def test_sync_since_none(self) -> None:
        assert MessageSourceOut.resolve_sync_since(self._source()) is None

    def test_last_sync_at(self) -> None:
        dt = datetime(2026, 6, 7, 8, 9, 10)
        assert MessageSourceOut.resolve_last_sync_at(self._source(last_sync_at=dt)) == "2026-06-07T08:09:10"
        assert MessageSourceOut.resolve_last_sync_at(self._source()) is None

    def test_last_sync_status_default_pending(self) -> None:
        from apps.message_hub.models import SyncStatus

        assert MessageSourceOut.resolve_last_sync_status(self._source(last_sync_status="")) == SyncStatus.PENDING
        assert MessageSourceOut.resolve_last_sync_status(self._source(last_sync_status="ok")) == "ok"

    def test_created_at(self) -> None:
        dt = datetime(2026, 2, 3)
        assert MessageSourceOut.resolve_created_at(self._source(created_at=dt)) == "2026-02-03T00:00:00"
        assert MessageSourceOut.resolve_created_at(self._source()) == ""


class TestCreateUpdateSchemas:
    def test_create_in_defaults(self) -> None:
        from apps.message_hub.api.message_source_api import MessageSourceCreateIn

        payload = MessageSourceCreateIn(display_name="测试源", credential_id=3)
        assert payload.source_type == "imap"
        assert payload.is_enabled is True
        assert payload.poll_interval_minutes == 30
        assert payload.sync_since is None
        assert payload.imap_host == ""

    def test_update_in_all_optional(self) -> None:
        from apps.message_hub.api.message_source_api import MessageSourceUpdateIn

        payload = MessageSourceUpdateIn()
        assert payload.display_name is None
        assert payload.sender_blacklist is None
