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


def create_placeholder(key: str, label: str, source: str = "manual", **extra: Any) -> dict[str, Any]:
    """创建替换词。"""
    return client.post("/documents/placeholders", json={"key": key, "label": label, "source": source, **extra})  # type: ignore[return-value]


def update_placeholder(placeholder_id: int, **fields: Any) -> dict[str, Any]:
    """更新替换词。"""
    return client.put(f"/documents/placeholders/{placeholder_id}", json=fields)  # type: ignore[return-value]


def delete_placeholder(placeholder_id: int) -> None:
    """软删除替换词。"""
    client.delete(f"/documents/placeholders/{placeholder_id}")
