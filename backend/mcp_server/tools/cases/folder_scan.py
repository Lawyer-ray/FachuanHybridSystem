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


def list_scan_subfolders(case_id: int) -> dict[str, Any]:
    """获取案件文件夹扫描的子文件夹列表。

    返回 ``{root_path, subfolders}``（后端 ``CaseFolderScanSubfolderListOut``）。
    """
    return client.get(f"/cases/{case_id}/folder-scan/subfolders")  # type: ignore[return-value]


def get_scan_status(case_id: int, session_id: int) -> dict[str, Any]:
    """查询文件夹扫描任务状态。status: pending/running/classifying/completed/staged/failed/cancelled（staged=文件已导入为案件附件）。"""
    return client.get(f"/cases/{case_id}/folder-scan/{session_id}")  # type: ignore[return-value]


def create_scan_stage(case_id: int, session_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    """为文件夹扫描任务写入阶段条目。

    后端 ``CaseFolderScanStageIn`` 只接受 ``items`` 数组。早前工具传
    ``stage_name``，结构不符，调用必然 422。

    Args:
        case_id: 案件 ID。
        session_id: 扫描会话 ID。
        items: 阶段条目数组（每项包含子文件夹与阶段的对应关系）。
    """
    return client.post(f"/cases/{case_id}/folder-scan/{session_id}/stage", json={"items": items})  # type: ignore[no-any-return]
