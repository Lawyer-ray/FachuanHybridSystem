"""仪表盘 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_dashboard_stats() -> dict[str, Any]:
    """获取仪表盘统计数据（各模块计数、趋势、分布）。"""
    return client.get("/dashboard/stats")  # type: ignore[return-value]
