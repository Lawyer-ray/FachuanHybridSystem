"""法院短信处理 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import FachuanApiError, client


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
) -> dict[str, Any]:
    """查询法院短信列表。

    Args:
        status: 处理状态（pending / processing / completed / failed）。
        sms_type: 短信类型。
        has_case: True 只查已关联案件的。
        date_from / date_to: 接收时间范围（YYYY-MM-DD）。

    Returns:
        后端 ``PagedCourtSMSListOut`` 原样：``{items, count}``。注意计数字段叫
        ``count`` 而非 ``total``——之前用 ``as_items`` 包壳时 docstring 写的是
        ``{items, total, page, page_size}``，与实际返回并不一致。
    """
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
    payload: dict[str, Any] = client.get("/automation/court-sms", params=params)  # type: ignore[assignment]
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise FachuanApiError(
            f"/automation/court-sms 返回了非分页结构: {type(payload).__name__}；后端契约可能已变更，请检查"
        )
    return payload


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
    """删除法院短信记录——硬删除,不可恢复。"""
    client.delete(f"/automation/court-sms/{sms_id}")


def download_sms_documents(sms_id: int) -> dict[str, Any]:
    """打包下载法院短信关联的全部文书（后端返回 ZIP）。

    返回 ``{filename, content_type, data_base64}``，与 ``download_sms_document``
    一致。早前用 ``client.get`` 请求该端点并声明 ``list[dict]``——后端是
    ``FileResponse`` 二进制流，``resp.json()`` 必然抛异常，工具永久不可用。
    """
    content, filename, content_type = client.download(f"/automation/court-sms/{sms_id}/documents/download-all")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def download_sms_document(sms_id: int, ref_index: int) -> dict[str, Any]:
    """下载法院短信关联的单个文书。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/automation/court-sms/{sms_id}/documents/{ref_index}/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
