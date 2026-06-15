"""法院短信处理 MCP tools"""

from __future__ import annotations

import base64
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
    """重新处理法院短信。已绑定案件的保留关联，仅重新执行下载/重命名/通知；未绑定的重新执行完整流程。"""
    return client.post(f"/automation/court-sms/{sms_id}/retry", json={})  # type: ignore[return-value]


def delete_court_sms(sms_id: int) -> None:
    """删除法院短信记录。此操作不可逆。"""
    client.delete(f"/automation/court-sms/{sms_id}")


def download_sms_documents(sms_id: int) -> list[dict[str, Any]]:
    """下载法院短信关联的所有文书文档。返回文书列表。"""
    return client.get(f"/automation/court-sms/{sms_id}/documents/download-all")  # type: ignore[return-value]


def download_sms_document(sms_id: int, ref_index: int) -> dict[str, Any]:
    """下载法院短信关联的单个文书。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/automation/court-sms/{sms_id}/documents/{ref_index}/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
