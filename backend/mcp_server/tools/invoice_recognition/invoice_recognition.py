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
    # 统一走 client.upload:错误信封(FachuanApiError)与传输层异常翻译
    # (FachuanTransportError)由 client 管——此前直接 client._http.post 且
    # 引用了未 import 的 FachuanApiError,非 2xx 时会 NameError。
    return client.upload(  # type: ignore[no-any-return]
        "/invoice-recognition/quick-recognize",
        files=_build_invoice_files(files),
    )


def upload_invoices(task_id: int, files: list[dict[str, str]]) -> dict[str, Any]:
    """上传发票文件到指定任务并自动识别。files 为 [{base64: '...', filename: 'xxx.pdf'}, ...]。"""
    return client.upload(  # type: ignore[no-any-return]
        f"/invoice-recognition/{task_id}/upload",
        files=_build_invoice_files(files),
    )


def get_invoice_task_status(task_id: int, include_raw_text: bool = False) -> dict[str, Any]:
    """查询发票识别任务状态和发票记录列表。

    Args:
        task_id: 发票识别任务 ID。
        include_raw_text: 是否返回每条记录的 raw_text（OCR 全文），默认 False 以减少返回体积。
    """
    data: dict[str, Any] = client.get(f"/invoice-recognition/{task_id}/status")
    if not include_raw_text:
        for record in data.get("records", []):
            record.pop("raw_text", None)
    return data


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
    content, filename, content_type = client.download(f"/invoice-recognition/{task_id}/download", params=params)
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
