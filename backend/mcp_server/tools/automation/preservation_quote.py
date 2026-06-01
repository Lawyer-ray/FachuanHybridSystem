"""财产保全询价 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def create_preservation_quote(
    preserve_amount: float,
    corp_id: str,
    category_id: str,
    credential_id: int,
) -> dict[str, Any]:
    """创建财产保全担保费询价任务。preserve_amount 为保全金额；corp_id 为法院/企业ID；category_id 为分类ID；credential_id 为账号凭证ID。"""
    return client.post(
        "/automation/preservation-quotes",
        json={
            "preserve_amount": preserve_amount,
            "corp_id": corp_id,
            "category_id": category_id,
            "credential_id": credential_id,
        },
    )  # type: ignore[return-value]


def list_preservation_quotes(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    """查询财产保全询价任务列表。status 可选：pending/running/success/partial_success/failed。"""
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    return client.get("/automation/preservation-quotes", params=params)  # type: ignore[return-value]


def get_preservation_quote(quote_id: int) -> dict[str, Any]:
    """获取询价任务详情，包含所有保险公司的报价记录。"""
    return client.get(f"/automation/preservation-quotes/{quote_id}")  # type: ignore[return-value]


def execute_preservation_quote(quote_id: int) -> dict[str, Any]:
    """执行询价任务，并发查询所有保险公司报价。返回执行结果统计。"""
    return client.post(f"/automation/preservation-quotes/{quote_id}/execute", json={})  # type: ignore[return-value]
