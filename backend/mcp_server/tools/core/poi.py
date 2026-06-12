"""POI 文档生成 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def poi_health() -> dict[str, Any]:
    """检查 Apache POI 微服务健康状态。"""
    return client.get("/poi/health")  # type: ignore[return-value]


def generate_poi_complaint(**params: Any) -> dict[str, Any]:
    """通过 POI 服务生成起诉状 DOCX。"""
    return client.post("/poi/complaint", json=params)  # type: ignore[return-value]


def generate_report(**params: Any) -> dict[str, Any]:
    """通过 POI 服务生成尽职调查报告 DOCX。"""
    return client.post("/poi/report", json=params)  # type: ignore[return-value]
