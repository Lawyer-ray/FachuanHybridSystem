"""案件文件夹扫描 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def start_folder_scan(case_id: int, folder_path: str) -> dict[str, Any]:
    """启动案件文件夹扫描任务。folder_path 为要扫描的文件夹路径。"""
    return client.post(  # type: ignore[return-value]
        f"/cases/{case_id}/folder-scan",
        json={"folder_path": folder_path},
    )


def list_scan_subfolders(case_id: int) -> list[dict[str, Any]]:
    """获取案件文件夹扫描的子文件夹列表。"""
    return client.get(f"/cases/{case_id}/folder-scan/subfolders")  # type: ignore[return-value]


def get_scan_status(case_id: int, session_id: int) -> dict[str, Any]:
    """查询文件夹扫描任务状态。status: pending/scanning/completed/failed。"""
    return client.get(f"/cases/{case_id}/folder-scan/{session_id}")  # type: ignore[return-value]


def create_scan_stage(case_id: int, session_id: int, stage_name: str) -> dict[str, Any]:
    """为文件夹扫描任务创建阶段标记。stage_name 为阶段名称。"""
    return client.post(  # type: ignore[return-value]
        f"/cases/{case_id}/folder-scan/{session_id}/stage",
        json={"stage_name": stage_name},
    )
