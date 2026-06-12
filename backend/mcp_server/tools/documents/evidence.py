"""证据管理 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def reorder_evidence_items(list_id: int, item_ids: list[int]) -> dict[str, Any]:
    """重新排列证据列表中的证据项顺序。"""
    return client.post(f"/evidence/evidence-lists/{list_id}/reorder", json={"item_ids": item_ids})  # type: ignore[return-value]
