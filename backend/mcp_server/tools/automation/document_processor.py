"""文档处理器 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def process_document(
    file_path: str, kind: str | None = None, limit: int | None = None, preview_page: int | None = None
) -> dict[str, Any]:
    """处理文档，返回图片 URL 和文本摘要。"""
    params: dict[str, Any] = {"file_path": file_path}
    if kind is not None:
        params["kind"] = kind
    if limit is not None:
        params["limit"] = limit
    if preview_page is not None:
        params["preview_page"] = preview_page
    return client.post("/automation/document-processor/process", params=params, json={})  # type: ignore[return-value]


def process_document_by_path(
    file_path: str, limit: int | None = None, preview_page: int | None = None
) -> dict[str, Any]:
    """按路径处理文档（无需指定 kind）。"""
    params: dict[str, Any] = {"file_path": file_path}
    if limit is not None:
        params["limit"] = limit
    if preview_page is not None:
        params["preview_page"] = preview_page
    return client.post("/automation/document-processor/process-by-path", params=params, json={})  # type: ignore[return-value]
