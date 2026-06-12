"""身份证件 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_identity_doc(doc_id: int) -> dict[str, Any]:
    """获取单个身份证件详情。"""
    return client.get(f"/client/identity-docs/{doc_id}")  # type: ignore[return-value]


def delete_identity_doc(doc_id: int) -> None:
    """删除身份证件。此操作不可逆。"""
    client.delete(f"/client/identity-docs/{doc_id}")
