"""合同相关 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_contracts(
    case_type: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """查询合同列表。可按案件类型（case_type）和状态（status）筛选。"""
    params: dict[str, Any] = {}
    if case_type:
        params["case_type"] = case_type
    if status:
        params["status"] = status
    return client.get("/contracts/contracts", params=params)  # type: ignore[return-value]


def get_contract(contract_id: int) -> dict[str, Any]:
    """获取单个合同的详细信息，包含关联案件、当事人、律师指派、付款记录等。"""
    return client.get(f"/contracts/contracts/{contract_id}")  # type: ignore[return-value]
