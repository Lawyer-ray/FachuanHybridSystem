"""收件箱消息 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_inbox_messages(
    source_id: int | None = None,
    has_attachments: bool | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """查询收件箱消息列表。可按来源（source_id）、是否有附件（has_attachments）、关键词（search）筛选。"""
    params: dict[str, Any] = {}
    if source_id is not None:
        params["source_id"] = source_id
    if has_attachments is not None:
        params["has_attachments"] = has_attachments
    if search:
        params["search"] = search
    return client.get("/inbox/messages", params=params)  # type: ignore[return-value]


def get_inbox_message(message_id: int) -> dict[str, Any]:
    """获取单条消息的详细信息，包含正文（text/html）和附件列表。"""
    return client.get(f"/inbox/messages/{message_id}")  # type: ignore[return-value]


def rename_inbox_attachment(
    message_id: int,
    part_index: int,
    custom_filename: str,
) -> dict[str, Any]:
    """重命名消息附件。custom_filename 为空字符串时恢复原始文件名。"""
    payload: dict[str, Any] = {"custom_filename": custom_filename}
    return client.post(
        f"/inbox/messages/{message_id}/attachments/{part_index}/rename",
        json=payload,
    )  # type: ignore[return-value]


def download_inbox_attachment(message_id: int, part_index: int) -> dict[str, Any]:
    """下载消息附件，返回文件内容（base64 编码）。"""
    content, filename, content_type = client.download(
        f"/inbox/messages/{message_id}/attachments/{part_index}/download",
    )
    import base64

    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode("ascii"),
    }


def preview_inbox_attachment(message_id: int, part_index: int) -> dict[str, Any]:
    """预览消息附件（在线查看），返回文件内容（base64 编码）。"""
    content, filename, content_type = client.download(
        f"/inbox/messages/{message_id}/attachments/{part_index}/preview",
    )
    import base64

    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode("ascii"),
    }
