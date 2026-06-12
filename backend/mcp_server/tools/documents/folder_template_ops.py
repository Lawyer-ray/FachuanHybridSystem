"""文件夹模板操作 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_folder_template(template_id: int) -> dict[str, Any]:
    """获取文件夹模板详情。"""
    return client.get(f"/documents/folder-templates/{template_id}")  # type: ignore[return-value]


def create_folder_template(**fields: Any) -> dict[str, Any]:
    """创建文件夹模板。"""
    return client.post("/documents/folder-templates", json=fields)  # type: ignore[return-value]


def update_folder_template(template_id: int, **fields: Any) -> dict[str, Any]:
    """更新文件夹模板。"""
    return client.put(f"/documents/folder-templates/{template_id}", json=fields)  # type: ignore[return-value]


def delete_folder_template(template_id: int) -> None:
    """软删除文件夹模板。"""
    client.delete(f"/documents/folder-templates/{template_id}")


def validate_folder_structure(template_id: int) -> dict[str, Any]:
    """验证文件夹模板的结构。"""
    return client.post(f"/documents/folder-templates/{template_id}/validate", json={})  # type: ignore[return-value]
