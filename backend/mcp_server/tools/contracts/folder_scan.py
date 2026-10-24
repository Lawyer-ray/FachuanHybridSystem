"""合同文件夹扫描 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def start_contract_scan(contract_id: int, rescan: bool = False, scan_subfolder: str | None = None) -> dict[str, Any]:
    """启动合同文件夹扫描任务（异步,之后用状态工具轮询）。

    Args:
        contract_id: 合同 ID。
        rescan: True 时重扫已有材料的文件(默认 False 只扫新文件)。
        scan_subfolder: 只扫描绑定文件夹下的该子文件夹(省略=扫根目录);
            可选值先看 list_contract_scan_subfolders。
    """
    body: dict[str, Any] = {"rescan": rescan}
    if scan_subfolder is not None:
        body["scan_subfolder"] = scan_subfolder
    return client.post(f"/contracts/{contract_id}/folder-scan", json=body)  # type: ignore[no-any-return]


def list_contract_scan_subfolders(contract_id: int) -> dict[str, Any]:
    """列出合同文件夹中可用于扫描的子文件夹。

    返回 ``{root_path, subfolders}``（后端 ``ContractFolderScanSubfolderListOut``）。
    """
    return client.get(f"/contracts/{contract_id}/folder-scan/subfolders")  # type: ignore[no-any-return]


def get_latest_contract_scan(contract_id: int) -> dict[str, Any]:
    """获取合同最近一次扫描会话的状态与结果摘要。"""
    return client.get(f"/contracts/{contract_id}/folder-scan/latest")  # type: ignore[no-any-return]


def get_contract_scan_status(contract_id: int, session_id: str) -> dict[str, Any]:
    """获取指定扫描会话的状态（传入会话 ID）。"""
    return client.get(f"/contracts/{contract_id}/folder-scan/{session_id}")  # type: ignore[no-any-return]


def confirm_contract_scan(
    contract_id: int,
    session_id: str,
    items: list[dict[str, Any]] | None = None,
    work_log_suggestions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """确认扫描结果：导入选中的候选文件和工作日志建议。

    Args:
        contract_id: 合同 ID。
        session_id: start_contract_scan 返回的扫描会话 ID。
        items: 要导入的候选文件列表——取扫描结果里的候选对象原样传回(空=全部不导)。
        work_log_suggestions: 要采纳的工作日志建议列表——同样取扫描结果原样传回。
    """
    return client.post(  # type: ignore[no-any-return]
        f"/contracts/{contract_id}/folder-scan/{session_id}/confirm",
        json={"items": items or [], "work_log_suggestions": work_log_suggestions or []},
    )
