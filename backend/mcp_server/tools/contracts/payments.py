"""合同收款 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def create_payment(
    contract_id: int,
    payment_data: dict[str, Any],
) -> dict[str, Any]:
    """创建收款记录。payment_data 包含 amount（金额）、payment_date（日期）、payment_type（类型）等字段。"""
    payload: dict[str, Any] = {"contract_id": contract_id, **payment_data}
    return client.post("/contracts/finance/payments", json=payload)  # type: ignore[return-value]


def update_payment(
    payment_id: int,
    payment_data: dict[str, Any],
) -> dict[str, Any]:
    """更新收款记录。只传需要修改的字段。"""
    return client.put(f"/contracts/finance/payments/{payment_id}", json=payment_data)  # type: ignore[return-value]


def delete_payment(payment_id: int) -> None:
    """删除指定收款记录。此操作不可逆。"""
    client.delete(f"/contracts/finance/payments/{payment_id}")
