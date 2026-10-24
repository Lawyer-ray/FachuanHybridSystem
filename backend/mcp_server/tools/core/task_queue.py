"""任务队列 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_queued_tasks() -> dict[str, Any]:
    """获取排队中的任务列表（管理员;反映系统实时负载）。"""
    return list_result(client.get("/task-queue/queued"))


def list_completed_tasks(limit: int = 30) -> dict[str, Any]:
    """获取已完成任务列表（管理员）。REST 端点无分页,默认只取前 30 条
    （实测全量 71KB+,超 pi 20KB 截断线）;``total`` 是完整条数,要看更多
    显式调大 limit。"""
    return list_result(client.get("/task-queue/completed"), limit=limit)


def list_failed_tasks(limit: int = 20) -> dict[str, Any]:
    """获取失败任务列表（管理员;排障入口,可配合 resubmit_task 重试）。
    REST 端点无分页;失败任务条目肥(含错误结果/堆栈,实测 ~0.9KB/条),
    默认只取前 20 条避免超 pi 20KB 截断线;``total`` 是完整条数,要看更多
    显式调大 limit。"""
    return list_result(client.get("/task-queue/failed"), limit=limit)


def list_scheduled_tasks() -> dict[str, Any]:
    """获取定时任务列表（含下次/上次执行时间）。"""
    return list_result(client.get("/task-queue/scheduled"))


def delete_task(task_id: str) -> None:
    """删除任务记录——管理员;只删记录,已产生的业务效果不回滚。"""
    client.delete(f"/task-queue/tasks/{task_id}")


def delete_schedule(schedule_id: str) -> None:
    """删除定时任务调度——管理员;该周期任务从此不再执行。"""
    client.delete(f"/task-queue/schedules/{schedule_id}")


def resubmit_task(task_id: str) -> dict[str, Any]:
    """把失败任务重新入队执行——管理员;注意确认失败原因已修复,盲目重试会重复失败。"""
    return client.post(f"/task-queue/tasks/{task_id}/resubmit", json={})  # type: ignore[no-any-return]
