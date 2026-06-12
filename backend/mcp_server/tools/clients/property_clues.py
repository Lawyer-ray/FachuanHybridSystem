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


def get_property_clue(clue_id: int) -> dict[str, Any]:
    """获取单条财产线索详情。"""
    return client.get(f"/client/property-clues/{clue_id}")  # type: ignore[return-value]


def update_property_clue(clue_id: int, clue_type: str | None = None, content: str | None = None) -> dict[str, Any]:
    """更新财产线索。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if clue_type is not None:
        payload["clue_type"] = clue_type
    if content is not None:
        payload["content"] = content
    return client.put(f"/client/property-clues/{clue_id}", json=payload)  # type: ignore[return-value]


def delete_property_clue(clue_id: int) -> None:
    """删除财产线索。此操作不可逆。"""
    client.delete(f"/client/property-clues/{clue_id}")


def get_property_clue_content_template() -> dict[str, Any]:
    """获取财产线索的内容模板（预填格式）。"""
    return client.get("/client/property-clues/content-template")  # type: ignore[return-value]
