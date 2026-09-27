"""``scan_migration_anomalies`` 管理命令。

测试库是从代码迁移文件现建的，三类异常都不会自然出现，所以用假记录构造场景：
孤儿 = 插一条 app 名不存在于代码的记录；重复 = 同一条插两次。
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

_FAKE_APP = "fake_orphan_app"
_FAKE_NAME = "0001_initial"


def _insert(app: str, name: str) -> None:
    with connection.cursor() as cur:
        cur.execute(
            "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, NOW())",
            [app, name],
        )


def _delete(app: str, name: str) -> None:
    with connection.cursor() as cur:
        cur.execute("DELETE FROM django_migrations WHERE app = %s AND name = %s", [app, name])


@pytest.mark.django_db
class TestScanMigrationAnomalies:
    def test_healthy_records_pass(self) -> None:
        """记录与代码一致时成功返回。"""
        out = StringIO()
        call_command("scan_migration_anomalies", stdout=out)
        assert "迁移记录健康" in out.getvalue()

    def test_orphan_is_reported(self) -> None:
        """库有记录、磁盘无文件 → 归入「孤儿」并以非零退出码结束。"""
        _insert(_FAKE_APP, _FAKE_NAME)
        try:
            out = StringIO()
            with pytest.raises(CommandError, match="孤儿 1"):
                call_command("scan_migration_anomalies", stdout=out)
            value = out.getvalue()
            assert "[孤儿]" in value
            assert f"{_FAKE_APP}.{_FAKE_NAME}" in value
        finally:
            _delete(_FAKE_APP, _FAKE_NAME)

    def test_duplicate_is_reported(self) -> None:
        """同一 (app, name) 插两次 → 归入「重复」。

        回归：django_migrations 没有唯一约束，并发 migrate 会各插一行；
        这类重复不影响 Django 行为（读的是 dict），但会让 COUNT(*) 与唯一键数
        对不上，排查时极易误判（本仓库就因此把 309 vs 308 当成孤儿问题查过一轮）。
        """
        _insert(_FAKE_APP, _FAKE_NAME)
        _insert(_FAKE_APP, _FAKE_NAME)
        try:
            out = StringIO()
            with pytest.raises(CommandError, match="重复 1 组"):
                call_command("scan_migration_anomalies", stdout=out)
            value = out.getvalue()
            assert "[重复]" in value
            assert f"{_FAKE_APP}.{_FAKE_NAME}  出现 2 次" in value
        finally:
            _delete(_FAKE_APP, _FAKE_NAME)
