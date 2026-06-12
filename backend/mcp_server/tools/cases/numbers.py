"""案号 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_case_numbers(case_id: int) -> list[dict[str, Any]]:
    """查询指定案件的所有案号记录。"""
    return client.get("/cases/case-numbers", params={"case_id": case_id})  # type: ignore[return-value]


def create_case_number(case_id: int, number: str, remarks: str | None = None) -> dict[str, Any]:
    """为案件添加案号。number 为案号字符串，remarks 为备注。"""
    payload: dict[str, Any] = {"case_id": case_id, "number": number}
    if remarks:
        payload["remarks"] = remarks
    return client.post("/cases/case-numbers", json=payload)  # type: ignore[return-value]


def get_case_number(number_id: int) -> dict[str, Any]:
    """获取单个案号详情。"""
    return client.get(f"/cases/case-numbers/{number_id}")  # type: ignore[return-value]


def update_case_number(number_id: int, number: str | None = None, remarks: str | None = None) -> dict[str, Any]:
    """更新案号信息。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if number is not None:
        payload["number"] = number
    if remarks is not None:
        payload["remarks"] = remarks
    return client.put(f"/cases/case-numbers/{number_id}", json=payload)  # type: ignore[return-value]


def delete_case_number(number_id: int) -> None:
    """删除案号记录。"""
    client.delete(f"/cases/case-numbers/{number_id}")
