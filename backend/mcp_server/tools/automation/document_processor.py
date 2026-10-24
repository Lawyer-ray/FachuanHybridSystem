"""文档处理器 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def process_document(
    file_path: str, kind: str | None = None, limit: int | None = None, preview_page: int | None = None
) -> dict[str, Any]:
    """解析文档（PDF/图片等）,返回可浏览的图片 URL 与文本摘要——大文档预览入口。"""
    params: dict[str, Any] = {"file_path": file_path}
    if kind is not None:
        params["kind"] = kind
    if limit is not None:
        params["limit"] = limit
    if preview_page is not None:
        params["preview_page"] = preview_page
    return client.post("/automation/document-processor/process", params=params, json={})  # type: ignore[return-value]


def process_document_by_path(
    file_path: str,
    kind: str,
    limit: int | None = None,
    preview_page: int | None = None,
) -> dict[str, Any]:
    """按服务器上的文件路径处理文档。

    后端 ``DocumentProcessIn`` 必填 ``file_path`` **和** ``kind``（处理种类）。
    早前 docstring 写「无需指定 kind」且确实没传，调用必然 422。

    Args:
        file_path: 服务器上的文件路径。
        kind: 处理种类（如 pdf / docx / image）。
        limit: 可选，最多处理多少页。
        preview_page: 可选，预览页序号。
    """
    payload: dict[str, Any] = {"file_path": file_path, "kind": kind}
    if limit is not None:
        payload["limit"] = limit
    if preview_page is not None:
        payload["preview_page"] = preview_page
    return client.post("/automation/document-processor/process-by-path", json=payload)  # type: ignore[no-any-return]
