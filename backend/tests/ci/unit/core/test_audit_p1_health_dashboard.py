"""安全审计（2026-10-19）P1 回归测试。

- /api/v1/health 输出最小化：to_dict 默认不外发 diagnostic_info/details/system_info
  与原始异常 message（含 Redis 连接串、DB 主机拓扑），include_details=True 分支
  保持内部排障能力
- /api/v1/dashboard/stats 提醒列表接入读范围过滤：非管理员看不到他人案件的提醒
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus, SystemHealth


def test_health_to_dict_default_strips_sensitive_details():
    """默认序列化不泄露连接串/主机/异常原文；include_details=True 保留排障能力。"""
    redis_url = "redis://:p%40ss@redis-host.internal:6379/1"  # privacy-allow 虚构连接串，断言其不被泄露
    raw_error = (
        'connection to server at "db-host.internal" (10.0.0.5), port 5432 failed: '
        'FATAL: password authentication failed for user "fachuan"'
    )
    system = SystemHealth(
        status=HealthStatus.UNHEALTHY,
        version="1.0.0",
        uptime_seconds=12.34,
        components=[
            ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {raw_error}",
                details={"internal_detail": "x"},
                diagnostic_info={"database_host": "db-host.internal", "error_details": raw_error},
            ),
            ComponentHealth(
                name="cache",
                status=HealthStatus.DEGRADED,
                message=f"Cache error: {raw_error}",
                diagnostic_info={"cache_backend": "django_redis", "cache_location": redis_url},
            ),
        ],
        system_info={"hostname": "prod-host.internal"},
    )

    public = system.to_dict()
    public_dumped = json.dumps(public, ensure_ascii=False)

    # 对外结构只有 status/latency/message 最小信息
    assert "system_info" not in public
    for comp in public["components"]:
        assert set(comp) == {"name", "status", "latency_ms", "message"}
        assert "diagnostic_info" not in comp
        assert "details" not in comp

    # 不含连接串 / 主机 / 原始异常
    assert redis_url not in public_dumped
    assert raw_error not in public_dumped
    assert "redis-host.internal" not in public_dumped
    assert "db-host.internal" not in public_dumped

    # message 是固定人话短句，状态仍如实反映
    db_comp, cache_comp = public["components"]
    assert db_comp["message"] == "数据库不可用"
    assert db_comp["status"] == "unhealthy"
    assert cache_comp["message"] == "缓存不可用"
    assert cache_comp["status"] == "degraded"

    # 内部用途（admin /health/detail）显式传 include_details=True：完整保留
    detail = system.to_dict(include_details=True)
    detail_db, detail_cache = detail["components"]
    assert detail["system_info"] == {"hostname": "prod-host.internal"}
    assert detail_db["message"] == f"Database error: {raw_error}"
    assert detail_db["diagnostic_info"]["database_host"] == "db-host.internal"
    assert detail_cache["diagnostic_info"]["cache_location"] == redis_url


@pytest.mark.django_db
def test_dashboard_upcoming_reminders_scoped_for_non_admin():
    """非管理员在仪表盘看不到他人案件的提醒原文；ctx=None 内部口径不过滤。"""
    from django.utils import timezone

    from apps.cases.models import CaseAssignment
    from apps.core.security.access_context import AccessContext
    from apps.reminders.models import Reminder
    from apps.testing.factories import CaseFactory, LawyerFactory
    from apps.workbench.services.dashboard_service import _upcoming_reminders

    lawyer_a = LawyerFactory()
    lawyer_b = LawyerFactory()
    case_b = CaseFactory()
    CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)
    now = timezone.now()
    Reminder.objects.create(
        case=case_b,
        reminder_type="hearing",
        content="B的案件开庭提醒",
        due_at=now + timedelta(days=1),
    )

    result_a = _upcoming_reminders(now, AccessContext(user=lawyer_a, org_access=None, perm_open_access=False))
    result_b = _upcoming_reminders(now, AccessContext(user=lawyer_b, org_access=None, perm_open_access=False))
    result_internal = _upcoming_reminders(now)  # ctx=None：admin/首页内部口径不过滤

    assert result_a == []  # A 未被指派该案件，看不到 B 的提醒 content
    assert [r["title"] for r in result_b] == ["B的案件开庭提醒"]
    assert any(r["title"] == "B的案件开庭提醒" for r in result_internal)
