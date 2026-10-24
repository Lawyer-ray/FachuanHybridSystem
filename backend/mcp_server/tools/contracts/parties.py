"""合同当事人 / 客户关联全景 MCP tools。

## 为什么单独拆出来

`get_contract` 返回的是合同自身字段，`get_client` 返回的是客户自身字段，
但律师真正要问的是「这个客户还有哪些在办案件和合同」「这个合同的当事人
都齐了吗」。这两类问题在系统里都有专门端点（``related-items`` /
``parties``），此前没有暴露给 agent，模型只能自己拼多个工具，既慢又容易漏。
"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_client_related_items(client_id: int) -> dict[str, Any]:
    """一次性拿到某个客户关联的全部案件与合同（客户全景）。

    回答「这个客户还有哪些案子」「我们和这家公司签过几份合同」时用它，
    比先 list_cases 再逐个过滤准确得多（后端已按访问权限过滤）。

    Args:
        client_id: 客户 ID。

    Returns:
        ``{cases: [...], contracts: [...]}``
    """
    return client.get(f"/client/clients/{client_id}/related-items")  # type: ignore[no-any-return]


def add_contract_party(contract_id: int, client_id: int, role: str = "principal") -> dict[str, Any]:
    """给合同添加当事人（已存在则更新其角色）。

    Args:
        contract_id: 合同 ID。
        client_id: 客户 ID。
        role: 当事人角色，默认 ``principal``（委托人）；常见值还有
            ``opposing``（对方）等，取值同后端 PartyRole 枚举。
    """
    return client.post(  # type: ignore[no-any-return]
        f"/contracts/contracts/{contract_id}/parties",
        json={"client_id": client_id, "role": role},
    )


def remove_contract_party(contract_id: int, client_id: int) -> dict[str, Any]:
    """从合同中移除当事人。

    Args:
        contract_id: 合同 ID。
        client_id: 客户 ID。
    """
    return client.delete(f"/contracts/contracts/{contract_id}/parties/{client_id}")  # type: ignore[no-any-return]
