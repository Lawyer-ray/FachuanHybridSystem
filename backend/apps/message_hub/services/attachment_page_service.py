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

from django.db import transaction

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
    with transaction.atomic():
        # 行锁重取消息行：attachments_meta 是 JSONField 读-改-写，与并发追加/
        # 重命名会互相覆盖，锁行串行化后再基于最新 meta 回填（对照 manual_upload_service 的锁模式）。
        locked = InboxMessage.objects.select_for_update().get(pk=message.pk)
        metas = list(locked.attachments_meta or [])
        if not fill_page_counts(metas):
            return
        locked.attachments_meta = metas
        locked.save(update_fields=["attachments_meta"])
        # 同步回传入对象，调用方无需 refresh 即可读到页数
        message.attachments_meta = metas
        logger.info("材料包 %s 回填 PDF 页数完成", locked.pk)


def rename_attachment_in_meta(message: InboxMessage, *, part_index: int, custom_filename: str) -> tuple[str, str]:
    """在行锁内重命名附件的自定义文件名（留空恢复原始名）。

    attachments_meta 是 JSONField 读-改-写，并发重命名/追加/页数回填会互相
    覆盖，锁行串行化后再基于最新 meta 修改（对照 manual_upload_service 的
    锁模式）。返回 (original_filename, custom_filename)。

    Raises:
        NotFoundError: part_index 对应的附件不存在。
    """
    from django.db import transaction

    from apps.core.exceptions import NotFoundError

    with transaction.atomic():
        locked = InboxMessage.objects.select_for_update().get(pk=message.pk)
        meta = list(locked.attachments_meta or [])
        target = None
        for att in meta:
            if int(att.get("part_index", -1)) == part_index:
                target = att
                break
        if target is None:
            raise NotFoundError(f"附件 part_index={part_index} 不存在")

        original = target.get("original_filename") or target.get("filename") or ""
        custom = custom_filename.strip()

        if custom and custom != original:
            target["custom_filename"] = custom
        else:
            target.pop("custom_filename", None)
            custom = ""

        locked.attachments_meta = meta
        locked.save(update_fields=["attachments_meta"])

    return original, custom
