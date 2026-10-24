"""任务队列 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_queued_tasks() -> dict[str, Any]:
    """获取排队中的任务列表（管理员;反映系统实时负载）。"""
    return list_result(client.get("/task-queue/queued"))


def list_completed_tasks() -> dict[str, Any]:
    """获取已完成任务列表（管理员）。"""
    return list_result(client.get("/task-queue/completed"))


def list_failed_tasks() -> dict[str, Any]:
    """获取失败任务列表（管理员;排障入口,可配合 resubmit_task 重试）。"""
    return list_result(client.get("/task-queue/failed"))


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
