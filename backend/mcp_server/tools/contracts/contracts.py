"""合同 CRUD MCP tools"""

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


def create_contract(
    name: str,
    case_type: str,
    lawyer_ids: list[int],
    status: str | None = None,
    fixed_amount: float | None = None,
    fee_mode: str | None = None,
) -> dict[str, Any]:
    """创建新合同。case_type 同案件类型；lawyer_ids 第一个为主办律师；fee_mode：fixed（固定）或 risk（风险代理）。"""
    payload: dict[str, Any] = {"name": name, "case_type": case_type, "lawyer_ids": lawyer_ids}
    if status:
        payload["status"] = status
    if fixed_amount is not None:
        payload["fixed_amount"] = fixed_amount
    if fee_mode:
        payload["fee_mode"] = fee_mode
    return client.post("/contracts/contracts", json=payload)  # type: ignore[return-value]
