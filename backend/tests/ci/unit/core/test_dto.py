"""测试 core.dto 子模块

覆盖: auth.py, request_context.py, 以及其他 DTO 类
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ============================================================
# auth.py - LoginAttemptResult / TokenAcquisitionResult
# ============================================================


class TestLoginAttemptResult:
    """测试 LoginAttemptResult DTO"""

    def test_to_dict_success(self) -> None:
        from apps.core.dto.auth import LoginAttemptResult

        result = LoginAttemptResult(
            success=True,
            token="tok123",  # allowlist secret
            account="user@test.com",  # allowlist secret
            error_message=None,
            attempt_duration=1.5,
            retry_count=0,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["token"] == "tok123"
        assert d["account"] == "user@test.com"  # allowlist secret
        assert d["error_message"] is None
        assert d["attempt_duration"] == 1.5
        assert d["retry_count"] == 0

    def test_to_dict_failure(self) -> None:
        from apps.core.dto.auth import LoginAttemptResult

        result = LoginAttemptResult(
            success=False,
            token=None,
            account="user@test.com",  # allowlist secret
            error_message="invalid credentials",
            attempt_duration=0.5,
            retry_count=3,
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["token"] is None
        assert d["error_message"] == "invalid credentials"
        assert d["retry_count"] == 3


class TestTokenAcquisitionResult:
    """测试 TokenAcquisitionResult DTO"""

    def test_to_dict_success(self) -> None:
        from apps.core.dto.auth import LoginAttemptResult, TokenAcquisitionResult

        attempt = LoginAttemptResult(
            success=True, token="t", account="a", error_message=None,
            attempt_duration=1.0, retry_count=0,
        )
        result = TokenAcquisitionResult(
            success=True,
            token="tok",
            acquisition_method="login",
            total_duration=2.0,
            login_attempts=[attempt],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["token"] == "tok"
        assert len(d["login_attempts"]) == 1

    def test_to_dict_with_error(self) -> None:
        from apps.core.dto.auth import TokenAcquisitionResult

        result = TokenAcquisitionResult(
            success=False,
            token=None,
            acquisition_method="login",
            total_duration=5.0,
            login_attempts=[],
            error_details={"reason": "timeout"},
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error_details"] == {"reason": "timeout"}


# ============================================================
# request_context.py - RequestContext / extract_request_context
# ============================================================


class TestRequestContext:
    """测试 RequestContext DTO"""

    def test_to_access_context(self) -> None:
        from apps.core.dto.request_context import RequestContext

        user = SimpleNamespace(id=1, is_authenticated=True)
        ctx = RequestContext(
            user=user,
            org_access={"lawyers": {1}},
            perm_open_access=False,
        )
        ac = ctx.to_access_context()
        assert ac.user is user
        assert ac.org_access == {"lawyers": {1}}
        assert ac.perm_open_access is False

    def test_frozen(self) -> None:
        from apps.core.dto.request_context import RequestContext

        ctx = RequestContext(user=None, org_access=None, perm_open_access=False)
        with pytest.raises(AttributeError):
            ctx.perm_open_access = True  # type: ignore[misc]


class TestExtractRequestContext:
    """测试 extract_request_context"""

    def test_extracts_from_request(self) -> None:
        from apps.core.dto.request_context import extract_request_context

        user = SimpleNamespace(id=5)
        request = SimpleNamespace(
            user=user,
            org_access={"a": 1},
            perm_open_access=True,
        )
        ctx = extract_request_context(request)
        assert ctx.user is user
        assert ctx.org_access == {"a": 1}
        assert ctx.perm_open_access is True

    def test_defaults_when_missing(self) -> None:
        from apps.core.dto.request_context import extract_request_context

        request = SimpleNamespace()
        ctx = extract_request_context(request)
        assert ctx.user is None
        assert ctx.org_access is None
        assert ctx.perm_open_access is False


# ============================================================
# events.py - Events 常量
# ============================================================


class TestEvents:
    """测试 Events 事件常量"""

    def test_case_events(self) -> None:
        from apps.core.infrastructure.events import Events

        assert Events.CASE_CREATED == "case.created"
        assert Events.CASE_UPDATED == "case.updated"
        assert Events.CASE_DELETED == "case.deleted"
