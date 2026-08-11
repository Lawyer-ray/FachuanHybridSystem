"""合同收款 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def create_payment(
    contract_id: int,
    payment_data: dict[str, Any],
) -> dict[str, Any]:
    """创建收款记录。payment_data 需包含: amount（收款金额，float，>0）；可选字段:
    received_at（收款日期，如 2026-01-01 字符串）、invoice_status（开票状态，如
    UNINVOICED/INVOICED_PARTIAL/INVOICED_FULL）、invoiced_amount（已开票金额，float，
    ≥0，默认 0）、note（备注字符串）、confirm（bool，必填为 True，否则后端拒绝）。"""
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
