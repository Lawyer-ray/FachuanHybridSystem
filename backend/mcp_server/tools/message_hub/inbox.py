"""收件箱消息 MCP tools"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_inbox_messages(
    source_id: Annotated[int | None, Field(description="按消息来源筛选(来源 ID 见 list_message_sources)")] = None,
    has_attachments: Annotated[bool | None, Field(description="按是否有附件筛选")] = None,
    search: Annotated[str | None, Field(description="主题/发件人/正文关键词")] = None,
    limit: Annotated[int, Field(description="最多返回条数(默认 30,约 0.57KB/条,默认调用留在 20KB 截断线内)", ge=1)] = 30,
    offset: Annotated[int, Field(description="跳过前 offset 条再取——truncated=true 时续取翻页用(第 N 页传 offset=N×limit)", ge=0)] = 0,
) -> dict[str, Any]:
    """查询收件箱消息列表。可按来源（source_id）、是否有附件（has_attachments）、关键词（search）筛选。

    limit 默认 30（实测约 0.57KB/条,30 条 ≈ 17KB——pi 对工具输出 20KB 起
    腰斩,默认调用应留在截断线内;REST 端点默认 500 是给前端收件箱的）;
    truncated=true 时用 offset 续取(第 N 页传 offset=N×limit),或换更窄筛选。

    Args:
        source_id: 按消息来源筛选。
        has_attachments: 按是否有附件筛选。
        search: 主题/发件人/正文关键词。
        limit: 最多返回条数(默认 30)。
        offset: 跳过前 offset 条再取——续取翻页用。
    """
    params: dict[str, Any] = {"limit": limit + 1, "offset": offset}  # limit+1 探测:知还有更多
    if source_id is not None:
        params["source_id"] = source_id
    if has_attachments is not None:
        params["has_attachments"] = has_attachments
    if search:
        params["search"] = search
    return list_result(client.get("/inbox/messages", params=params), limit=limit)


def get_inbox_message(message_id: int) -> dict[str, Any]:
    """获取单条消息的详细信息，包含正文（text/html）和附件列表。"""
    return client.get(f"/inbox/messages/{message_id}")  # type: ignore[no-any-return]


def rename_inbox_attachment(
    message_id: int,
    part_index: int,
    custom_filename: str,
) -> dict[str, Any]:
    """重命名消息附件。custom_filename 为空字符串时恢复原始文件名。"""
    payload: dict[str, Any] = {"custom_filename": custom_filename}
    return client.post(  # type: ignore[no-any-return]
        f"/inbox/messages/{message_id}/attachments/{part_index}/rename",
        json=payload,
    )


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
