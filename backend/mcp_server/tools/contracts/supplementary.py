"""补充协议 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_supplementary_agreements(contract_id: int) -> dict[str, Any]:
    """查询合同的补充协议列表（按主合同归组）。"""
    return list_result(client.get(f"/contracts/contracts/{contract_id}/supplementary-agreements"))


def get_supplementary_agreement(agreement_id: int) -> dict[str, Any]:
    """获取单个补充协议详情（条款内容、签署状态）。"""
    return client.get(f"/contracts/supplementary-agreements/{agreement_id}")  # type: ignore[no-any-return]


def create_supplementary_agreement(contract_id: int, agreement_data: dict[str, Any]) -> dict[str, Any]:
    """创建补充协议。

    Args:
        contract_id: 主合同 ID（后端 ``SupplementaryAgreementIn`` 必填）。
        agreement_data: 其余字段（name、parties、party_ids 等）。
    """
    payload: dict[str, Any] = {"contract_id": contract_id, **agreement_data}
    return client.post("/contracts/supplementary-agreements", json=payload)  # type: ignore[no-any-return]


def update_supplementary_agreement(
    agreement_id: int,
    agreement_data: dict[str, Any],
) -> dict[str, Any]:
    """更新补充协议。只传需要修改的字段。"""
    return client.put(f"/contracts/supplementary-agreements/{agreement_id}", json=agreement_data)  # type: ignore[no-any-return]


def delete_supplementary_agreement(agreement_id: int) -> None:
    """删除补充协议——硬删除,不可恢复（主合同不受影响）。"""
    client.delete(f"/contracts/supplementary-agreements/{agreement_id}")
