"""测试 apps.core.middleware.db_statement_timeout.DbStatementTimeoutMiddleware

覆盖：set/reset 严格配对、异常路径恢复、非 PG vendor 跳过、DEBUG 跳过、
超时值解析（env 覆盖 / 非法值回退 / 0 关闭）、SET 失败不 reset、RESET 失败不影响响应、
settings MIDDLEWARE 注册。
全部 mock connection，不依赖真实数据库。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest, HttpResponse

from apps.core.middleware import db_statement_timeout as mw_module
from apps.core.middleware.db_statement_timeout import (
    _RESET_SQL,
    _SET_SQL,
    DEFAULT_WEB_STATEMENT_TIMEOUT_MS,
    DbStatementTimeoutMiddleware,
)

_MIDDLEWARE_PATH = "apps.core.middleware.db_statement_timeout.DbStatementTimeoutMiddleware"


def _ok_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


class _FakeConnection:
    """记录 cursor.execute 调用序列的假连接；可注入异常。"""

    def __init__(
        self,
        *,
        vendor: str = "postgresql",
        set_error: Exception | None = None,
        reset_error: Exception | None = None,
    ) -> None:
        self.vendor = vendor
        self._set_error = set_error
        self._reset_error = reset_error
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)


class _FakeCursor:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> None:
        self._conn.executed.append((sql, tuple(params or ())))
        if self._conn._set_error is not None and sql == _SET_SQL:
            raise self._conn._set_error
        if self._conn._reset_error is not None and sql == _RESET_SQL:
            raise self._conn._reset_error


def _make(
    monkeypatch: pytest.MonkeyPatch,
    *,
    vendor: str = "postgresql",
    debug: bool = False,
    env: str | None = None,
    set_error: Exception | None = None,
    reset_error: Exception | None = None,
) -> tuple[DbStatementTimeoutMiddleware, _FakeConnection]:
    if env is not None:
        monkeypatch.setenv(mw_module.ENV_NAME, env)
    else:
        monkeypatch.delenv(mw_module.ENV_NAME, raising=False)
    fake_conn = _FakeConnection(vendor=vendor, set_error=set_error, reset_error=reset_error)
    with (
        patch.object(mw_module, "settings", SimpleNamespace(DEBUG=debug)),
        patch.object(mw_module, "connection", fake_conn),
    ):
        middleware = DbStatementTimeoutMiddleware(_ok_view)
    # 重新打补丁供 __call__ 使用（构造与调用分开，便于外部再触发 __call__）
    return middleware, fake_conn


def _run(middleware: DbStatementTimeoutMiddleware, fake_conn: _FakeConnection) -> HttpResponse:
    with (
        patch.object(mw_module, "settings", SimpleNamespace(DEBUG=False)),
        patch.object(mw_module, "connection", fake_conn),
    ):
        request = HttpRequest()
        response = middleware(request)
    assert isinstance(response, HttpResponse)
    return response


# ============================================================
# set/reset 配对
# ============================================================


class TestSetResetPairing:
    def test_normal_path_sets_then_resets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch)
        response = _run(middleware, fake_conn)

        assert response.status_code == 200
        assert fake_conn.executed == [
            (_SET_SQL, (str(DEFAULT_WEB_STATEMENT_TIMEOUT_MS),)),
            (_RESET_SQL, ()),
        ]

    def test_set_executes_before_view_and_reset_after(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch)
        order: list[str] = []

        def tracking_view(request: HttpRequest) -> HttpResponse:
            order.append("view")
            assert fake_conn.executed and fake_conn.executed[0][0] == _SET_SQL
            return HttpResponse("ok")

        middleware.get_response = tracking_view
        with (
            patch.object(mw_module, "settings", SimpleNamespace(DEBUG=False)),
            patch.object(mw_module, "connection", fake_conn),
        ):
            middleware(HttpRequest())
        assert order == ["view"]
        assert len(fake_conn.executed) == 2

    def test_exception_in_view_propagates_and_resets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch)

        def boom(request: HttpRequest) -> HttpResponse:
            raise ValueError("view exploded")

        middleware.get_response = boom
        with (
            patch.object(mw_module, "settings", SimpleNamespace(DEBUG=False)),
            patch.object(mw_module, "connection", fake_conn),
            pytest.raises(ValueError, match="view exploded"),
        ):
            middleware(HttpRequest())

        # 异常路径同样完成 reset，防止 CONN_MAX_AGE 复用连接残留超时值
        assert fake_conn.executed == [
            (_SET_SQL, (str(DEFAULT_WEB_STATEMENT_TIMEOUT_MS),)),
            (_RESET_SQL, ()),
        ]


# ============================================================
# 跳过条件：DEBUG / 非 PG / 超时值 <= 0
# ============================================================


class TestSkipConditions:
    def test_debug_skipped_entirely(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch, debug=True)
        with (
            patch.object(mw_module, "settings", SimpleNamespace(DEBUG=True)),
            patch.object(mw_module, "connection", fake_conn),
        ):
            response = middleware(HttpRequest())
        assert response.status_code == 200
        # DEBUG 下连接 options 已全局注入 statement_timeout，
        # 中间件必须零 SQL（否则 reset 会抹掉全局值）
        assert fake_conn.executed == []

    def test_non_pg_vendor_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch, vendor="sqlite")
        response = _run(middleware, fake_conn)
        assert response.status_code == 200
        assert fake_conn.executed == []

    def test_mysql_vendor_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch, vendor="mysql")
        response = _run(middleware, fake_conn)
        assert response.status_code == 200
        assert fake_conn.executed == []

    def test_zero_timeout_disables_feature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch, env="0")
        response = _run(middleware, fake_conn)
        assert response.status_code == 200
        assert fake_conn.executed == []


# ============================================================
# 超时值解析
# ============================================================


class TestTimeoutResolution:
    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch, env="12345")
        response = _run(middleware, fake_conn)
        assert response.status_code == 200
        assert fake_conn.executed[0] == (_SET_SQL, ("12345",))

    def test_invalid_env_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with patch.object(mw_module.logger, "warning") as mock_warn:
            middleware, fake_conn = _make(monkeypatch, env="not-a-number")
        assert middleware.timeout_ms == DEFAULT_WEB_STATEMENT_TIMEOUT_MS
        assert mock_warn.called
        response = _run(middleware, fake_conn)
        assert fake_conn.executed[0] == (_SET_SQL, (str(DEFAULT_WEB_STATEMENT_TIMEOUT_MS),))

    def test_default_value_is_60_seconds(self) -> None:
        assert DEFAULT_WEB_STATEMENT_TIMEOUT_MS == 60_000

    def test_negative_env_disables_feature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch, env="-1")
        response = _run(middleware, fake_conn)
        assert response.status_code == 200
        assert fake_conn.executed == []


# ============================================================
# SET / RESET 失败路径
# ============================================================


class TestFailurePaths:
    def test_set_failure_skips_reset_and_still_serves_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch, set_error=RuntimeError("conn broken"))
        response = _run(middleware, fake_conn)

        assert response.status_code == 200
        # 只有 1 次 SET 尝试；SET 未生效则不 reset（reset 反而会引入额外失败面）
        assert len(fake_conn.executed) == 1
        assert fake_conn.executed[0][0] == _SET_SQL

    def test_reset_failure_does_not_break_response(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        middleware, fake_conn = _make(monkeypatch, reset_error=RuntimeError("conn closed"))
        with patch.object(mw_module.logger, "warning") as mock_warn:
            response = _run(middleware, fake_conn)

        assert response.status_code == 200
        assert len(fake_conn.executed) == 2
        assert mock_warn.called

    def test_set_failure_logs_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware, fake_conn = _make(monkeypatch, set_error=RuntimeError("conn broken"))
        with patch.object(mw_module.logger, "exception") as mock_exc:
            _run(middleware, fake_conn)
        assert mock_exc.called


# ============================================================
# 中间件能力声明与注册
# ============================================================


class TestRegistrationAndMode:
    def test_middleware_registered_in_settings(self) -> None:
        from django.conf import settings as django_settings

        assert _MIDDLEWARE_PATH in django_settings.MIDDLEWARE

    def test_sync_only_capability(self) -> None:
        # 显式 sync-only：ASGI 下由 Django 用 sync_to_async 包装，
        # 与视图的 thread-sensitive ORM 共享线程 → 连接归属正确
        assert DbStatementTimeoutMiddleware.async_capable is False
        assert DbStatementTimeoutMiddleware.sync_capable is True

    def test_concurrent_requests_pair_correctly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """两个中间件实例（模拟两个并发请求线程）各自配对，互不干扰。"""
        mw1, conn1 = _make(monkeypatch)
        mw2, conn2 = _make(monkeypatch, env="5000")

        _run(mw1, conn1)
        _run(mw2, conn2)

        assert conn1.executed[-1] == (_RESET_SQL, ())
        assert conn2.executed == [(_SET_SQL, ("5000",)), (_RESET_SQL, ())]


# ============================================================
# MagicMock 兼容性（确认 patch django.db.connection 的常用方式可用）
# ============================================================


def test_works_with_magicmock_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(mw_module.ENV_NAME, raising=False)
    cursor = MagicMock()
    conn = MagicMock()
    conn.vendor = "postgresql"
    conn.cursor.return_value.__enter__.return_value = cursor
    with (
        patch.object(mw_module, "settings", SimpleNamespace(DEBUG=False)),
        patch.object(mw_module, "connection", conn),
    ):
        middleware = DbStatementTimeoutMiddleware(_ok_view)
        response = middleware(HttpRequest())
    assert response.status_code == 200
    calls = [str(c.args[0]) for c in cursor.execute.call_args_list]
    assert calls == [_SET_SQL, _RESET_SQL]
