"""文件夹模板操作 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_folder_template(template_id: int) -> dict[str, Any]:
    """获取文件夹模板详情。"""
    return client.get(f"/documents/folder-templates/{template_id}")  # type: ignore[return-value]


def create_folder_template(
    name: str,
    template_type: str | None = None,
    case_types: list[str] | None = None,
    case_stages: list[str] | None = None,
    contract_types: list[str] | None = None,
    structure: dict[str, Any] | None = None,
    is_default: bool | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    """创建文件夹模板。

    Args:
        name: 模板名称（必填）。
        template_type: 模板类型。
        case_types: 适用案件类型列表（litigation / non_litigation 等）。
        case_stages: 适用案件阶段列表。
        contract_types: 适用合同类型列表。
        structure: 目录结构树（节点含 name / children 等）。
        is_default: 是否默认模板。
        is_active: 是否启用。
    """
    payload: dict[str, Any] = {"name": name}
    for field in (
        "template_type",
        "case_types",
        "case_stages",
        "contract_types",
        "structure",
        "is_default",
        "is_active",
    ):
        value = locals()[field]
        if value is not None:
            payload[field] = value
    return client.post("/documents/folder-templates", json=payload)  # type: ignore[return-value]


def update_folder_template(template_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """更新文件夹模板。"""
    return client.put(f"/documents/folder-templates/{template_id}", json=fields or {})  # type: ignore[return-value]


def delete_folder_template(template_id: int) -> dict[str, Any]:
    """软删除文件夹模板。返回后端删除结果。"""
    return client.delete(f"/documents/folder-templates/{template_id}")  # type: ignore[no-any-return]


def validate_folder_structure(template_id: int) -> dict[str, Any]:
    """验证文件夹模板的结构。"""
    return client.post(f"/documents/folder-templates/{template_id}/validate", json={})  # type: ignore[return-value]
