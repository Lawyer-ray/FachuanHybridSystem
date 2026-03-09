"""案件进展日志 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_case_logs(case_id: int) -> list[dict[str, Any]]:
    """查询指定案件的所有进展日志，按时间倒序排列。"""
    return client.get("/cases/logs", params={"case_id": case_id})  # type: ignore[return-value]


def create_case_log(case_id: int, content: str) -> dict[str, Any]:
    """为案件添加进展日志。content 为日志内容，支持多行文本。"""
    return client.post("/cases/logs", json={"case_id": case_id, "content": content})  # type: ignore[return-value]


def list_case_numbers(case_id: int) -> list[dict[str, Any]]:
    """查询指定案件的所有案号记录。"""
    return client.get("/cases/case-numbers", params={"case_id": case_id})  # type: ignore[return-value]


def create_case_number(case_id: int, number: str, remarks: str | None = None) -> dict[str, Any]:
    """为案件添加案号。number 为案号字符串，remarks 为备注。"""
    payload: dict[str, Any] = {"case_id": case_id, "number": number}
    if remarks:
        payload["remarks"] = remarks
    return client.post("/cases/case-numbers", json=payload)  # type: ignore[return-value]


def assign_lawyer(case_id: int, lawyer_id: int) -> dict[str, Any]:
    """为案件指派律师。"""
    return client.post("/cases/assignments", json={"case_id": case_id, "lawyer_id": lawyer_id})  # type: ignore[return-value]


def list_case_assignments(case_id: int) -> list[dict[str, Any]]:
    """查询案件的律师指派记录。"""
    return client.get("/cases/assignments", params={"case_id": case_id})  # type: ignore[return-value]
