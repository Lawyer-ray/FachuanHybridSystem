"""Business logic services."""

from __future__ import annotations

import contextlib
import io
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any, ClassVar, cast

from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import BusinessException, ValidationException
from apps.evidence.models import EvidenceList


def _get_pdf_merge_utils_module() -> Any:
    return import_module("apps.documents.services.infrastructure.pdf_merge_utils")


class PDFMergeValidator:
    SUPPORTED_FORMATS: ClassVar = [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".bmp"]
    IMAGE_FORMATS: ClassVar = [".jpg", ".jpeg", ".png", ".gif", ".bmp"]
    WORD_FORMATS: ClassVar = [".doc", ".docx"]

    def get_items(self, evidence_list: EvidenceList) -> Any:
        items = evidence_list.items.filter(file__isnull=False).exclude(file="").order_by("order")
        if not items.exists():
            raise ValidationException(
                message=_("证据清单没有任何文件"),
                code="NO_FILES_TO_MERGE",
                errors={"evidence_list_id": int(evidence_list.pk)},
            )
        return items

    def assert_supported_format(self, ext: str, file_path: str) -> None:
        if ext not in self.SUPPORTED_FORMATS:
            raise BusinessException(
                message=f"不支持的文件格式: {ext}",
                code="UNSUPPORTED_FILE_FORMAT",
                errors={"file_path": file_path, "extension": ext},
            )


class PDFMergeWorkflow:
    def __init__(self, validator: PDFMergeValidator | None = None) -> None:
        self._validator = validator

    @property
    def validator(self) -> PDFMergeValidator:
        if self._validator is None:
            self._validator = PDFMergeValidator()
        return self._validator

    def merge_evidence_files(
        self, evidence_list: EvidenceList, progress_callback: Callable[[int, int, str], None] | None = None
    ) -> str:
        items = self.validator.get_items(evidence_list)
        try:
            import pikepdf

            merged_pdf = pikepdf.Pdf.new()
            temp_files: list[Any] = []
            total_files = items.count()
            if progress_callback:
                progress_callback(0, total_files, "开始合并")
            self._merge_all_items(merged_pdf, items, temp_files, total_files, progress_callback)
            output_buffer = io.BytesIO()
            merged_pdf.save(output_buffer)
            output_buffer.seek(0)
            if progress_callback:
                progress_callback(total_files, total_files, "正在添加页码")
            pdf_with_pages = self.add_page_numbers(output_buffer, evidence_list.start_page)
            file_name = self._generate_merged_filename(evidence_list)
            self._save_merged_pdf(evidence_list, file_name, pdf_with_pages)
            self._cleanup_temp_files(temp_files)
            return evidence_list.merged_pdf.path
        except (ValidationException, BusinessException):
            raise
        except Exception as e:
            raise BusinessException(
                message=f"PDF 合并失败: {e!s}", code="PDF_MERGE_FAILED", errors={"original_error": str(e)}
            ) from e

    def _merge_all_items(
        self, merged_pdf: Any, items: Any, temp_files: Any, total_files: Any, progress_callback: Any
    ) -> None:
        import pikepdf

        for index, item in enumerate(items, start=1):
            try:
                file_path = item.file.path
                ext = Path(file_path).suffix.lower()
                pdf_path = file_path if ext == ".pdf" else self.convert_to_pdf(file_path)
                if pdf_path != file_path:
                    temp_files.append(pdf_path)
                with pikepdf.open(pdf_path) as pdf:
                    merged_pdf.pages.extend(pdf.pages)
                if progress_callback:
                    file_label = item.file_name or Path(file_path).name
                    progress_callback(index, total_files, f"已处理:{file_label}")
            except Exception as e:
                raise BusinessException(
                    message=f"处理文件 {item.file_name} 失败: {e!s}",
                    code="FILE_CONVERSION_FAILED",
                    errors={"item_id": item.id, "file_name": item.file_name},
                ) from e

    def _save_merged_pdf(self, evidence_list: Any, file_name: Any, pdf_with_pages: Any) -> None:
        if evidence_list.merged_pdf:
            with contextlib.suppress(Exception):
                evidence_list.merged_pdf.delete(save=False)
        evidence_list.merged_pdf.save(file_name, ContentFile(pdf_with_pages))
        evidence_list.total_pages = self.get_pdf_page_count(io.BytesIO(pdf_with_pages))
        evidence_list.save(update_fields=["merged_pdf", "total_pages", "updated_at"])

    def _cleanup_temp_files(self, temp_files: list[Any]) -> None:
        for temp_file in temp_files:
            with contextlib.suppress(Exception):
                Path(temp_file).unlink(missing_ok=True)

    def convert_to_pdf(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        self.validator.assert_supported_format(ext, file_path)
        utils = _get_pdf_merge_utils_module()
        if ext in self.validator.IMAGE_FORMATS:
            return utils.convert_image_to_pdf(file_path)  # type: ignore[no-any-return]
        if ext in self.validator.WORD_FORMATS:
            return utils.convert_docx_to_pdf(file_path)  # type: ignore[no-any-return]
        return file_path

    def add_page_numbers(self, pdf_input: io.BytesIO, start_page: int = 1) -> bytes:
        utils = _get_pdf_merge_utils_module()
        return utils.add_page_numbers(pdf_input, start_page)  # type: ignore[no-any-return]

    def _generate_merged_filename(self, evidence_list: EvidenceList) -> str:

        case_name = evidence_list.case.name
        date_str = timezone.now().strftime("%Y%m%d")
        list_suffix = ""
        title = evidence_list.title
        if title.startswith("证据清单"):
            list_suffix = title[4:]
        elif title.startswith("补充证据清单"):
            list_suffix = title[6:]
        version = evidence_list.export_version
        filename = f"证据明细{list_suffix}({case_name})V{version}_{date_str}.pdf"
        return filename

    def get_pdf_page_count(self, pdf_input: Any) -> int:
        from apps.evidence.services.infrastructure.pdf_utils import get_pdf_page_count

        return get_pdf_page_count(pdf_input, default=0)


class PDFMergeService:
    def __init__(self, workflow: PDFMergeWorkflow | None = None) -> None:
        self._workflow = workflow

    @property
    def workflow(self) -> PDFMergeWorkflow:
        if self._workflow is None:
            self._workflow = PDFMergeWorkflow()
        return self._workflow

    def merge_evidence_files(
        self, evidence_list: EvidenceList, progress_callback: Callable[[int, int, str], None] | None = None
    ) -> str:
        return self.workflow.merge_evidence_files(evidence_list, progress_callback)

    def convert_to_pdf(self, file_path: str) -> str:
        return self.workflow.convert_to_pdf(file_path)

    def add_page_numbers(self, pdf_input: io.BytesIO, start_page: int = 1) -> bytes:
        return self.workflow.add_page_numbers(pdf_input, start_page)

    def get_pdf_page_count(self, pdf_input: Any) -> int:
        return self.workflow.get_pdf_page_count(pdf_input)
