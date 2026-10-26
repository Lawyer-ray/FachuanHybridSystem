"""身份证件 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_identity_doc(doc_id: int) -> dict[str, Any]:
    """获取单个身份证件详情（类型、号码、归属人）。"""
    return client.get(f"/client/identity-docs/{doc_id}")  # type: ignore[no-any-return]


def delete_identity_doc(doc_id: int) -> None:
    """删除身份证件记录——硬删除,不可恢复。"""
    client.delete(f"/client/identity-docs/{doc_id}")
