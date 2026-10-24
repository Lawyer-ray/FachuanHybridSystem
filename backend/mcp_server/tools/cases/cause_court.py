"""案由/法院数据 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_causes_data() -> list[dict[str, Any]]:
    """获取所有案由数据（扁平列表,含编码/名称）——创建案件时选案由用。"""
    return client.get("/cases/causes-data")  # type: ignore[return-value]


def list_causes_tree() -> list[dict[str, Any]]:
    """获取案由树形结构（按民事/刑事/行政等分类）——按层级浏览选案由。"""
    return client.get("/cases/causes-tree")  # type: ignore[return-value]


def get_cause(cause_id: int) -> dict[str, Any]:
    """获取单个案由详情（编码、名称、分类）。"""
    return client.get(f"/cases/cause/{cause_id}")  # type: ignore[return-value]


def list_courts_data() -> list[dict[str, Any]]:
    """获取所有法院数据列表——创建案件/文书时选受理法院用。"""
    return client.get("/cases/courts-data")  # type: ignore[return-value]
