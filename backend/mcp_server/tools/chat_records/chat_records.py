"""聊天记录取证 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def create_project(name: str) -> dict[str, Any]:
    """创建聊天记录取证项目（微信/QQ 等聊天证据的容器）。"""
    return client.post("/chat-records/projects", json={"name": name})  # type: ignore[no-any-return]


def list_projects() -> dict[str, Any]:
    """列出当前用户的全部取证项目。"""
    return list_result(client.get("/chat-records/projects"))


def list_recordings(project_id: int) -> dict[str, Any]:
    """列出取证项目下的录屏列表。"""
    return list_result(client.get(f"/chat-records/projects/{project_id}/recordings"))


def list_screenshots(project_id: int) -> dict[str, Any]:
    """列出取证项目下的截图列表。"""
    return list_result(client.get(f"/chat-records/projects/{project_id}/screenshots"))


def create_export(project_id: int, export_type: str = "pdf") -> dict[str, Any]:
    """创建导出任务。export_type: pdf / docx。"""
    return client.post(  # type: ignore[no-any-return]
        f"/chat-records/projects/{project_id}/exports",
        json={"export_type": export_type},
    )


def get_export_task(task_id: str) -> dict[str, Any]:
    """查询导出任务状态。status: pending/running/success/failed。"""
    return client.get(f"/chat-records/exports/{task_id}")  # type: ignore[no-any-return]


def get_export_types() -> dict[str, Any]:
    """获取可用的证据导出类型枚举。"""
    return list_result(client.get("/chat-records/export-types"))


def get_export_statuses() -> dict[str, Any]:
    """获取导出任务的状态枚举（轮询时判断用）。"""
    return list_result(client.get("/chat-records/export-statuses"))


def download_export(task_id: str) -> dict[str, Any]:
    """下载导出任务的结果文件。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/chat-records/exports/{task_id}/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def get_recording(recording_id: int) -> dict[str, Any]:
    """获取单条录屏详情（时长、提取状态）。"""
    return client.get(f"/chat-records/recordings/{recording_id}")  # type: ignore[no-any-return]


def update_recording(recording_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """更新录屏信息。通过 kwargs 传递要修改的字段。"""
    return client.patch(f"/chat-records/recordings/{recording_id}", json=fields or {})  # type: ignore[no-any-return]


def delete_recording(recording_id: int) -> None:
    """删除录屏——硬删除,不可恢复。"""
    client.delete(f"/chat-records/recordings/{recording_id}")


def extract_recording(recording_id: int) -> dict[str, Any]:
    """触发录屏的文字提取（OCR/ASR）。异步执行。"""
    return client.post(f"/chat-records/recordings/{recording_id}/extract", json={})  # type: ignore[no-any-return]


def cancel_extract_recording(recording_id: int) -> dict[str, Any]:
    """取消正在进行的录屏文字提取任务。"""
    return client.post(f"/chat-records/recordings/{recording_id}/extract/cancel", json={})  # type: ignore[no-any-return]


def reset_extract_recording(recording_id: int) -> dict[str, Any]:
    """重置录屏的文字提取结果（清除已提取内容）。"""
    return client.post(f"/chat-records/recordings/{recording_id}/extract/reset", json={})  # type: ignore[no-any-return]


def update_screenshot(screenshot_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """更新截图信息。通过 kwargs 传递要修改的字段。"""
    return client.patch(f"/chat-records/screenshots/{screenshot_id}", json=fields or {})  # type: ignore[no-any-return]


def reorder_screenshots(project_id: int, screenshot_ids: list[int]) -> dict[str, Any]:
    """重新排序项目下的截图。screenshot_ids 为按新顺序排列的截图ID列表。"""
    return client.post(  # type: ignore[no-any-return]
        f"/chat-records/projects/{project_id}/screenshots/reorder",
        json={"screenshot_ids": screenshot_ids},
    )
