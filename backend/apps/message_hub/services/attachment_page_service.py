"""附件页数维护：上传时落库 + 详情读取时回填。

前端材料预处理打开材料包需要每个 PDF 的真实页数来构建初始分段。此前前端
必须下载整个 PDF 再用 pdf.js 数页数（26MB 扫描件 ≈ 1.2s 起步，多附件串行
线性叠加）。改为后端在 attachments_meta（JSONField）里维护 page_count，
前端直接取用、零下载；老数据由详情接口读取时回填，无需数据库迁移。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from apps.message_hub.models import InboxMessage
from apps.message_hub.services.base import resolve_media_attachment_path

logger = logging.getLogger("apps.message_hub")


def is_pdf_attachment(att: dict[str, Any]) -> bool:
    ct = str(att.get("content_type") or "").lower()
    name = str(att.get("filename") or att.get("original_filename") or "").lower()
    return "pdf" in ct or name.endswith(".pdf")


def count_pdf_pages(path: Path) -> int | None:
    """用 PyMuPDF 数 PDF 页数；打不开 / 加密 / 非法文件返回 None（调用方保持缺省）。"""
    try:
        import pymupdf as fitz

        with fitz.open(path) as doc:
            return int(doc.page_count)
    except Exception as e:
        logger.warning("计算 PDF 页数失败 path=%s: %s", path, e)
        return None


def has_page_count(att: dict[str, Any]) -> bool:
    try:
        return int(att.get("page_count") or 0) > 0
    except (TypeError, ValueError):
        return False


def fill_page_counts(metas: list[dict[str, Any]]) -> bool:
    """就地给 metas 里缺页数的 PDF 附件补上 page_count，返回是否有改动。

    只处理能解析到本地文件且能数出页数的附件；其余（非 PDF、文件缺失、
    解析失败）保持原样，前端自行兜底（photo/office 页数恒为 1）。
    """
    changed = False
    for att in metas:
        if not isinstance(att, dict) or not is_pdf_attachment(att) or has_page_count(att):
            continue
        resolved = resolve_media_attachment_path(str(att.get("local_path", "")) or "")
        if resolved is None or not resolved.is_file():
            continue
        pages = count_pdf_pages(resolved)
        if pages:
            att["page_count"] = pages
            changed = True
    return changed


def ensure_page_counts(message: InboxMessage) -> None:
    """详情读取时回填：给老消息缺页数的 PDF 附件补算并落库（一次写，后续命中缓存直读）。"""
    metas = list(message.attachments_meta or [])
    if not fill_page_counts(metas):
        return
    message.attachments_meta = metas
    message.save(update_fields=["attachments_meta"])
    logger.info("材料包 %s 回填 PDF 页数完成", message.pk)
