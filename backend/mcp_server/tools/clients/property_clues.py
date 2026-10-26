"""客户财产线索 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_property_clues(client_id: int) -> dict[str, Any]:
    """查询指定客户的所有财产线索，包含房产、车辆、银行账户等信息。"""
    return list_result(client.get(f"/client/clients/{client_id}/property-clues"))


def create_property_clue(client_id: int, clue_type: str, content: str) -> dict[str, Any]:
    """为客户添加财产线索。clue_type 有效值: bank（银行账户）、alipay（支付宝账户）、
    wechat（微信账户）、real_estate（不动产）、other（其他）。content 为线索详情。"""
    return client.post(  # type: ignore[no-any-return]
        f"/client/clients/{client_id}/property-clues",
        json={"clue_type": clue_type, "content": content},
    )


def get_property_clue(clue_id: int) -> dict[str, Any]:
    """获取单条财产线索详情（类型:银行/支付宝/微信/不动产等）。"""
    return client.get(f"/client/property-clues/{clue_id}")  # type: ignore[no-any-return]


def update_property_clue(clue_id: int, clue_type: str | None = None, content: str | None = None) -> dict[str, Any]:
    """更新财产线索。只传需要修改的字段。

    Args:
        clue_id: 线索 ID。
        clue_type: 线索类型(如 银行账户/房产/车辆——见类型模板工具)。
        content: 线索内容(结构建议先取 get_property_clue_content_template)。
    """
    payload: dict[str, Any] = {}
    if clue_type is not None:
        payload["clue_type"] = clue_type
    if content is not None:
        payload["content"] = content
    return client.put(f"/client/property-clues/{clue_id}", json=payload)  # type: ignore[no-any-return]


def delete_property_clue(clue_id: int) -> None:
    """删除财产线索——硬删除,不可恢复。"""
    client.delete(f"/client/property-clues/{clue_id}")


def get_property_clue_content_template(clue_type: str) -> dict[str, Any]:
    """获取指定类型财产线索的内容模板（预填格式）。

    后端必填 query 参数 ``clue_type``。早前工具没传，调用必然 422。

    Args:
        clue_type: 财产线索类型（如 bank_account / real_estate / vehicle / equity）。
    """
    return client.get("/client/property-clues/content-template", params={"clue_type": clue_type})  # type: ignore[no-any-return]
