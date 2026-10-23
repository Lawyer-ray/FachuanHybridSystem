"""Agent 对话附件读取 —— 模型按 attachment_id 取附件正文。

## 为什么不是把 base64 给模型

对话附件（PDF/图片/文档）由前端上传、服务端存档（apps/agent
services/attachments.py）。模型要的是**正文文本**，不是文件字节：
base64 过模型上下文意味着 500KB PDF ≈ 数十万 token，且模型回显长
base64 不可靠。本工具在 mcp_server 侧把文件转投 /document-parsing
提取文本（图片类按 MIME 走 OCR 后端），模型只看到正文。

## 链路

    read_agent_attachment(attachment_id)
      → GET /agent/attachments/{id}/content（律师身份，归属校验在服务端）
      → 文本类直接解码；其余 POST /document-parsing/extract-text
      → {filename, mime, chars, truncated, content}
"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client

#: 正文回给模型的默认上限（字符）——大材料应显式分段/收敛查询
DEFAULT_MAX_LENGTH = 20000

_TEXT_MIMES = {"text/plain"}
#: 与 apps/agent 附件白名单一致；解析端点按 MIME 选后端
_CONTENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".txt": "text/plain",
}


def _content_type_for(filename: str) -> str:
    lowered = filename.lower()
    for suffix, mime in _CONTENT_TYPES.items():
        if lowered.endswith(suffix):
            return mime
    return "application/octet-stream"


def read_agent_attachment(
    attachment_id: str,
    max_length: int = DEFAULT_MAX_LENGTH,
    start: int = 0,
) -> dict[str, Any]:
    """读取一个对话附件的正文文本。

    用户消息里的「[已上传附件：name (attachment_id=…)]」引用用本工具取内容：
    文本类直接返回；PDF/Word/图片由解析服务提取（图片走 OCR 后端）。
    返回 content 为提取的正文；超长时截断并置 truncated=true，
    用 start 从下一分段继续读。

    Args:
        attachment_id: 消息里引用的附件标识。
        max_length: 本次返回的正文上限（字符），默认 20000。
        start: 从正文的第几个字符开始读（分段读长材料用）。
    """
    info: dict[str, Any] = client.get(f"/agent/attachments/{attachment_id}/content")
    filename = str(info.get("filename") or "")
    mime = str(info.get("mime") or "")
    payload = str(info.get("content_base64") or "")
    file_bytes = base64.b64decode(payload) if payload else b""

    offset = max(0, int(start))
    limit = max(1000, int(max_length))
    if mime in _TEXT_MIMES or filename.lower().endswith(".txt"):
        text = file_bytes.decode("utf-8", errors="replace")
    else:
        # 分段读：向解析端点多要 offset 那一段，再在本地切片
        result = client.upload(
            "/document-parsing/extract-text",
            files={"file": (filename, file_bytes, _content_type_for(filename))},
            data={"backend": "auto", "max_length": str(offset + limit)},
        )
        text = str(result.get("text") or "")
        if not result.get("success", True) and not text:
            reason = str(result.get("error") or result.get("status") or "解析失败")
            return {
                "attachment_id": attachment_id,
                "filename": filename,
                "mime": mime,
                "chars": 0,
                "truncated": False,
                "content": "",
                "error": f"附件解析失败：{reason}",
            }

    truncated = len(text) > offset + limit
    return {
        "attachment_id": attachment_id,
        "filename": filename,
        "mime": mime,
        "chars": len(text),
        "truncated": truncated,
        "content": text[offset : offset + limit],
    }
