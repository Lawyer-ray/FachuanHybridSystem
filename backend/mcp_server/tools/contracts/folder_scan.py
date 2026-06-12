"""合同文件夹扫描 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def start_contract_scan(contract_id: int, rescan: bool = False, scan_subfolder: str | None = None) -> dict[str, Any]:
    """启动合同文件夹扫描任务。"""
    body: dict[str, Any] = {"rescan": rescan}
    if scan_subfolder is not None:
        body["scan_subfolder"] = scan_subfolder
    return client.post(f"/contracts/{contract_id}/folder-scan", json=body)  # type: ignore[return-value]


def list_contract_scan_subfolders(contract_id: int) -> list[dict[str, Any]]:
    """列出合同文件夹中可用于扫描的子文件夹。"""
    return client.get(f"/contracts/{contract_id}/folder-scan/subfolders")  # type: ignore[return-value]


def get_latest_contract_scan(contract_id: int) -> dict[str, Any]:
    """获取合同最新扫描会话状态。"""
    return client.get(f"/contracts/{contract_id}/folder-scan/latest")  # type: ignore[return-value]


def get_contract_scan_status(contract_id: int, session_id: str) -> dict[str, Any]:
    """获取指定扫描会话的状态。"""
    return client.get(f"/contracts/{contract_id}/folder-scan/{session_id}")  # type: ignore[return-value]


def confirm_contract_scan(
    contract_id: int,
    session_id: str,
    items: list[dict[str, Any]] | None = None,
    work_log_suggestions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """确认扫描结果：导入选中的候选文件和工作日志建议。"""
    return client.post(
        f"/contracts/{contract_id}/folder-scan/{session_id}/confirm",
        json={"items": items or [], "work_log_suggestions": work_log_suggestions or []},
    )  # type: ignore[return-value]
