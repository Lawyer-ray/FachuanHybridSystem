"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from django.db import transaction

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.documents.models import EvidenceItem


class EvidenceFileService:
    SUPPORTED_FORMATS: ClassVar = [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".bmp"]
    MAX_FILE_SIZE = 50 * 1024 * 1024

    @transaction.atomic
    def upload_file(self, *, item: EvidenceItem, file: Any) -> EvidenceItem:
        file_name = getattr(file, "name", "")
        file_size = getattr(file, "size", 0)

        ext = Path(file_name).suffix.lower()
        if ext not in self.SUPPORTED_FORMATS:
            raise ValidationException(
                message=_("不支持的文件格式"),
                code="UNSUPPORTED_FILE_FORMAT",
                errors={
                    "file": f"不支持 {ext} 格式",
                    "supported_formats": self.SUPPORTED_FORMATS,
                },
            )

        if file_size > self.MAX_FILE_SIZE:
            raise ValidationException(
                message=_("文件过大"),
                code="FILE_TOO_LARGE",
                errors={
                    "file": f"文件大小 {file_size / (1024 * 1024):.1f}MB 超过限制 50MB",
                    "max_size": self.MAX_FILE_SIZE,
                },
            )

        if item.file:
            with contextlib.suppress(Exception):
                item.file.delete(save=False)

        item.file = file
        item.file_name = file_name
        item.file_size = file_size
        item.page_count = self._get_page_count(ext=ext, file=file)
        item.save()
        return item

    @transaction.atomic
    def delete_file(self, *, item: EvidenceItem) -> bool:
        if item.file:
            with contextlib.suppress(Exception):
                item.file.delete(save=False)

        item.file = None
        item.file_name = ""
        item.file_size = 0
        item.page_count = 0
        item.page_start = None
        item.page_end = None
        item.save()
        return True

    def _get_page_count(self, *, ext: str, file: Any) -> int:
        if ext == ".pdf":
            from apps.documents.services.pdf_utils import get_pdf_page_count

            return get_pdf_page_count(file, default=1)
        return 1
