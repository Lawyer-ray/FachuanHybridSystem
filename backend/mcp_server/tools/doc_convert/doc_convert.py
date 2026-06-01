"""要素式转换 MCP tools"""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import unquote

from mcp_server.client import client


def list_doc_convert_types() -> dict[str, Any]:
    """获取支持的文书类型列表（mbid），按类别分组。需要系统启用 ZNSZJ_ENABLED。"""
    return client.get("/doc-convert/mbid-list")  # type: ignore[return-value]


def convert_document(file_base64: str, filename: str, mbid: str) -> dict[str, Any]:
    """将传统文书转换为要素式文书。file_base64 为 .docx/.doc/.pdf 文件的 base64 编码；mbid 为文书类型标识符（来自 list_doc_convert_types）。返回 {filename, content_type, data_base64}。"""
    file_bytes = base64.b64decode(file_base64)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "docx"
    mime_map = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "pdf": "application/pdf",
    }
    mime = mime_map.get(ext, "application/octet-stream")

    # convert 是 POST multipart + 返回二进制，直接操作底层 httpx
    resp = client._http.post(
        "/doc-convert/convert",
        headers=client._headers(),
        files={"file": (filename, file_bytes, mime)},
        data={"mbid": mbid},
    )
    if not resp.is_success:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise RuntimeError(f"HTTP {resp.status_code}: {detail}")

    content_type = resp.headers.get("content-type", "application/octet-stream")
    disposition = resp.headers.get("content-disposition", "")
    out_filename = "converted.docx"
    if disposition:
        m = re.search(r"filename\*=UTF-8''([^;]+)", disposition)
        if m:
            out_filename = unquote(m.group(1))
        else:
            m2 = re.search(r'filename="?([^";]+)"?', disposition)
            if m2:
                out_filename = m2.group(1).strip()

    return {
        "filename": out_filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(resp.content).decode(),
    }
