"""OA 立案 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_oa_configs() -> list[dict[str, Any]]:
    """获取当前用户可用的 OA 系统列表（需要有对应账号凭证）。"""
    return client.get("/oa-filing/configs")  # type: ignore[return-value]


def trigger_oa_filing(
    contract_id: int,
    site_name: str,
    case_id: int | None = None,
) -> dict[str, Any]:
    """发起 OA 立案。site_name 为 OA 系统名称（如 jczd）。返回立案会话信息，可用 get_filing_status 查询进度。"""
    payload: dict[str, Any] = {"contract_id": contract_id, "site_name": site_name}
    if case_id is not None:
        payload["case_id"] = case_id
    return client.post("/oa-filing/execute", json=payload)  # type: ignore[return-value]


def get_filing_status(session_id: int) -> dict[str, Any]:
    """查询 OA 立案进度。返回状态（pending/running/completed/failed）和错误信息。"""
    return client.get(f"/oa-filing/session/{session_id}")  # type: ignore[return-value]
