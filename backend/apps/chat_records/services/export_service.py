"""导出服务门面 —— 根据导出类型委托给 PdfExportService 或 DocxExportService。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.core.files.base import ContentFile

    from .docx_export_service import DocxExportService
    from .pdf_export_service import PdfExportService

from apps.chat_records.models import ChatRecordProject, ChatRecordScreenshot
from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportLayout:
    images_per_page: int
    show_page_number: bool
    header_text: str

    @classmethod
    def from_payload(cls, export_type: str, payload: dict[str, Any]) -> ExportLayout:
        data = payload or {}
        images_per_page = int(data.get("images_per_page") or 2)
        show_page_number = bool(data.get("show_page_number", True))
        header_text = str(data.get("header_text") or "").strip()

        if images_per_page not in (1, 2):
            raise ValidationException("仅支持 1 张/页 或 2 张/页")

        return cls(
            images_per_page=images_per_page,
            show_page_number=show_page_number,
            header_text=header_text,
        )


class ExportService:
    """门面类：根据导出类型委托给对应的子服务。"""

    def __init__(
        self,
        *,
        pdf_service: PdfExportService | None = None,
        docx_service: DocxExportService | None = None,
    ) -> None:
        self._pdf_service = pdf_service or PdfExportService()
        self._docx_service = docx_service or DocxExportService()

    def export_pdf(
        self,
        *,
        project: ChatRecordProject,
        screenshots: list[ChatRecordScreenshot],
        layout: ExportLayout,
        filename: str,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> ContentFile[bytes]:
        return self._pdf_service.export_pdf(
            project=project,
            screenshots=screenshots,
            layout=layout,
            filename=filename,
            progress_callback=progress_callback,
        )

    def export_docx(
        self,
        *,
        project: ChatRecordProject,
        screenshots: list[ChatRecordScreenshot],
        layout: ExportLayout,
        filename: str,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> ContentFile[bytes]:
        return self._docx_service.export_docx(
            project=project,
            screenshots=screenshots,
            layout=layout,
            filename=filename,
            progress_callback=progress_callback,
        )


# 延迟导入避免循环引用 —— 放在模块末尾
from .docx_export_service import DocxExportService  # noqa: E402
from .pdf_export_service import PdfExportService  # noqa: E402

__all__ = [
    "DocxExportService",
    "ExportLayout",
    "ExportService",
    "PdfExportService",
]
