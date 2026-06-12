"""合同文件夹绑定 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def create_folder_binding(
    contract_id: int,
    folder_path: str,
    storage_type: str = "local",
    storage_account_id: int | None = None,
) -> dict[str, Any]:
    """绑定合同到指定文件夹。storage_type 为 local（本地）或 cloud（云端）；storage_account_id 为云端存储账号 ID。"""
    payload: dict[str, Any] = {
        "folder_path": folder_path,
        "storage_type": storage_type,
    }
    if storage_account_id is not None:
        payload["storage_account_id"] = storage_account_id
    return client.post(f"/contracts/{contract_id}/folder-binding", json=payload)  # type: ignore[return-value]


def get_folder_binding(contract_id: int) -> dict[str, Any]:
    """获取合同的文件夹绑定信息，包含路径和可访问性状态。"""
    return client.get(f"/contracts/{contract_id}/folder-binding")  # type: ignore[return-value]


def delete_folder_binding(contract_id: int) -> None:
    """解除合同的文件夹绑定。"""
    client.delete(f"/contracts/{contract_id}/folder-binding")


def browse_folders(
    path: str | None = None,
    storage_type: str = "local",
    storage_account_id: int | None = None,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """浏览本地或云端文件夹内容。path 为文件夹路径；storage_type 为 local 或 cloud。"""
    params: dict[str, Any] = {"storage_type": storage_type, "include_hidden": include_hidden}
    if path:
        params["path"] = path
    if storage_account_id is not None:
        params["storage_account_id"] = storage_account_id
    return client.get("/contracts/folder-browse", params=params)  # type: ignore[return-value]


def list_cloud_storage_accounts() -> list[dict[str, Any]]:
    """获取可用的云端存储账号列表（坚果云、OneDrive 等）。"""
    return client.get("/contracts/cloud-storage-accounts")  # type: ignore[return-value]
