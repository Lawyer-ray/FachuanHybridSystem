"""客户财产线索 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_property_clues(client_id: int) -> list[dict[str, Any]]:
    """查询指定客户的所有财产线索，包含房产、车辆、银行账户等信息。"""
    return client.get(f"/client/clients/{client_id}/property-clues")  # type: ignore[return-value]


def create_property_clue(client_id: int, clue_type: str, content: str) -> dict[str, Any]:
    """为客户添加财产线索。clue_type 常用值：bank（银行账户）、real_estate（房产）、vehicle（车辆）、other（其他）。content 为线索详情。"""
    return client.post(
        f"/client/clients/{client_id}/property-clues",
        json={"clue_type": clue_type, "content": content},
    )  # type: ignore[return-value]
