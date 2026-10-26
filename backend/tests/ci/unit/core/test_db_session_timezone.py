"""数据库会话时区与 Django TIME_ZONE 一致性守卫。

背景（真实缺陷）：`DATABASES["default"]` 此前没有 `TIME_ZONE` 键。Django 的
`timezone_name` 读的是 **settings_dict["TIME_ZONE"]**（不是 `settings.TIME_ZONE`），
值为 `None` 时当成 `"UTC"`，并在每条连接建立后主动执行 `SET TIME ZONE 'UTC'`
（django/db/backends/base/base.py + postgresql/base.py::_configure_timezone）。

后果：DB 侧 `CURRENT_DATE` / `::date` / `date_trunc('day', ...)` 按 UTC 解释，
而 Python 侧 `timezone.localdate()` 按 `Asia/Shanghai` 解释，每天 00:00–08:00
（CST）两者差一天 —— 「今日到期」「今日新增」类统计与提醒在凌晨集体错位，
白天却完全无法复现。

注意：**不能**靠 `OPTIONS: {"options": "-c timezone=..."}` 修——Django 建连后的
`SET TIME ZONE` 会把它覆盖掉（实测无效）。唯一正确位置是 `DATABASES[*]["TIME_ZONE"]`。
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.db import connection
from django.utils import timezone


class TestSessionTimezoneMatchesDjangoTimezone:
    """DB 会话时区必须与 settings.TIME_ZONE 一致"""

    def test_databases_time_zone_key_is_set(self) -> None:
        """DATABASES[*]["TIME_ZONE"] 必须有显式值——None 会被 Django 当成 UTC。"""
        tz = settings.DATABASES["default"].get("TIME_ZONE")
        assert tz is not None, (
            "DATABASES['default']['TIME_ZONE'] 为 None 时 Django 会 SET TIME ZONE 'UTC'，"
            "与 settings.TIME_ZONE 不一致，DB 侧日期计算会在凌晨差一天"
        )
        assert tz == settings.TIME_ZONE

    def test_connection_timezone_name(self) -> None:
        """Django 认定该连接使用的时区名就是 TIME_ZONE。"""
        assert connection.timezone_name == settings.TIME_ZONE

    @pytest.mark.django_db
    def test_sql_date_matches_python_localdate(self) -> None:
        """DB 侧的「今天」与 Python 侧 timezone.localdate() 必须相同。

        这是缺陷的直接断言：会话时区为 UTC 时，凌晨窗口（CST 00:00–08:00）
        两者会差一天。
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT CURRENT_DATE")
            db_today = cursor.fetchone()[0]
        assert db_today == timezone.localdate()

    @pytest.mark.django_db
    def test_session_time_zone_reported_by_server(self) -> None:
        """服务端自报的会话时区与配置一致（PostgreSQL 专有，SQLite 无此概念）。"""
        if connection.vendor != "postgresql":
            pytest.skip("SHOW TIME ZONE 仅 PostgreSQL 有")
        with connection.cursor() as cursor:
            cursor.execute("SHOW TIME ZONE")
            assert cursor.fetchone()[0] == settings.TIME_ZONE

    @pytest.mark.django_db
    def test_boundary_timestamp_not_off_by_one(self) -> None:
        """跨日窗口的关键断言：CST 凌晨 01:00 的 timestamptz，会话内 ::date 必须是 CST 那天。

        旧配置（UTC 会话）下 `('2026-10-27 01:00:00+08')::date` 会返回 10-26，
        比律师看到的日历日早一天。SQL 用字面量构造，不依赖「今天」是哪天。
        """
        if connection.vendor != "postgresql":
            pytest.skip("timestamptz 字面量与 ::date 的时区语义仅 PostgreSQL 有")
        with connection.cursor() as cursor:
            cursor.execute("SELECT ('2026-10-27 01:00:00+08'::timestamptz)::date")
            got = cursor.fetchone()[0]
        assert got.isoformat() == "2026-10-27"
