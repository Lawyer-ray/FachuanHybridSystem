"""全局搜索 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def global_search(q: str, **extra: Any) -> dict[str, Any]:
    """跨模块关键词搜索（客户、案件、合同、收件箱、法院短信、联系人）。"""
    return client.get("/search", params={"q": q, **extra})  # type: ignore[return-value]
