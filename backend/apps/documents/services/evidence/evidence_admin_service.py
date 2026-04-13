"""Business logic services."""

from __future__ import annotations

from typing import Any, cast

from django.utils import timezone

from apps.documents.services.evidence.evidence_service import EvidenceService
from apps.documents.services.evidence.export_service import EvidenceExportService
from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService


class EvidenceAdminService:
    """
    证据清单 Admin 服务

    封装 Admin 层的证据清单操作,包括合并、导出等.
    """

    def __init__(
        self,
        evidence_service: EvidenceService | None = None,
        pdf_service: PDFMergeService | None = None,
        export_service: EvidenceExportService | None = None,
    ) -> None:
        self._evidence_service = evidence_service
        self._pdf_service = pdf_service
        self._export_service = export_service

    @property
    def evidence_service(self) -> EvidenceService:
        if self._evidence_service is None:
            from apps.documents.services.infrastructure.wiring import get_case_service

            self._evidence_service = EvidenceService(case_service=get_case_service())
        return self._evidence_service

    @property
    def pdf_service(self) -> PDFMergeService:
        if self._pdf_service is None:
            self._pdf_service = PDFMergeService()
        return self._pdf_service

    @property
    def export_service(self) -> EvidenceExportService:
        if self._export_service is None:
            self._export_service = EvidenceExportService()
        return self._export_service

    def merge_and_update(self, list_id: int) -> dict[str, Any]:
        """
        合并证据文件并更新页码

        Args:
            list_id: 证据清单 ID

        Returns:
            操作结果

        Requirements: 11.5
        """
        # 获取证据清单
        evidence_list = self.evidence_service.get_evidence_list(list_id)

        # 合并 PDF
        pdf_path = self.pdf_service.merge_evidence_files(evidence_list)

        # 重新加载证据清单
        evidence_list.refresh_from_db()

        # 计算页码范围
        self.evidence_service.calculate_page_ranges(list_id)

        # 更新后续清单的页码
        self.evidence_service.update_subsequent_lists_pages(evidence_list.case_id, evidence_list.order + 1)

        return {
            "success": True,
            "pdf_path": pdf_path,
            "total_pages": evidence_list.total_pages,
            "message": f"合并成功,共 {evidence_list.total_pages} 页",
        }

    def export_list_word(self, list_id: int) -> tuple[bytes, str]:
        """
        导出证据清单 Word 文档

        Args:
            list_id: 证据清单 ID

        Returns:
            (文档内容, 文件名)

        Requirements: 11.5
        """
        return cast(tuple[bytes, str], self.export_service.export_evidence_list(list_id))

    def export_list_word_with_template(self, list_id: int, template_id: int) -> tuple[bytes, str]:
        """
        使用模板导出证据清单 Word 文档

        Args:
            list_id: 证据清单 ID
            template_id: 模板 ID

        Returns:
            (文档内容, 文件名)

        Requirements: 6.1, 6.2
        """
        return cast(tuple[bytes, str], self.export_service.export_evidence_list_with_template(list_id, template_id))

    def export_detail_word(self, list_id: int) -> tuple[bytes, str]:
        """
        导出证据明细 Word 文档

        Args:
            list_id: 证据清单 ID

        Returns:
            (文档内容, 文件名)

        Requirements: 11.5
        """
        return cast(tuple[bytes, str], self.export_service.export_evidence_detail(list_id))

    def reorder_items(self, list_id: int, item_ids: list[int]) -> bool:
        """
        重新排序证据明细

        Args:
            list_id: 证据清单 ID
            item_ids: 新顺序的明细 ID 列表

        Returns:
            是否成功

        Requirements: 11.5
        """
        return self.evidence_service.reorder_items(list_id, item_ids)

    def get_evidence_list_with_items(self, list_id: int) -> dict[str, Any]:
        """
        获取证据清单及其明细

        Args:
            list_id: 证据清单 ID

        Returns:
            证据清单数据
        """
        evidence_list = self.evidence_service.get_evidence_list(list_id)
        items = list(evidence_list.items.order_by("order"))

        return {
            "id": evidence_list.pk,
            "title": evidence_list.title,
            "order": evidence_list.order,
            "total_pages": evidence_list.total_pages,
            "start_page": evidence_list.start_page,
            "end_page": evidence_list.end_page,
            "page_range_display": evidence_list.page_range_display,
            "export_version": evidence_list.export_version,
            "has_merged_pdf": bool(evidence_list.merged_pdf),
            "items": [
                {
                    "id": item.id,
                    "order": item.order,
                    "name": item.name,
                    "purpose": item.purpose,
                    "page_count": item.page_count,
                    "page_range_display": item.page_range_display,
                    "has_file": bool(item.file),
                    "file_name": item.file_name,
                    "file_size_display": item.file_size_display,
                }
                for item in items
            ],
        }

    def generate_pdf_filename(self, evidence_list: Any) -> str:
        """
        生成证据明细 PDF 文件名

        Args:
            evidence_list: 证据清单对象

        Returns:
            文件名,格式:证据明细{序号}({案件名称})V{版本号}_{日期}.pdf
            示例:证据明细一(XX与YY纠纷)V1_20260115.pdf
        """

        # 获取案件名称
        case_name = evidence_list.case.name

        # 获取日期
        date_str = timezone.now().strftime("%Y%m%d")

        # 从证据清单标题中提取序号部分
        # 如"证据清单一"提取"一","补充证据清单二"提取"二"
        list_suffix = ""
        title = evidence_list.title
        if title.startswith("证据清单"):
            list_suffix = title[4:]  # 提取"证据清单"后面的部分
        elif title.startswith("补充证据清单"):
            list_suffix = title[6:]  # 提取"补充证据清单"后面的部分

        # 版本号
        version = evidence_list.export_version

        # 格式:证据明细{序号}({案件名称})V{版本号}_{日期}.pdf
        filename = f"证据明细{list_suffix}({case_name})V{version}_{date_str}.pdf"

        return filename

    def _recount_item_pages(self, item: Any) -> tuple[int, int, str | None]:
        """重新计算单个证据项的页数，返回 (updated_count, page_count, error_msg)"""
        from pathlib import Path

        from .infrastructure.pdf_utils import get_pdf_page_count_with_error

        if not item.file:
            update_fields: list[str] = []
            if item.page_count != 0:
                item.page_count = 0
                update_fields.append("page_count")
            if item.page_start is not None:
                item.page_start = None
                update_fields.append("page_start")
            if item.page_end is not None:
                item.page_end = None
                update_fields.append("page_end")
            if update_fields:
                item.save(update_fields=update_fields)
                return 1, 0, None
            return 0, 0, None

        file_name = item.file.name
        ext = Path(file_name).suffix.lower()
        if ext != ".pdf":
            return 0, item.page_count or 1, None

        page_count, error = get_pdf_page_count_with_error(item.file, default=1)
        error_msg = f"文件 {item.file_name or file_name} 识别失败:{error}" if error else None
        updated = 0
        if page_count != item.page_count:
            item.page_count = page_count
            item.save(update_fields=["page_count"])
            updated = 1
        return updated, page_count, error_msg

    def recount_pages(self, list_id: int) -> dict[str, Any]:
        """重新识别证据清单中所有 PDF 文件的页数"""
        from apps.documents.models import EvidenceList

        evidence_list = EvidenceList.objects.prefetch_related("items").get(pk=list_id)
        items = evidence_list.items.all()

        updated = 0
        errors: list[Any] = []
        total_pages = 0

        for item in items:
            item_updated, item_pages, item_error = self._recount_item_pages(item)
            updated += item_updated
            total_pages += item_pages
            if item_error:
                errors.append(item_error)

        if evidence_list.total_pages != total_pages:
            evidence_list.total_pages = total_pages
            evidence_list.save(update_fields=["total_pages"])

        return {"updated": updated, "total_pages": total_pages, "errors": errors}
