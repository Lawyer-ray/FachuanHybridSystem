"""补充协议 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_supplementary_agreements(contract_id: int) -> list[dict[str, Any]]:
    """查询指定合同的补充协议列表。"""
    return client.get(f"/contracts/contracts/{contract_id}/supplementary-agreements")  # type: ignore[return-value]


def get_supplementary_agreement(agreement_id: int) -> dict[str, Any]:
    """获取单个补充协议的详细信息。"""
    return client.get(f"/contracts/supplementary-agreements/{agreement_id}")  # type: ignore[return-value]


def create_supplementary_agreement(agreement_data: dict[str, Any]) -> dict[str, Any]:
    """创建补充协议。agreement_data 包含 contract_id、name、content 等字段。"""
    return client.post("/contracts/supplementary-agreements", json=agreement_data)  # type: ignore[return-value]


def update_supplementary_agreement(
    agreement_id: int,
    agreement_data: dict[str, Any],
) -> dict[str, Any]:
    """更新补充协议。只传需要修改的字段。"""
    return client.put(f"/contracts/supplementary-agreements/{agreement_id}", json=agreement_data)  # type: ignore[return-value]


def delete_supplementary_agreement(agreement_id: int) -> None:
    """删除指定补充协议。此操作不可逆。"""
    client.delete(f"/contracts/supplementary-agreements/{agreement_id}")
