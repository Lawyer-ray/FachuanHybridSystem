"""客户财产线索 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_property_clues(client_id: int) -> list[dict[str, Any]]:
    """查询指定客户的所有财产线索，包含房产、车辆、银行账户等信息。"""
    return client.get(f"/client/clients/{client_id}/property-clues")  # type: ignore[return-value]
