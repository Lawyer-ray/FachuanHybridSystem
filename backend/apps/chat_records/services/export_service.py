"""导出服务门面 —— 根据导出类型委托给 PdfExportService 或 DocxExportService。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.core.files.base import ContentFile

from apps.chat_records.models import ChatRecordProject, ChatRecordScreenshot

from .docx_export_service import DocxExportService
from .export_types import ExportLayout
from .pdf_export_service import PdfExportService

logger = logging.getLogger(__name__)


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


__all__ = [
    "ExportLayout",
    "ExportService",
]
