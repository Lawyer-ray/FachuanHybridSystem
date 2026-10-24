"""案由/法院数据 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_causes_data(search: str | None = None, case_type: str | None = None, limit: int = 50) -> dict[str, Any]:
    """搜索案由（扁平列表,含编码/名称）——创建案件时选案由用。

    案由字典很大,端点默认只回 50 条:知道关键词时务必传 ``search``
    （如「买卖合同」）,否则只能拿到字典头部。case_type 可按
    civil/criminal/administrative/execution/bankruptcy 收窄。
    """
    params: dict[str, Any] = {"limit": limit}
    if search:
        params["search"] = search
    if case_type:
        params["case_type"] = case_type
    return list_result(client.get("/cases/causes-data", params=params))


def list_causes_tree(parent_id: int | None = None) -> dict[str, Any]:
    """按层级浏览案由树——不传 parent_id 返回顶级,逐层下钻选案由。

    每层节点数有限,适合「不知道确切名称,按民事→合同→买卖合同
    逐层找」的场景;知道关键词用 ``list_causes_data`` 的 search 更快。
    """
    params: dict[str, Any] = {}
    if parent_id is not None:
        params["parent_id"] = parent_id
    return list_result(client.get("/cases/causes-tree", params=params))


def get_cause(cause_id: int) -> dict[str, Any]:
    """获取单个案由详情（编码、名称、分类）。"""
    return client.get(f"/cases/cause/{cause_id}")  # type: ignore[no-any-return]


def list_courts_data(search: str | None = None, limit: int = 50) -> dict[str, Any]:
    """搜索法院（全国法院字典很大,端点默认只回 50 条）——创建案件/文书时选受理法院用。

    知道关键词时务必传 ``search``（如「深圳」「浦东」）,否则只能拿到
    字典头部。
    """
    params: dict[str, Any] = {"limit": limit}
    if search:
        params["search"] = search
    return list_result(client.get("/cases/courts-data", params=params))
