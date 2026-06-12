"""诉讼费计算 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def calculate_litigation_fee(
    case_type: str,
    target_amount: float,
    **extra: Any,
) -> dict[str, Any]:
    """计算诉讼费。case_type: civil（民事）/ administrative（行政）等；target_amount: 诉讼标的额。"""
    payload: dict[str, Any] = {"case_type": case_type, "target_amount": target_amount, **extra}
    return client.post("/cases/calculate-fee", json=payload)  # type: ignore[return-value]
