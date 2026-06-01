"""OA 案件导入 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def trigger_case_import(file_base64: str, filename: str) -> dict[str, Any]:
    """上传 Excel 文件触发 OA 案件导入预览。file_base64 为 Excel 文件的 base64 编码。返回 session_id 用于查询进度。"""
    file_bytes = base64.b64decode(file_base64)
    return client.upload(
        "/case-import",
        files={"file": (filename, file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )  # type: ignore[return-value]


def get_case_import_session(session_id: int) -> dict[str, Any]:
    """查询案件导入会话状态。status: pending/running/completed/failed。"""
    return client.get(f"/case-import/{session_id}")  # type: ignore[return-value]


def get_case_import_preview(session_id: int) -> dict[str, Any]:
    """获取案件导入预览结果，包含匹配/未匹配的案件列表。"""
    return client.get(f"/case-import/{session_id}/preview")  # type: ignore[return-value]


def execute_case_import(
    session_id: int,
    case_nos: list[str],
    matched_case_nos: list[str] | None = None,
) -> dict[str, Any]:
    """执行案件导入。case_nos 为要导入的案件编号列表；matched_case_nos 为已匹配的案件编号（跳过）。"""
    payload: dict[str, Any] = {
        "case_nos": case_nos,
        "matched_case_nos": matched_case_nos or [],
    }
    return client.post(f"/case-import/{session_id}/execute", json=payload)  # type: ignore[return-value]
