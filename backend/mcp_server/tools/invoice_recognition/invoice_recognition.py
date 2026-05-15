"""发票识别 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def _build_invoice_files(files: list[dict[str, str]]) -> dict[str, Any]:
    """将 [{base64, filename}] 转为 httpx files 格式（多文件同字段名）。"""
    result = []
    for f in files:
        file_bytes = base64.b64decode(f["base64"])
        filename = f.get("filename", "invoice.pdf")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
        mime = "application/pdf" if ext == "pdf" else f"image/{ext}"
        result.append(("files", (filename, file_bytes, mime)))
    return result  # type: ignore[return-value]


def quick_recognize_invoice(files: list[dict[str, str]]) -> dict[str, Any]:
    """快速识别发票（不创建任务）。files 为 [{base64: '...', filename: 'xxx.pdf'}, ...]。返回识别结果列表。"""
    file_list = _build_invoice_files(files)
    resp = client._http.post(
        "/invoice-recognition/quick-recognize",
        headers=client._headers(),
        files=file_list,
    )
    if not resp.is_success:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
    return resp.json()  # type: ignore[return-value]


def upload_invoices(task_id: int, files: list[dict[str, str]]) -> dict[str, Any]:
    """上传发票文件到指定任务并自动识别。files 为 [{base64: '...', filename: 'xxx.pdf'}, ...]。"""
    file_list = _build_invoice_files(files)
    resp = client._http.post(
        f"/invoice-recognition/{task_id}/upload",
        headers=client._headers(),
        files=file_list,
    )
    if not resp.is_success:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
    return resp.json()  # type: ignore[return-value]


def get_invoice_task_status(task_id: int) -> dict[str, Any]:
    """查询发票识别任务状态和发票记录列表。"""
    return client.get(f"/invoice-recognition/{task_id}/status")  # type: ignore[return-value]


def download_invoices(
    task_id: int,
    scope: str,
    fmt: str = "zip",
    invoice_id: int | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """下载发票文件。scope: single（单张）/category（按类别）/all（全部）；fmt: pdf/zip；scope=single 时需传 invoice_id；scope=category 时需传 category。返回 {filename, content_type, data_base64}。"""
    params: dict[str, Any] = {"scope": scope, "fmt": fmt}
    if invoice_id is not None:
        params["invoice_id"] = invoice_id
    if category is not None:
        params["category"] = category
    content, filename, content_type = client.download(
        f"/invoice-recognition/{task_id}/download", params=params
    )
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
