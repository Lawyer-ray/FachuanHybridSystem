"""全局搜索 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def global_search(q: str, limit: int = 5) -> dict[str, Any]:
    """跨模块关键词搜索（客户、案件、合同、收件箱、法院短信、联系人）。

    Args:
        q: 搜索关键词。
        limit: 每个模块返回的最大条数，默认 5，最大 10。
    """
    return client.get("/search", params={"q": q, "limit": limit})  # type: ignore[no-any-return]
