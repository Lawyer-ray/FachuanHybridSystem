"""PDF 合并服务 — 跨 app 共享基类

提供 PDFMergeValidator、PDFMergeWorkflowBase、PDFMergeServiceBase 三个基类。
evidence 和 documents 各自继承并实现差异部分（Model 类型、文件名生成、utils 路径）。
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable

from django.core.files.base import ContentFile

from apps.core.exceptions import BusinessException, ValidationException
from apps.core.exceptions.error_codes import FILE_CONVERSION_FAILED, PDF_MERGE_FAILED
from apps.core.services.pdf_utils import get_pdf_page_count


@runtime_checkable
class _EvidenceLike(Protocol):
    """EvidenceList 的鸭子类型协议，避免直接依赖具体 Model。"""

    @property
    def pk(self) -> Any: ...
    @property
    def items(self) -> Any: ...
    @property
    def merged_pdf(self) -> Any: ...
    @merged_pdf.setter
    def merged_pdf(self, value: Any) -> None: ...
    @property
    def total_pages(self) -> int: ...
    @total_pages.setter
    def total_pages(self, value: int) -> None: ...
    @property
    def start_page(self) -> int: ...
    @property
    def title(self) -> str: ...
    @property
    def case(self) -> Any: ...
    @property
    def export_version(self) -> Any: ...
    # 与 django-stubs 的 Model.save 签名保持一致（`**kwargs: Any` 会导致
    # 具体模型类因只接受固定关键字参数而不满足结构化协议）
    def save(
        self,
        *,
        force_insert: bool | tuple[Any, ...] = ...,
        force_update: bool = ...,
        using: str | None = ...,
        update_fields: Iterable[str] | None = ...,
    ) -> None: ...


class PDFMergeValidator:
    """合并前校验 — 公共逻辑。"""

    SUPPORTED_FORMATS: ClassVar = [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".bmp"]
    IMAGE_FORMATS: ClassVar = [".jpg", ".jpeg", ".png", ".gif", ".bmp"]
    WORD_FORMATS: ClassVar = [".doc", ".docx"]

    def get_items(self, evidence_list: _EvidenceLike) -> Any:
        items = evidence_list.items.filter(file__isnull=False).exclude(file="").order_by("order")
        if not items.exists():
            raise ValidationException(
                message="证据清单没有任何文件",
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


class PDFMergeWorkflowBase:
    """PDF 合并工作流基类。

    子类需要实现:
    - convert_to_pdf(): 文件格式转换
    - add_page_numbers(): 页码插入
    - generate_merged_filename(): 文件名生成
    """

    def __init__(self, validator: PDFMergeValidator | None = None) -> None:
        self._validator = validator

    @property
    def validator(self) -> PDFMergeValidator:
        if self._validator is None:
            self._validator = PDFMergeValidator()
        return self._validator

    def merge_evidence_files(
        self,
        evidence_list: _EvidenceLike,
        progress_callback: Callable[[int, int, str], None] | None = None,
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
            file_name = self.generate_merged_filename(evidence_list)
            self._save_merged_pdf(evidence_list, file_name, pdf_with_pages)
            self._cleanup_temp_files(temp_files)
            return str(evidence_list.merged_pdf.path)
        except (ValidationException, BusinessException):
            raise
        except Exception as e:
            raise BusinessException(
                message=f"PDF 合并失败: {e!s}", code=PDF_MERGE_FAILED, errors={"original_error": str(e)}
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
                    code=FILE_CONVERSION_FAILED,
                    errors={"item_id": item.id, "file_name": item.file_name},
                ) from e

    def _save_merged_pdf(self, evidence_list: _EvidenceLike, file_name: str, pdf_with_pages: bytes) -> None:
        if evidence_list.merged_pdf:
            with contextlib.suppress(Exception):
                evidence_list.merged_pdf.delete(save=False)
        evidence_list.merged_pdf.save(file_name, ContentFile(pdf_with_pages))
        evidence_list.total_pages = self.get_pdf_page_count(io.BytesIO(pdf_with_pages))
        evidence_list.save(update_fields=["merged_pdf", "total_pages", "updated_at"])

    def _cleanup_temp_files(self, temp_files: list[Any]) -> None:  # pragma: no cover
        for temp_file in temp_files:
            with contextlib.suppress(Exception):
                Path(temp_file).unlink(missing_ok=True)

    # ── 子类必须实现 ──

    def convert_to_pdf(self, file_path: str) -> str:  # pragma: no cover
        """将非 PDF 文件转换为 PDF。子类必须实现。"""
        raise NotImplementedError

    def add_page_numbers(self, pdf_input: io.BytesIO, start_page: int = 1) -> bytes:  # pragma: no cover
        """为 PDF 添加页码。子类必须实现。"""
        raise NotImplementedError

    def generate_merged_filename(self, evidence_list: _EvidenceLike) -> str:  # pragma: no cover
        """生成合并后的文件名。子类必须实现。"""
        raise NotImplementedError

    def get_pdf_page_count(self, pdf_input: Any) -> int:
        """读取 PDF 页数。"""
        return get_pdf_page_count(pdf_input, default=0)


class PDFMergeServiceBase:
    """PDF 合并服务门面 — 公共逻辑。"""

    def __init__(self, workflow: PDFMergeWorkflowBase | None = None) -> None:
        self._workflow = workflow

    @property
    def workflow(self) -> PDFMergeWorkflowBase:
        if self._workflow is None:
            self._workflow = self._create_workflow()
        return self._workflow

    def _create_workflow(self) -> PDFMergeWorkflowBase:
        """子类必须覆写此方法返回具体的 workflow 实例。"""
        raise NotImplementedError

    def merge_evidence_files(
        self,
        evidence_list: _EvidenceLike,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> str:
        return self.workflow.merge_evidence_files(evidence_list, progress_callback)

    def convert_to_pdf(self, file_path: str) -> str:
        return self.workflow.convert_to_pdf(file_path)

    def add_page_numbers(self, pdf_input: io.BytesIO, start_page: int = 1) -> bytes:
        return self.workflow.add_page_numbers(pdf_input, start_page)

    def get_pdf_page_count(self, pdf_input: Any) -> int:
        return self.workflow.get_pdf_page_count(pdf_input)
