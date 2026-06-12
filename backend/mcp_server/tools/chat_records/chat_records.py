"""聊天记录取证 MCP tools"""

from __future__ import annotations

import base64
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


def get_export_types() -> list[dict[str, Any]]:
    """获取所有可用的导出类型列表。"""
    return client.get("/chat-records/export-types")  # type: ignore[return-value]


def get_export_statuses() -> list[dict[str, Any]]:
    """获取所有导出状态列表。"""
    return client.get("/chat-records/export-statuses")  # type: ignore[return-value]


def download_export(task_id: str) -> dict[str, Any]:
    """下载导出任务的结果文件。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/chat-records/exports/{task_id}/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def get_recording(recording_id: int) -> dict[str, Any]:
    """获取单条录屏详情。"""
    return client.get(f"/chat-records/recordings/{recording_id}")  # type: ignore[return-value]


def update_recording(recording_id: int, **fields: Any) -> dict[str, Any]:
    """更新录屏信息。通过 kwargs 传递要修改的字段。"""
    return client.patch(f"/chat-records/recordings/{recording_id}", json=fields)  # type: ignore[return-value]


def delete_recording(recording_id: int) -> None:
    """删除录屏。此操作不可逆。"""
    client.delete(f"/chat-records/recordings/{recording_id}")


def extract_recording(recording_id: int) -> dict[str, Any]:
    """触发录屏的文字提取（OCR/ASR）。异步执行。"""
    return client.post(f"/chat-records/recordings/{recording_id}/extract", json={})  # type: ignore[return-value]


def cancel_extract_recording(recording_id: int) -> dict[str, Any]:
    """取消正在进行的录屏文字提取任务。"""
    return client.post(f"/chat-records/recordings/{recording_id}/extract/cancel", json={})  # type: ignore[return-value]


def reset_extract_recording(recording_id: int) -> dict[str, Any]:
    """重置录屏的文字提取结果（清除已提取内容）。"""
    return client.post(f"/chat-records/recordings/{recording_id}/extract/reset", json={})  # type: ignore[return-value]


def update_screenshot(screenshot_id: int, **fields: Any) -> dict[str, Any]:
    """更新截图信息。通过 kwargs 传递要修改的字段。"""
    return client.patch(f"/chat-records/screenshots/{screenshot_id}", json=fields)  # type: ignore[return-value]


def delete_screenshot(screenshot_id: int) -> None:
    """删除截图。此操作不可逆。"""
    client.delete(f"/chat-records/screenshots/{screenshot_id}")


def reorder_screenshots(project_id: int, screenshot_ids: list[int]) -> dict[str, Any]:
    """重新排序项目下的截图。screenshot_ids 为按新顺序排列的截图ID列表。"""
    return client.post(  # type: ignore[return-value]
        f"/chat-records/projects/{project_id}/screenshots/reorder",
        json={"screenshot_ids": screenshot_ids},
    )
