"""发票下载服务。"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import pymupdf as fitz
from django.conf import settings

from apps.invoice_recognition.models import InvoiceCategory, InvoiceRecognitionTask, InvoiceRecord

logger = logging.getLogger(__name__)

_ILLEGAL_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


class InvoiceDownloadService:
    """发票下载服务：单张/类目/全部，支持 PDF 合并和 ZIP 压缩。"""

    def _get_task_for_user(self, task_id: int, user: Any | None) -> InvoiceRecognitionTask:
        """按 ID 取任务；user 非空且非 superuser 时校验任务归属（否则视为不存在）."""
        qs = InvoiceRecognitionTask.objects.all()
        if user is not None and not getattr(user, "is_superuser", False):
            qs = qs.filter(created_by=user)
        return qs.get(pk=task_id)

    def download_single(
        self,
        invoice_id: int,
        task_id: int | None = None,
        *,
        user: Any | None = None,
    ) -> tuple[Path, str]:
        qs = InvoiceRecord.objects.select_related("task")
        if task_id is not None:
            qs = qs.filter(task_id=task_id)
        if user is not None and not getattr(user, "is_superuser", False):
            qs = qs.filter(task__created_by=user)
        record = qs.get(pk=invoice_id)
        abs_path = Path(settings.MEDIA_ROOT) / record.file_path
        if not abs_path.exists():
            logger.warning("发票文件不存在: %s", abs_path)
            raise FileNotFoundError(f"文件不存在: {abs_path}")
        return abs_path, record.original_filename

    def download_by_category(
        self, task_id: int, category: str, fmt: str = "zip", *, user: Any | None = None
    ) -> tuple[bytes, str]:
        task = self._get_task_for_user(task_id, user)
        records = list(
            InvoiceRecord.objects.filter(
                task_id=task_id,
                category=category,
                is_duplicate=False,
            )
        )
        task_name: str = task.name

        try:
            category_label: str = str(InvoiceCategory(category).label)
        except ValueError:
            category_label = category

        data = self._merge_to_pdf(records) if fmt == "pdf" else self._pack_to_zip(records)
        filename = self._generate_filename(task_name, category_label, fmt)
        return data, filename

    def download_all(self, task_id: int, fmt: str = "zip", *, user: Any | None = None) -> tuple[bytes, str]:
        task = self._get_task_for_user(task_id, user)
        records = list(
            InvoiceRecord.objects.filter(
                task_id=task_id,
                is_duplicate=False,
            )
        )
        task_name: str = task.name

        data = self._merge_to_pdf(records) if fmt == "pdf" else self._pack_to_zip(records)
        filename = self._generate_filename(task_name, None, fmt)
        return data, filename

    def _merge_to_pdf(self, records: list[InvoiceRecord]) -> bytes:  # pragma: no cover
        dest: fitz.Document = fitz.open()
        for record in records:
            abs_path = Path(settings.MEDIA_ROOT) / record.file_path
            if not abs_path.exists():
                logger.warning("合并 PDF 时文件不存在，跳过: %s", abs_path)
                continue
            try:
                suffix = abs_path.suffix.lower()
                if suffix in {".jpg", ".jpeg", ".png"}:
                    img_doc: fitz.Document = fitz.open(str(abs_path))
                    dest.insert_pdf(img_doc)
                    img_doc.close()
                else:
                    pdf_doc: fitz.Document = fitz.open(str(abs_path))
                    dest.insert_pdf(pdf_doc)
                    pdf_doc.close()
            except Exception:
                logger.warning("合并 PDF 时处理文件失败，跳过: %s", abs_path, exc_info=True)
        result: bytes = dest.tobytes()
        dest.close()
        return result

    def _pack_to_zip(self, records: list[InvoiceRecord]) -> bytes:  # pragma: no cover
        buf = io.BytesIO()
        seen_names: dict[str, int] = {}
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for record in records:
                abs_path = Path(settings.MEDIA_ROOT) / record.file_path
                if not abs_path.exists():
                    logger.warning("打包 ZIP 时文件不存在，跳过: %s", abs_path)
                    continue
                arcname = record.original_filename
                if arcname in seen_names:
                    seen_names[arcname] += 1
                    stem = Path(arcname).stem
                    suffix = Path(arcname).suffix
                    arcname = f"{stem}_{seen_names[record.original_filename]}{suffix}"
                else:
                    seen_names[arcname] = 0
                zf.write(str(abs_path), arcname=arcname)
        return buf.getvalue()

    def _generate_filename(self, task_name: str, category: str | None, fmt: str) -> str:
        category_part = category if category is not None else "全部"
        today = date.today().strftime("%Y%m%d")
        raw = f"{task_name}_{category_part}_{today}.{fmt}"
        return _ILLEGAL_CHARS_RE.sub("_", raw)
