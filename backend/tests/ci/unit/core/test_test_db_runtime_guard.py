"""测试库运行时防护 —— 防止再次在真实库上跑测试导致数据被 flush。

## 事故背景（2026-10-23）

修复附件视觉链路时，一次回退验证用了真实库 ``fachuan_dev`` 跑带 ``django_db``
的集成测试，pytest 的 flush 把 ``agent_agentattachment`` 表清空了。

``conftest.py::pytest_configure`` 原本就有一道检查，但它只读 ``DB_NAME``
环境变量；``--reuse-db`` 复用已存在的库时不会重建，配置检查与实际连接的库
可以不一致。因此补了第二道：挂在 ``connection_created`` 信号上，**按实际连上
的库名**判定，非 test 库立即中止进程。

## 本文件守什么

1. 真实库名（``fachuan_dev`` 等）→ 必须判为不安全；
2. 合法测试库名（``test_*`` / ``*_test`` / ``*_test_*`` / ``fachuan_ci_test``）→ 安全；
3. sqlite 不参与判定（CI 的 sqlite 跑法不应被误杀）；
4. 守卫确实注册到了 ``connection_created`` 信号上（防「函数在但没挂上」）。

守不住的代价是「安静地删掉别人的工作数据」，所以这里直接测判定函数与信号注册，
不去 mock 掉待测逻辑本身。
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import _install_runtime_db_guard, _is_safe_test_db_name


def _all_receiver_fns() -> list[Any]:
    """``_live_receivers`` 返回 ``(key, [fn, ...])`` 元组序列，这里拍平成函数列表。"""
    from django.db.backends.signals import connection_created

    receivers = connection_created._live_receivers(sender=None)  # type: ignore[attr-defined]
    fns: list[Any] = []
    for item in receivers:
        # 结构随 Django 版本变化：兼容 (key, group) 与展平后的 (key, fn, ...)
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (list, tuple)):
            fns.extend(item[1])
        elif isinstance(item, (list, tuple)):
            fns.extend(part for part in item if callable(part))
        elif callable(item):
            fns.append(item)
    return fns


class TestSafeDbNamePredicate:
    @pytest.mark.parametrize(
        "db_name",
        ["fachuan_dev", "fachuan_oa_dev", "postgres", "main", "prod", "fachuan"],
    )
    def test_real_database_names_are_unsafe(self, db_name: str) -> None:
        """真实库名必须判为不安全（宁可误杀，不可删数据）。"""
        assert not _is_safe_test_db_name(db_name)

    @pytest.mark.parametrize(
        "db_name",
        ["test_fachuan_dev", "fachuan_dev_test", "my_test_db", "test", "fachuan_ci_test"],
    )
    def test_test_database_names_are_safe(self, db_name: str) -> None:
        """合法测试库名必须放行，不能把正常 CI 跑法也挡了。"""
        assert _is_safe_test_db_name(db_name)

    def test_case_insensitive(self) -> None:
        assert _is_safe_test_db_name("TEST_Fachuan_dev")
        assert not _is_safe_test_db_name("Fachuan_DEV")

    def test_empty_name_is_allowed(self) -> None:
        """空名放行：连接建立瞬间可能还没填 NAME，误杀会弄死整个测试会话。"""
        assert _is_safe_test_db_name("")


class TestGuardRegistration:
    def test_guard_is_registered_on_connection_created(self) -> None:
        """守卫必须真的挂上信号；「函数存在但没注册」等于没有防护。"""
        from django.db.backends.signals import connection_created

        _install_runtime_db_guard()
        names = {getattr(fn, "__name__", "") for fn in _all_receiver_fns()}
        assert "_guard" in names, f"守卫未注册，现有接收者：{names}"

    def test_installing_twice_does_not_duplicate(self) -> None:
        """重复安装不应注册多个接收者（dispatch_uid 去重）。"""
        from django.db.backends.signals import connection_created

        _install_runtime_db_guard()
        _install_runtime_db_guard()
        guard_count = sum(1 for fn in _all_receiver_fns() if getattr(fn, "__name__", "") == "_guard")
        assert guard_count == 1, f"守卫被重复注册 {guard_count} 次"


class TestGuardBehaviour:
    """直接驱动守卫接收者，验证它对接上来的库真的会拦截。"""

    @staticmethod
    def _guard_receiver() -> Any:
        for fn in _all_receiver_fns():
            if getattr(fn, "__name__", "") == "_guard":
                return fn
        raise AssertionError("守卫未注册")

    @pytest.mark.parametrize("db_name", ["fachuan_dev", "postgres"])
    def test_blocks_real_db_connection(self, db_name: str) -> None:
        """连上真实库时必须中止进程（returncode=3）。"""
        _install_runtime_db_guard()
        guard = self._guard_receiver()

        class _FakeConnection:
            settings_dict = {"ENGINE": "django.db.backends.postgresql", "NAME": db_name}

        # pytest.exit 抛的是 _pytest.outcomes.Exit（BaseException 子类），
        # 不是 SystemExit；直接 catch BaseException 以免把「成功拦截」当成崩溃。
        with pytest.raises(BaseException) as excinfo:
            guard(sender=None, connection=_FakeConnection())
        message = str(excinfo.value)
        assert "非测试数据库" in message, f"拦住了但原因不对：{message}"
        assert getattr(excinfo.value, "returncode", None) == 3

    @pytest.mark.parametrize("db_name", ["test_fachuan_dev", "fachuan_ci_test"])
    def test_allows_test_db_connection(self, db_name: str) -> None:
        _install_runtime_db_guard()
        guard = self._guard_receiver()

        class _FakeConnection:
            settings_dict = {"ENGINE": "django.db.backends.postgresql", "NAME": db_name}

        result = guard(sender=None, connection=_FakeConnection())
        assert result is None, "测试库连接应原样放行（不 exit、无返回标记）"

    def test_sqlite_is_exempt(self) -> None:
        """sqlite 没有「生产库被清空」风险，不参与判定（否则 CI 的 sqlite 跑法全红）。"""
        _install_runtime_db_guard()
        guard = self._guard_receiver()

        class _FakeConnection:
            settings_dict = {"ENGINE": "django.db.backends.sqlite3", "NAME": "/tmp/whatever.sqlite3"}

        result = guard(sender=None, connection=_FakeConnection())
        assert result is None, "sqlite 连接应原样放行（不参与判定）"
