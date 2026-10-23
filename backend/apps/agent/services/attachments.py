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
import logging
import mimetypes
import time
from pathlib import Path
from typing import Any

from django.core.files.storage import default_storage

from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.services.storage_service import save_uploaded_file

from ..models import AgentAttachment, AgentSession

logger = logging.getLogger(__name__)

#: 与解析端点支持面对齐（mcp_server/tools/documents/parsing.CONTENT_TYPES）
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
    """按归属取附件：只有会话属于当前用户才可见（超管/服务账号同样 fail-closed）。"""
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


#: 走页图渲染的 mime 前缀（其余交给文本解析链路）
_IMAGE_MIME_PREFIX = "image/"
_PDF_MIMES = {"application/pdf", "application/x-pdf"}


def render_attachment_pages(
    attachment: AgentAttachment,
    *,
    pages: str | int | list[int] | None = None,
    dpi: int = 200,
    format: str = "png",
    max_pages: int = 20,
    user_id: int | None = None,
) -> Any:
    """把附件的指定页渲染成图片，供模型走视觉通道（扫描件/图片附件必需）。

    权限**不在这里重做**：调用方必须先经 :func:`get_attachment_for_user` 拿到
    ``attachment``（越权即拿不到，返回 404 而非 403，不区分「不存在」与
    「不是你的」）。这里只负责「读物理文件 → 按 mime 分流 → 渲染」。

    Args:
        attachment: 已通过归属校验的附件记录。
        pages: 页范围（``"1-3"`` / ``[1,5]`` / ``"all"`` / ``"7"`` / ``None``=前若干页）。
            图片附件恒为 1 页，给了别的页码按 ``page_out_of_range`` 处理。
        dpi: 首选渲染分辨率（PDF 扫描页；超体积会自动降档）。
        format: ``"png"`` / ``"jpeg"``。
        max_pages: 本次最多渲染页数（超出截断并标注 ``truncated_pages``）。
        user_id: 发起人（仅用于审计日志的 ``who`` 字段）。

    Returns:
        :class:`apps.agent.services.attachment_render.RenderResult`。打开失败/加密/
        mime 不支持时 ``error`` 非空且 ``pages`` 为空——**不会**用空内容冒充成功。
    """
    mime = (attachment.mime or "").lower().strip()
    fmt = "jpeg" if str(format).lower().strip() in ("jpg", "jpeg") else "png"
    try:
        with default_storage.open(attachment.storage_path, "rb") as fh:
            file_bytes = fh.read()
    except OSError as exc:
        started = time.monotonic()
        logger.warning("附件物理文件读取失败 attachment_id=%s: %s", attachment.attachment_id, exc)
        from . import attachment_render as render

        result = render.RenderResult(
            attachment_id=str(attachment.attachment_id),
            filename=attachment.filename,
            mime=mime,
            error=render.RenderError.NOT_FOUND,
            detail="附件文件已不存在",
        )
        render.log_render(who=user_id, result=result, elapsed_ms=_elapsed_ms(started))
        return result
    return _render_bytes_pages(
        ref_id=str(attachment.attachment_id),
        filename=attachment.filename,
        mime=mime,
        file_bytes=file_bytes,
        pages=pages,
        dpi=dpi,
        fmt=fmt,
        max_pages=max_pages,
        user_id=user_id,
    )


