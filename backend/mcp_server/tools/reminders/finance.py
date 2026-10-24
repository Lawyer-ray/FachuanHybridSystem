"""财务付款 MCP tools（从 contracts 域迁移）"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_payments(
    contract_id: int | None = None,
    invoice_status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """查询收款记录列表。可按合同 ID（contract_id）、开票状态（invoice_status）、
    收款日期范围（start_date/end_date，ISO 格式）筛选。

    invoice_status 取值（**大写**）：UNINVOICED（未开票）/ INVOICED_PARTIAL
    （部分开票）/ INVOICED_FULL（已开票）。

    limit 默认 200——REST 端点本无截断,2026-10-25 补的可选参数;需要更多时
    显式调大（上限 2000）。注意:历史版本的 payment_type 参数从未生效
    （REST 不支持,ninja 静默忽略），已移除。
    """
    params: dict[str, Any] = {"limit": limit}
    if contract_id is not None:
        params["contract_id"] = contract_id
    if invoice_status:
        params["invoice_status"] = invoice_status
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return client.get("/contracts/finance/payments", params=params)  # type: ignore[return-value]


def get_finance_stats() -> dict[str, Any]:
    """获取财务统计概览，包含总收款、待收款、本月收款等汇总数据。"""
    return client.get("/contracts/finance/stats")  # type: ignore[return-value]
