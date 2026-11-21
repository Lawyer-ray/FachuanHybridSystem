"""启动期迁移健康检查：只在 DEBUG 喊，且永不阻断启动。"""

from __future__ import annotations

import pytest

from apps.core.utils import migration_health


def test_no_warning_outside_debug(settings: pytest.FixtureRequest) -> None:
    """生产（DEBUG=False）不喊：滚动部署期间落后是正常的，喊也没人管。"""
    from django.test import override_settings

    with override_settings(DEBUG=False):
        assert migration_health.warn_if_unapplied() == 0


def test_degrades_silently_when_db_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """库读不了（迁移表不存在/连接断）→ 返回空表，绝不抛异常。

    这条守的是「启动不能因为健康检查变慢或挂掉」——CI 里没有迁移过的库、
    部署时的冷启动都会走到这个分支。
    """
    from django.db import DatabaseError

    class _Boom:
        def __init__(self, *a: object, **k: object) -> None:
            raise DatabaseError("connection refused")

    monkeypatch.setattr("django.db.migrations.executor.MigrationExecutor", _Boom)
    assert migration_health.unapplied_migrations() == []
