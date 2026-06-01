"""聊天记录取证 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def create_project(name: str) -> dict[str, Any]:
    """创建聊天记录取证项目。"""
    return client.post("/chat-records/projects", json={"name": name})  # type: ignore[no-any-return]


def list_projects() -> list[dict[str, Any]]:
    """列出当前用户的所有取证项目。"""
    return client.get("/chat-records/projects")  # type: ignore[no-any-return]


def list_recordings(project_id: int) -> list[dict[str, Any]]:
    """列出项目下的录屏列表。"""
    return client.get(f"/chat-records/projects/{project_id}/recordings")  # type: ignore[no-any-return]


def list_screenshots(project_id: int) -> list[dict[str, Any]]:
    """列出项目下的截图列表。"""
    return client.get(f"/chat-records/projects/{project_id}/screenshots")  # type: ignore[no-any-return]


def create_export(project_id: int, export_type: str = "pdf") -> dict[str, Any]:
    """创建导出任务。export_type: pdf / docx。"""
    return client.post(  # type: ignore[no-any-return]
        f"/chat-records/projects/{project_id}/exports",
        json={"export_type": export_type},
    )


def get_export_task(task_id: str) -> dict[str, Any]:
    """查询导出任务状态。status: pending/processing/completed/failed。"""
    return client.get(f"/chat-records/exports/{task_id}")  # type: ignore[no-any-return]
