"""任务队列查询服务（封装 django-q2 模型查询）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django_q.models import OrmQ, Schedule, Success, Task

SCHEDULE_TYPE_LABELS: dict[int, str] = {
    Schedule.ONCE: "单次",
    Schedule.MINUTES: "分钟间隔",
    Schedule.HOURLY: "小时",
    Schedule.DAILY: "每天",
    Schedule.WEEKLY: "每周",
    Schedule.MONTHLY: "每月",
    Schedule.QUARTERLY: "每季度",
    Schedule.YEARLY: "每年",
}


def list_queued(limit: int = 200) -> Any:
    """获取排队中的任务。"""
    return OrmQ.objects.all().order_by("-lock")[:limit]


def list_completed(limit: int = 200) -> Any:
    """获取已完成的成功任务。"""
    return Task.objects.filter(success=True).order_by("-stopped")[:limit]


def list_failed(limit: int = 200) -> Any:
    """获取失败的任务。"""
    return Task.objects.filter(success=False).order_by("-stopped")[:limit]


def list_scheduled(limit: int = 200) -> Any:
    """获取定时调度任务。"""
    return Schedule.objects.all().order_by("next_run")[:limit]


def get_last_run_time(name: str) -> datetime | None:
    """获取指定调度名称的最后运行时间。"""
    task = Success.objects.filter(name=name).order_by("-stopped").first()
    return task.stopped if task else None


def get_last_run_times(names: list[str]) -> dict[str, datetime]:
    """批量获取多个调度名称的最后运行时间（单次查询，按名称去重取最新）。"""
    last_runs: dict[str, datetime] = {}
    tasks = Success.objects.filter(name__in=names).order_by("-stopped")
    for task in tasks:
        if task.name not in last_runs:
            last_runs[task.name] = task.stopped
    return last_runs


def cluster_status() -> dict[str, Any]:
    """Django-Q 集群活性聚合（设置页·系统状态卡片消费，只读）。

    - ``clusters``：redis 心跳键按集群名去重的数量（心跳 TTL 3s，键在 = 心跳在）。
      0 = 没有集群在跑；>1 = 多棵进程树抢同一 broker（僵尸集群，成因与清剿
      手法见 backend/CLAUDE.md「Django-Q 队列与僵尸集群防范」）。
    - ``queue_depth``：OrmQ 待消费条数。
    - ``succeeded_today`` / ``failed_today``：本地今日成败计数。
    - ``last_success_at`` / ``last_failed_at``：最近一次成功 / 失败时间。
    - ``broker_error``：redis 探测失败时的异常摘要；非 redis broker 或探测失败时
      ``clusters`` 为 None——前端显示「无法探测」而不是误报成 0（无集群）。
    """
    from django.utils import timezone

    from apps.core.tasking.redis_queue import _get_redis_connection, is_redis_broker

    today = timezone.localdate()
    last_success = Task.objects.filter(success=True).order_by("-stopped").values_list("stopped", flat=True).first()
    last_failure = Task.objects.filter(success=False).order_by("-stopped").values_list("stopped", flat=True).first()

    clusters: int | None = None
    broker_error: str | None = None
    try:
        if is_redis_broker():
            conn = _get_redis_connection()
            names: set[str] = set()
            for key in conn.scan_iter(match="django_q:*:cluster:*", count=200):
                parts = (key.decode() if isinstance(key, bytes) else str(key)).split(":")
                # 键形如 django_q:<集群名>:cluster:<pid>；同一集群多进程只算一个名字
                if len(parts) >= 4 and parts[2] == "cluster":
                    names.add(parts[1])
            clusters = len(names)
    except Exception as exc:  # 状态页不允许因 redis 探测失败整体 500：降级为 clusters=None
        broker_error = str(exc)

    return {
        "clusters": clusters,
        "queue_depth": OrmQ.objects.count(),
        "succeeded_today": Task.objects.filter(success=True, stopped__date=today).count(),
        "failed_today": Task.objects.filter(success=False, stopped__date=today).count(),
        "last_success_at": last_success,
        "last_failed_at": last_failure,
        "broker_error": broker_error,
    }


def delete_task(task_id: str) -> int:
    """删除任务，返回删除数量。"""
    deleted, _ = Task.objects.filter(id=task_id).delete()
    return int(deleted)


def delete_schedule(schedule_id: int) -> int:
    """删除定时调度，返回删除数量。"""
    deleted, _ = Schedule.objects.filter(id=schedule_id).delete()
    return int(deleted)


def get_task_or_none(task_id: str) -> Task | None:
    """获取任务，不存在返回 None。"""
    return Task.objects.filter(id=task_id).first()


def resubmit_task(task_id: str) -> str | None:
    """重新提交失败的任务，返回新任务 ID。不存在返回 None。

    使用 async_task 直接调用原始函数，不经过 run_task 中间件包装。
    """
    from django_q.tasks import async_task

    task = get_task_or_none(task_id)
    if not task:
        return None
    new_id = async_task(
        task.func,
        *task.args or [],
        **task.kwargs or {},
        group=task.group,
        name=task.name,
    )
    return str(new_id)
