"""财务付款 MCP tools（从 contracts 域迁移）"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_payments(
    contract_id: int | None = None,
    payment_type: str | None = None,
) -> list[dict[str, Any]]:
    """查询付款记录列表。可按合同 ID（contract_id）和付款类型（payment_type）筛选。"""
    params: dict[str, Any] = {}
    if contract_id is not None:
        params["contract_id"] = contract_id
    if payment_type:
        params["payment_type"] = payment_type
    return client.get("/contracts/finance/payments", params=params)  # type: ignore[return-value]


def get_finance_stats() -> dict[str, Any]:
    """获取财务统计概览，包含总收款、待收款、本月收款等汇总数据。"""
    return client.get("/contracts/finance/stats")  # type: ignore[return-value]
