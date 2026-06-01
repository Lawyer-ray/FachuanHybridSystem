"""案件当事人 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_case_parties(case_id: int) -> list[dict[str, Any]]:
    """查询指定案件的所有当事人，包含客户详情和诉讼地位。"""
    return client.get("/cases/parties", params={"case_id": case_id})  # type: ignore[return-value]


def add_case_party(case_id: int, client_id: int, legal_status: str | None = None) -> dict[str, Any]:
    """为案件添加当事人。legal_status 为诉讼地位，如：原告、被告、第三人等。"""
    payload: dict[str, Any] = {"case_id": case_id, "client_id": client_id}
    if legal_status:
        payload["legal_status"] = legal_status
    return client.post("/cases/parties", json=payload)  # type: ignore[return-value]
