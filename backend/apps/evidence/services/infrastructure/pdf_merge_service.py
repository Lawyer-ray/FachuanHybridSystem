"""PDF 合并服务 — evidence 模块。

继承 core 基类，仅实现 evidence 特有的逻辑。
"""

from __future__ import annotations

import contextlib
import io
from importlib import import_module
from typing import Any

from django.utils import timezone

from apps.core.services.filename_template_service import FilenameTemplateService
from apps.core.services.pdf_merge_service import (
    PDFMergeServiceBase,
    PDFMergeValidator,
    PDFMergeWorkflowBase,
)
from apps.evidence.models import EvidenceList

# 向后兼容：测试 mock 需要
from pathlib import Path  # noqa: F401


def _get_pdf_merge_utils_module() -> Any:
    return import_module("apps.documents.services.infrastructure.pdf_merge_utils")


class EvidencePDFMergeWorkflow(PDFMergeWorkflowBase):
    """evidence 模块的 PDF 合并工作流。"""

    def _generate_merged_filename(self, evidence_list: Any) -> str:
        """向后兼容：原方法名带下划线前缀。"""
        return self.generate_merged_filename(evidence_list)

    def get_pdf_page_count(self, pdf_input: Any) -> int:
        """代理到 evidence.pdf_utils，保持测试可 mock。"""
        from apps.evidence.services.infrastructure.pdf_utils import get_pdf_page_count

        return get_pdf_page_count(pdf_input, default=0)

    def _cleanup_temp_files(self, temp_files: list[Any]) -> None:  # pragma: no cover
        """覆写以保持测试可 mock Path。"""
        for temp_file in temp_files:
            with contextlib.suppress(Exception):
                Path(temp_file).unlink(missing_ok=True)

    def convert_to_pdf(self, file_path: str) -> str:  # pragma: no cover
        ext = self._get_ext(file_path)
        self.validator.assert_supported_format(ext, file_path)
        utils = _get_pdf_merge_utils_module()
        if ext in PDFMergeValidator.IMAGE_FORMATS:
            return utils.convert_image_to_pdf(file_path)
        if ext in PDFMergeValidator.WORD_FORMATS:
            return utils.convert_docx_to_pdf(file_path)
        return file_path

    def add_page_numbers(self, pdf_input: io.BytesIO, start_page: int = 1) -> bytes:
        utils = _get_pdf_merge_utils_module()
        return utils.add_page_numbers(pdf_input, start_page)

    def generate_merged_filename(self, evidence_list: EvidenceList) -> str:
        case_name = evidence_list.case.name
        date_str = timezone.now().strftime("%Y%m%d")
        list_suffix = ""
        title = evidence_list.title
        if title.startswith("证据清单"):
            list_suffix = title[4:]
        elif title.startswith("补充证据清单"):
            list_suffix = title[6:]
        version = evidence_list.export_version
        return (
            FilenameTemplateService.render_generated_doc(
                doc_type=f"证据明细{list_suffix}", case_name=case_name, version=str(version), date=date_str
            )
            + ".pdf"
        )

    @staticmethod
    def _get_ext(file_path: str) -> str:
        from pathlib import Path

        return Path(file_path).suffix.lower()


class PDFMergeService(PDFMergeServiceBase):
    """evidence 模块的 PDF 合并服务门面。"""

    def _create_workflow(self) -> EvidencePDFMergeWorkflow:
        return EvidencePDFMergeWorkflow()


# 向后兼容：原类名
PDFMergeWorkflow = EvidencePDFMergeWorkflow
