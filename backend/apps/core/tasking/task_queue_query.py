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
