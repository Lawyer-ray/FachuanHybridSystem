"""案件文件夹绑定 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def create_case_folder_binding(
    case_id: int,
    folder_path: str,
    storage_type: str = "local",
    **extra: Any,
) -> dict[str, Any]:
    """绑定或更新案件文件夹。storage_type: local / webdav / onedrive。"""
    payload: dict[str, Any] = {"folder_path": folder_path, "storage_type": storage_type, **extra}
    return client.post(f"/cases/{case_id}/folder-binding", json=payload)  # type: ignore[return-value]


def get_case_folder_binding(case_id: int) -> dict[str, Any]:
    """获取案件的文件夹绑定信息。"""
    return client.get(f"/cases/{case_id}/folder-binding")  # type: ignore[return-value]


def delete_case_folder_binding(case_id: int) -> None:
    """解除案件的文件夹绑定。"""
    client.delete(f"/cases/{case_id}/folder-binding")


def get_contract_folder_path(case_id: int) -> dict[str, Any]:
    """获取案件关联合同的文件夹路径。"""
    return client.get(f"/cases/{case_id}/contract-folder-path")  # type: ignore[return-value]


def browse_case_folders(path: str = "") -> list[dict[str, Any]]:
    """浏览可用的文件夹目录。path 为空则返回根目录。"""
    params: dict[str, Any] = {}
    if path:
        params["path"] = path
    return client.get("/cases/folder-browse", params=params)  # type: ignore[return-value]


def list_case_cloud_storage_accounts() -> list[dict[str, Any]]:
    """获取可用的云存储账号列表（坚果云、OneDrive等）。"""
    return client.get("/cases/cloud-storage-accounts")  # type: ignore[return-value]
