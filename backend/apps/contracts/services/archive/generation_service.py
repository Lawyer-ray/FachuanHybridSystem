"""归档文书批量生成服务

负责根据归档分类批量生成5种模板文书：
- 案卷封面 (case_cover)
- 结案归档登记表 (closing_archive_register)
- 卷内目录 (inner_catalog)
- 律师工作日志 (lawyer_work_log)
- 办案小结 (case_summary)

生成的文书自动保存为 FinalizedMaterial 记录。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial, MaterialCategory

from .category_mapping import get_archive_category
from .constants import ARCHIVE_CHECKLIST, ChecklistItem

logger = logging.getLogger("apps.contracts.archive")


# 归档模板子类型 → 文件名映射
_ARCHIVE_TEMPLATE_FILES: dict[str, str] = {
    "case_cover": "1-案卷封面.docx",
    "closing_archive_register": "2-结案归档登记表.docx",
    "inner_catalog": "3-卷内目录.docx",
    "lawyer_work_log": "5-律师工作日志.docx",
    "case_summary": "7-办案小结.docx",
}



class ArchiveGenerationService:
    """归档文书批量生成服务"""

    def preview_archive_template(self, contract_id: int, template_subtype: str) -> dict[str, Any]:
        """预览归档文书占位符替换词

        Args:
            contract_id: 合同 ID
            template_subtype: 归档模板子类型

        Returns:
            包含 success/data/error 的字典
        """
        contract = Contract.objects.filter(pk=contract_id).first()
        if not contract:
            return {"success": False, "error": "合同不存在"}

        template_path = self.get_template_path(template_subtype)
        if not template_path:
            return {"success": False, "error": f"模板文件不存在: {template_subtype}"}

        from apps.documents.services.generation.pipeline import DocxPreviewService, PipelineContextBuilder

        context_builder = PipelineContextBuilder()
        context = context_builder.build_archive_context(contract)

        rows = DocxPreviewService().preview(str(template_path), context)
        return {"success": True, "data": rows}

    def get_template_path(self, template_subtype: str) -> Path | None:
        """
        获取归档模板文件的完整路径。

        Args:
            template_subtype: DocumentArchiveSubType 值，如 "case_cover"

        Returns:
            模板文件路径，不存在返回 None
        """
        filename = _ARCHIVE_TEMPLATE_FILES.get(template_subtype)
        if not filename:
            return None

        # 从 settings 获取模板基础路径，或使用默认路径
        base_dir = getattr(settings, "DOCX_TEMPLATE_DIR", None)
        if base_dir:
            template_path = Path(base_dir) / "3-归档模板" / filename
        else:
            template_path = Path(__file__).parent.parent.parent.parent / "documents" / "docx_templates" / "3-归档模板" / filename

        if template_path.exists():
            return template_path

        logger.warning("归档模板文件不存在: %s", template_path)
        return None

    def generate_archive_documents(
        self,
        contract: Contract,
        case: Any | None = None,
    ) -> list[dict[str, Any]]:
        """
        批量生成归档文书。

        Args:
            contract: 合同实例
            case: 案件实例（可选，用于填充案件相关占位符）

        Returns:
            生成结果列表，每项包含：
            - template_subtype: 模板子类型
            - filename: 文件名
            - content: 文件内容 (bytes)
            - material_id: 保存后的 FinalizedMaterial ID
            - error: 错误信息 (如有)
        """
        archive_category = get_archive_category(contract.case_type)
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

        # 筛选需要模板生成的项
        template_items = [item for item in checklist_items if item["template"] is not None]

        results: list[dict[str, Any]] = []

        for item in template_items:
            result = self._generate_single_document(contract, item, case)
            results.append(result)

        return results

    def _generate_single_document(
        self,
        contract: Contract,
        item: ChecklistItem,
        case: Any | None = None,
    ) -> dict[str, Any]:
        """
        生成单个归档文书。

        Args:
            contract: 合同实例
            item: 检查清单项
            case: 案件实例（可选）

        Returns:
            生成结果字典
        """
        template_subtype = item["template"]
        if not template_subtype:
            return {"template_subtype": None, "error": "非模板生成项"}

        template_path = self.get_template_path(template_subtype)
        if not template_path:
            return {"template_subtype": template_subtype, "error": f"模板文件不存在: {template_subtype}"}

        try:
            from apps.documents.services.generation.pipeline import DocxRenderer, PipelineContextBuilder

            # 构建上下文
            context_builder = PipelineContextBuilder()
            context = context_builder.build_archive_context(contract, case)

            # 渲染模板
            content = DocxRenderer().render(str(template_path), context)

            # 生成文件名
            filename = self._generate_filename(contract, item)

            # 保存为 FinalizedMaterial
            material = self._save_as_material(
                contract=contract,
                content=content,
                filename=filename,
                archive_item_code=item["code"],
            )

            logger.info(
                "归档文书生成成功: %s",
                filename,
                extra={
                    "contract_id": contract.id,
                    "template_subtype": template_subtype,
                    "material_id": material.id if material else None,
                },
            )

            return {
                "template_subtype": template_subtype,
                "filename": filename,
                "content": content,
                "material_id": material.id if material else None,
                "error": None,
            }

        except Exception as e:
            logger.exception("归档文书生成失败: %s", template_subtype)
            return {"template_subtype": template_subtype, "error": str(e)}

    def _generate_filename(self, contract: Contract, item: ChecklistItem) -> str:
        """生成归档文书文件名"""
        from datetime import date

        contract_name = contract.name or "未命名合同"
        item_name = item["name"]
        today_str = date.today().strftime("%Y%m%d")

        return f"{item_name}（{contract_name}）_{today_str}.docx"

    def _save_as_material(
        self,
        contract: Contract,
        content: bytes,
        filename: str,
        archive_item_code: str,
    ) -> FinalizedMaterial | None:
        """
        将生成的文书保存为 FinalizedMaterial 记录。

        Args:
            contract: 合同实例
            content: 文件内容
            filename: 文件名
            archive_item_code: 归档清单编号

        Returns:
            保存后的 FinalizedMaterial 实例
        """
        from django.core.files.base import ContentFile

        try:
            # 检查是否已有同编号的材料，避免重复生成
            existing = FinalizedMaterial.objects.filter(
                contract=contract,
                archive_item_code=archive_item_code,
            ).first()

            if existing:
                # 更新已有材料的文件
                from apps.core.services import storage_service as storage

                rel_path, _ = storage.save_uploaded_file(
                    uploaded_file=ContentFile(content, name=filename),
                    rel_dir=f"contracts/finalized/{contract.id}",
                    allowed_extensions=[".docx", ".pdf"],
                    max_size_bytes=20 * 1024 * 1024,
                )
                existing.file_path = rel_path
                existing.original_filename = filename
                existing.save(update_fields=["file_path", "original_filename"])
                return existing
            else:
                # 创建新材料
                from apps.core.services import storage_service as storage

                rel_path, _ = storage.save_uploaded_file(
                    uploaded_file=ContentFile(content, name=filename),
                    rel_dir=f"contracts/finalized/{contract.id}",
                    allowed_extensions=[".docx", ".pdf"],
                    max_size_bytes=20 * 1024 * 1024,
                )

                material = FinalizedMaterial.objects.create(
                    contract=contract,
                    file_path=rel_path,
                    original_filename=filename,
                    category=MaterialCategory.ARCHIVE_DOCUMENT,
                    archive_item_code=archive_item_code,
                )
                return material

        except Exception as e:
            logger.exception("保存归档文书材料失败: %s", filename)
            return None
