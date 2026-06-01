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
