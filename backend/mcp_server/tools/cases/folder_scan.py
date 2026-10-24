"""案件文件夹扫描 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def start_folder_scan(
    case_id: int,
    rescan: bool = False,
    scan_subfolder: str = "",
    enable_recognition: bool = True,
) -> dict[str, Any]:
    """启动案件文件夹扫描任务（扫描案件**绑定的文件夹**）。

    Args:
        case_id: 案件 ID。
        rescan: True 时即使已有结果也重新扫描。
        scan_subfolder: 只扫绑定目录下的某个子目录（空 = 全部）。
        enable_recognition: 是否启用识别分类。

    扫描目标来自案件的文件夹绑定,不可任意指定路径——旧签名的
    ``folder_path`` 参数从未生效（端点 ``CaseFolderScanStartIn`` 无此
    字段,2026-10-25 重写）。改绑目录走文件夹绑定接口。
    """
    return client.post(  # type: ignore[no-any-return]
        f"/cases/{case_id}/folder-scan",
        json={
            "rescan": rescan,
            "scan_subfolder": scan_subfolder,
            "enable_recognition": enable_recognition,
        },
    )


def list_scan_subfolders(case_id: int) -> dict[str, Any]:
    """获取案件文件夹扫描的子文件夹列表。

    返回 ``{root_path, subfolders}``（后端 ``CaseFolderScanSubfolderListOut``）。
    """
    return client.get(f"/cases/{case_id}/folder-scan/subfolders")  # type: ignore[no-any-return]


def get_scan_status(case_id: int, session_id: int) -> dict[str, Any]:
    """查询文件夹扫描任务状态。status: pending/running/classifying/completed/staged/failed/cancelled（staged=文件已导入为案件附件）。"""
    return client.get(f"/cases/{case_id}/folder-scan/{session_id}")  # type: ignore[no-any-return]


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
