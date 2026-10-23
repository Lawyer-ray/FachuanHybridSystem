"""Agent 对话附件 —— 上传存档与服务端读取。

## 链路

    前端拖拽/选择文件
      → POST /agent/sessions/{id}/attachments（multipart，归属校验）
      → save_uploaded_file（清洗/扩展名白名单/20MB 限额/工厂路径）
      → AgentAttachment 落库（路径 + 元数据）

    用户发消息时附带「[已上传附件：name (attachment_id=…)]」引用
      → 模型调 mcp__fachuan__read_agent_attachment(attachment_id)
      → GET /agent/attachments/{id}/content（以律师身份，归属校验）
      → mcp_server 把文件投给 /document-parsing/extract-text 提取正文
      → 模型只看到文本（base64 与大文件不进模型上下文）

## 为什么不让模型直接拿 base64

工具参数里传 base64 意味着全文要过一遍模型 token（500KB PDF ≈ 数十万
token，且模型回显长 base64 不可靠）——服务端提取文本是唯一可行路径，
图片类由解析端点按 MIME 走 OCR 后端。
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from django.core.files.storage import default_storage

from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.services.storage_service import save_uploaded_file

from ..models import AgentAttachment, AgentSession

#: 与解析端点支持面对齐（mcp_server/tools/documents/parsing._CONTENT_TYPES）
ALLOWED_EXTENSIONS = [".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".txt"]
MAX_SIZE_BYTES = 20 * 1024 * 1024


def create_attachment(*, session: AgentSession, user_id: int | None, uploaded_file: Any) -> AgentAttachment:
    """保存一个上传文件并落库（校验/清洗全部由 save_uploaded_file 承担）。

    Raises:
        业务异常（ValidationException 等）由 save_uploaded_file 抛出，API 层转 4xx。
    """
    rel_path, _safe_name = save_uploaded_file(
        uploaded_file=uploaded_file,
        rel_dir=MediaEntity.AGENT_ATTACHMENTS,
        allowed_extensions=ALLOWED_EXTENSIONS,
        max_size_bytes=MAX_SIZE_BYTES,
    )
    filename = str(getattr(uploaded_file, "name", "") or Path(rel_path).name)
    mime = mimetypes.guess_type(filename)[0] or ""
    size = getattr(uploaded_file, "size", 0) or 0
    return AgentAttachment.objects.create(
        session=session,
        user_id=user_id,
        filename=filename[:255],
        storage_path=rel_path,
        mime=mime[:100],
        size=int(size),
    )


def get_attachment_for_user(*, attachment_id: str, user_id: int | None) -> AgentAttachment | None:
    """按归属取附件：会话属于当前用户（或超管经 API 层判定）才可见。"""
    attachment = AgentAttachment.objects.select_related("session").filter(attachment_id=attachment_id).first()
    if attachment is None:
        return None
    owner_id = attachment.session.user_id
    if owner_id is None or user_id is None or int(owner_id) != int(user_id):
        return None
    return attachment


def read_attachment_content(attachment: AgentAttachment) -> dict[str, Any]:
    """读取物理文件为 base64（供 mcp_server 转投解析端点；不直接给模型）。"""
    with default_storage.open(attachment.storage_path, "rb") as fh:
        payload = base64.b64encode(fh.read()).decode("ascii")
    return {
        "attachment_id": str(attachment.attachment_id),
        "filename": attachment.filename,
        "mime": attachment.mime,
        "size": attachment.size,
        "content_base64": payload,
    }
