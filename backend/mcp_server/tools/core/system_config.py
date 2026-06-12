"""系统配置 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_system_configs() -> list[dict[str, Any]]:
    """获取所有系统配置项（密钥类脱敏显示）。"""
    return client.get("/config/system-configs")  # type: ignore[return-value]


def update_system_configs(configs: list[dict[str, Any]]) -> dict[str, Any]:
    """批量更新系统配置项，不存在则自动创建。"""
    return client.put("/config/system-configs", json=configs)  # type: ignore[return-value]


def create_system_config(key: str, value: str, category: str = "general", description: str = "") -> dict[str, Any]:
    """创建系统配置项（key 已存在则返回 409）。"""
    return client.post(
        "/config/system-configs", json={"key": key, "value": value, "category": category, "description": description}
    )  # type: ignore[return-value]


def patch_system_config(key: str, **fields: Any) -> dict[str, Any]:
    """部分更新单个配置项的属性。"""
    return client.patch(f"/config/system-configs/{key}", json=fields)  # type: ignore[return-value]


def delete_system_config(key: str) -> None:
    """删除系统配置项。"""
    client.delete(f"/config/system-configs/{key}")
