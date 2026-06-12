"""企业数据搜索 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def enterprise_search(keyword: str, provider: str | None = None) -> list[dict[str, Any]]:
    """搜索企业信息。keyword 为搜索关键词（公司名）；provider 为数据源（如 tianyancha、qichacha）。"""
    params: dict[str, Any] = {"keyword": keyword}
    if provider:
        params["provider"] = provider
    return client.get("/client/clients/enterprise/search", params=params)  # type: ignore[return-value]


def enterprise_prefill(keyword: str) -> dict[str, Any]:
    """根据公司名预填充客户信息（统一社会信用代码、法人等）。"""
    return client.get("/client/clients/enterprise/prefill", params={"keyword": keyword})  # type: ignore[return-value]
