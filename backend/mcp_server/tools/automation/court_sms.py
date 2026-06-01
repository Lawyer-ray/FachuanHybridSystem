"""法院短信处理 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def submit_court_sms(
    content: str,
    received_at: str | None = None,
    sender: str | None = None,
) -> dict[str, Any]:
    """提交法院短信。content 为短信内容；received_at 为接收时间（ISO格式）；sender 为发件人号码。"""
    payload: dict[str, Any] = {"content": content}
    if received_at:
        payload["received_at"] = received_at
    if sender:
        payload["sender"] = sender
    return client.post("/automation/court-sms", json=payload)  # type: ignore[return-value]


def list_court_sms(
    status: str | None = None,
    sms_type: str | None = None,
    has_case: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """查询法院短信列表。status 可选：pending/processing/completed/failed；has_case=True 只查已关联案件的。"""
    params: dict[str, Any] = {}
    if status:
        params["status"] = status
    if sms_type:
        params["sms_type"] = sms_type
    if has_case is not None:
        params["has_case"] = has_case
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    return client.get("/automation/court-sms", params=params)  # type: ignore[return-value]


def get_court_sms_detail(sms_id: int) -> dict[str, Any]:
    """查询单条法院短信的处理详情，包含解析结果和关联案件信息。"""
    return client.get(f"/automation/court-sms/{sms_id}")  # type: ignore[return-value]


def assign_sms_case(sms_id: int, case_id: int) -> dict[str, Any]:
    """手动为法院短信指定关联案件（自动匹配失败时使用）。"""
    return client.post(f"/automation/court-sms/{sms_id}/assign-case", json={"case_id": case_id})  # type: ignore[return-value]


def retry_sms_processing(sms_id: int) -> dict[str, Any]:
    """重新处理法院短信（重置状态并重新执行完整处理流程）。"""
    return client.post(f"/automation/court-sms/{sms_id}/retry", json={})  # type: ignore[return-value]
