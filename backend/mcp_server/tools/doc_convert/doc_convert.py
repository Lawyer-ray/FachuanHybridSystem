"""要素式转换 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def list_doc_convert_types() -> dict[str, Any]:
    """获取支持的文书类型列表（mbid），按类别分组。需要系统启用 ZNSZJ_ENABLED。"""
    return client.get("/doc-convert/mbid-list")  # type: ignore[no-any-return]


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

    # multipart 上传 + 二进制返回,统一走 client.download:享受 1MB 输出
    # 闸门(base64 不挤爆会话上下文)、传输层异常翻译(FachuanTransportError)
    # 与 Content-Disposition 解析——此前直接 client._http.post 三者全绕过。
    # LibreOffice 同步转换,大文书(目录/表格)冷启动可超 60s 默认超时。
    content, out_filename, content_type = client.download(
        "/doc-convert/convert",
        method="POST",
        files={"file": (filename, file_bytes, mime)},
        data={"mbid": mbid},
        timeout=180,
    )
    return {
        "filename": out_filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode("ascii"),
    }
