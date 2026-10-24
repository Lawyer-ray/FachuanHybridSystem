"""替换词操作 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_placeholder(placeholder_id: int) -> dict[str, Any]:
    """获取替换词详情。"""
    return client.get(f"/documents/placeholders/{placeholder_id}")  # type: ignore[return-value]


def get_placeholder_by_key(key: str) -> dict[str, Any]:
    """按 key 获取替换词。"""
    return client.get(f"/documents/placeholders/by-key/{key}")  # type: ignore[return-value]


def create_placeholder(
    key: str,
    display_name: str,
    example_value: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    """创建替换词。

    Args:
        key: 替换词键名（模板中以 ``{{key}}`` 引用）。
        display_name: 显示名（界面/文档中展示的名称）。
        example_value: 示例值。
        description: 用途说明。
        is_active: 是否启用；不传由后端默认。
    """
    payload: dict[str, Any] = {"key": key, "display_name": display_name}
    if example_value is not None:
        payload["example_value"] = example_value
    if description is not None:
        payload["description"] = description
    if is_active is not None:
        payload["is_active"] = is_active
    return client.post("/documents/placeholders", json=payload)  # type: ignore[return-value]


def update_placeholder(placeholder_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """更新替换词。"""
    return client.put(f"/documents/placeholders/{placeholder_id}", json=fields or {})  # type: ignore[return-value]


def delete_placeholder(placeholder_id: int) -> dict[str, Any]:
    """软删除替换词。返回后端删除结果。"""
    return client.delete(f"/documents/placeholders/{placeholder_id}")  # type: ignore[no-any-return]
