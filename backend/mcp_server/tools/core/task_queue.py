"""任务队列 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_queued_tasks() -> list[dict[str, Any]]:
    """获取当前排队（待处理）任务列表。"""
    return client.get("/task-queue/queued")  # type: ignore[return-value]


def list_completed_tasks() -> list[dict[str, Any]]:
    """获取已完成任务列表。"""
    return client.get("/task-queue/completed")  # type: ignore[return-value]


def list_failed_tasks() -> list[dict[str, Any]]:
    """获取失败任务列表。"""
    return client.get("/task-queue/failed")  # type: ignore[return-value]


def list_scheduled_tasks() -> list[dict[str, Any]]:
    """获取定时任务列表（含下次/上次执行时间）。"""
    return client.get("/task-queue/scheduled")  # type: ignore[return-value]


def delete_task(task_id: str) -> None:
    """删除已完成或失败的任务记录。"""
    client.delete(f"/task-queue/tasks/{task_id}")


def delete_schedule(schedule_id: str) -> None:
    """删除定时任务调度。"""
    client.delete(f"/task-queue/schedules/{schedule_id}")


def resubmit_task(task_id: str) -> dict[str, Any]:
    """重新提交失败任务执行。"""
    return client.post(f"/task-queue/tasks/{task_id}/resubmit", json={})  # type: ignore[return-value]
