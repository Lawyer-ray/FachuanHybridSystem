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


def create_contract_with_cases(
    contract_data: dict[str, Any],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """创建合同并同时关联案件。contract_data 为合同字段（name、case_type、lawyer_ids 等）；cases 为案件列表（每项含 case_type、client_name 等）。"""
    payload: dict[str, Any] = {**contract_data, "cases": cases}
    return client.post("/contracts/contracts/full", json=payload)  # type: ignore[return-value]


def update_contract(
    contract_id: int,
    contract_data: dict[str, Any],
    sync_cases: bool = False,
    confirm_finance: bool = False,
) -> dict[str, Any]:
    """更新合同信息。contract_data 为需要修改的字段；sync_cases 为 True 时同步更新关联案件；confirm_finance 为 True 时确认财务变动。"""
    params: dict[str, Any] = {}
    if sync_cases:
        params["sync_cases"] = sync_cases
    if confirm_finance:
        params["confirm_finance"] = confirm_finance
    return client.put(
        f"/contracts/contracts/{contract_id}",
        json=contract_data,
        params=params,
    )  # type: ignore[return-value]


def delete_contract(contract_id: int) -> None:
    """删除指定合同。此操作不可逆。"""
    client.delete(f"/contracts/contracts/{contract_id}")


def update_contract_lawyers(
    contract_id: int,
    lawyer_ids: list[int],
) -> dict[str, Any]:
    """更新合同的律师指派。lawyer_ids 第一个为主办律师。"""
    payload: dict[str, Any] = {"lawyer_ids": lawyer_ids}
    return client.put(f"/contracts/contracts/{contract_id}/lawyers", json=payload)  # type: ignore[return-value]


def get_contract_all_parties(contract_id: int) -> dict[str, Any]:
    """获取合同全部当事人信息，包含原告、被告、第三人等分组。"""
    return client.get(f"/contracts/contracts/{contract_id}/all-parties")  # type: ignore[return-value]