def _render_bytes_pages(
    *,
    ref_id: str,
    filename: str,
    mime: str,
    file_bytes: bytes,
    pages: str | int | list[int] | None = None,
    dpi: int = 200,
    fmt: str = "png",
    max_pages: int = 20,
    user_id: int | None = None,
    cache_ref: str | None = None,
) -> Any:
    """从字节渲染页图的共用编排层——附件与绑定文件夹引用（folder_refs）共用。

    ``ref_id`` 是展示与审计标识：附件传 attachment uuid；文件夹引用传
    ``folder:{contract_id}/{subpath}``。``cache_ref`` 为页图缓存键材料
    （默认同 ref_id）：文件夹引用必须传「含 size/mtime 指纹」的键，
    源文件更新后指纹变化、缓存自然失效（attachment_render 的键即
    ``(ref, page, dpi, fmt)`` 摘要）。
    """
    from . import attachment_render as render

    started = time.monotonic()
    mime = (mime or "").lower().strip()
    base: dict[str, Any] = {
        "attachment_id": ref_id,
        "filename": filename,
        "mime": mime,
    }

    if not (mime in _PDF_MIMES or filename.lower().endswith(".pdf") or mime.startswith(_IMAGE_MIME_PREFIX)):
        result = render.RenderResult(
            **base,
            error=render.RenderError.UNSUPPORTED_MIME,
            detail=f"mime={mime or '未知'} 没有页图形态，请用文本读取工具（read_agent_attachment）",
        )
        render.log_render(who=user_id, result=result, elapsed_ms=_elapsed_ms(started))
        return result

    if not file_bytes:
        result = render.RenderResult(**base, error=render.RenderError.PARSE_EMPTY, detail="附件内容为空")
        render.log_render(who=user_id, result=result, elapsed_ms=_elapsed_ms(started))
        return result

    if mime.startswith(_IMAGE_MIME_PREFIX):
        return _render_image_attachment(
            base, file_bytes, mime=mime, pages=pages, fmt=fmt, user_id=user_id, started=started
        )
    return _render_pdf_attachment(
        base,
        file_bytes,
        attachment_id=cache_ref or ref_id,
        pages=pages,
        dpi=dpi,
        fmt=fmt,
        max_pages=max_pages,
        user_id=user_id,
        started=started,
    )


def _render_image_attachment(
    base: dict[str, Any],
    file_bytes: bytes,
    *,
    mime: str,
    pages: str | int | list[int] | None,
    fmt: str,
    user_id: int | None,
    started: float,
) -> Any:
    """图片附件只有 1 页：页码越界要让调用方知道，而不是悄悄当成第 1 页。"""
    from . import attachment_render as render

    total_pages = 1
    try:
        wanted, _truncated = render.parse_pages(pages, total_pages, max_pages=1)
    except ValueError as exc:
        result = render.RenderResult(
            **base,
            total_pages=total_pages,
            error=render.RenderError.PAGE_OUT_OF_RANGE,
            detail=f"图片附件只有 1 页：{exc}",
        )
        render.log_render(who=user_id, result=result, elapsed_ms=_elapsed_ms(started))
        return result
    page = render.render_image(file_bytes, mime, page_no=wanted[0], fmt=fmt)
    result = render.RenderResult(**base, total_pages=total_pages, requested_pages=wanted, pages=[page])
    render.log_render(who=user_id, result=result, elapsed_ms=_elapsed_ms(started))
    return result


def _render_pdf_attachment(
    base: dict[str, Any],
    file_bytes: bytes,
    *,
    attachment_id: str,
    pages: str | int | list[int] | None,
    dpi: int,
    fmt: str,
    max_pages: int,
    user_id: int | None,
    started: float,
) -> Any:
    """PDF：先数页（页范围校验要用），再逐页渲染（含文字层判断）。"""
    from . import attachment_render as render

    total_pages = _count_pdf_pages(file_bytes)
    if total_pages <= 0:
        result = render.RenderResult(
            **base,
            error=render.RenderError.UNSUPPORTED_MIME,
            detail="PDF 无法打开（可能已损坏），请重新上传",
        )
        render.log_render(who=user_id, result=result, elapsed_ms=_elapsed_ms(started))
        return result

    try:
        wanted, truncated = render.parse_pages(pages, total_pages, max_pages=max_pages)
    except ValueError as exc:
        result = render.RenderResult(
            **base,
            total_pages=total_pages,
            error=render.RenderError.PAGE_OUT_OF_RANGE,
            detail=str(exc),
        )
        render.log_render(who=user_id, result=result, elapsed_ms=_elapsed_ms(started))
        return result

    rendered = render.render_pdf_pages(file_bytes, wanted, attachment_id=attachment_id, dpi=dpi, fmt=fmt)
    result = render.RenderResult(
        **base,
        total_pages=total_pages,
        requested_pages=wanted,
        pages=rendered,
        truncated_pages=truncated,
    )
    # 全部页都失败时把首因提到顶层，调用方不必遍历 pages 才知道发生了什么
    if rendered and all(page.error for page in rendered):
        result.error = rendered[0].error
        result.detail = rendered[0].detail
    render.log_render(who=user_id, result=result, elapsed_ms=_elapsed_ms(started))
    return result


def _count_pdf_pages(file_bytes: bytes) -> int:
    import pymupdf as fitz

    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            return int(doc.page_count)
    except Exception as exc:
        logger.warning("PDF 页数识别失败: %s", exc)
        return 0


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
