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
from io import BytesIO
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

        如果存在用户覆盖值，合并到自动生成的 context 中。

        Args:
            contract_id: 合同 ID
            template_subtype: 归档模板子类型

        Returns:
            包含 success/data/error 的字典
        """
        contract = Contract.objects.filter(pk=contract_id).first()
        if not contract:
            return {"success": False, "error": "合同不存在"}

        template_path = self.get_template_path(template_subtype, contract)
        if not template_path:
            return {"success": False, "error": f"模板文件不存在: {template_subtype}"}

        from apps.documents.services.generation.pipeline import DocxPreviewService, PipelineContextBuilder

        # 自动查找关联合同的首个案件
        case = contract.cases.select_related(
            "contract",
        ).prefetch_related(
            "supervising_authorities", "case_numbers", "assignments__lawyer", "parties__client",
        ).first()

        context_builder = PipelineContextBuilder()
        context = context_builder.build_archive_context(contract, case)

        # 合并用户覆盖值
        self._apply_overrides(context, contract, template_subtype)

        rows = DocxPreviewService().preview(str(template_path), context)
        return {"success": True, "data": rows}

    def get_template_path(self, template_subtype: str, contract: Contract | None = None) -> Path | None:
        """
        获取归档模板文件的完整路径。

        优先从 DocumentTemplate 数据库查找匹配合同 case_type 的归档模板，
        找不到再回退到硬编码的公有目录模板。

        Args:
            template_subtype: DocumentArchiveSubType 值，如 "case_cover"
            contract: 合同实例（可选，用于按 case_type 匹配模板）

        Returns:
            模板文件路径，不存在返回 None
        """
        # 1. 优先从数据库查找匹配的归档模板
        db_path = self._get_template_path_from_db(template_subtype, contract)
        if db_path:
            return db_path

        # 2. 回退到硬编码路径
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

    @staticmethod
    def _apply_overrides(context: dict[str, Any], contract: Contract, template_subtype: str) -> None:
        """将用户覆盖值合并到 context 中"""
        from apps.contracts.models.archive_override import ArchivePlaceholderOverride

        override_obj = ArchivePlaceholderOverride.objects.filter(
            contract=contract,
            template_subtype=template_subtype,
        ).first()

        if override_obj and override_obj.overrides:
            for key, value in override_obj.overrides.items():
                if value is not None and value != "":
                    context[key] = value

    @staticmethod
    def _get_template_path_from_db(template_subtype: str, contract: Contract | None) -> Path | None:
        """从 DocumentTemplate 数据库查找匹配的归档模板路径"""
        from apps.documents.models import DocumentTemplate, DocumentTemplateType

        templates = DocumentTemplate.objects.filter(
            template_type=DocumentTemplateType.ARCHIVE,
            archive_sub_type=template_subtype,
            is_active=True,
        )

        case_type = getattr(contract, "case_type", None) if contract else None

        for template in templates:
            case_types = template.case_types or []
            # 空列表表示匹配所有；有值时需要匹配 case_type
            if not case_types or "all" in case_types or (case_type and case_type in case_types):
                file_location = template.get_file_location()
                if file_location and Path(file_location).exists():
                    return Path(file_location)

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

    def generate_single_archive_document(
        self,
        contract: Contract,
        archive_item_code: str,
        case: Any | None = None,
    ) -> dict[str, Any]:
        """
        生成单个归档文书。

        Args:
            contract: 合同实例
            archive_item_code: 归档检查清单编号 (如 "cr_1", "lt_6")
            case: 案件实例（可选）

        Returns:
            生成结果字典
        """
        archive_category = get_archive_category(contract.case_type)
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

        # 查找目标项
        target_item = None
        for item in checklist_items:
            if item["code"] == archive_item_code:
                target_item = item
                break

        if not target_item:
            return {"template_subtype": None, "error": f"未找到检查清单项: {archive_item_code}"}

        if not target_item["template"]:
            return {"template_subtype": None, "error": "该检查项不支持模板生成"}

        # 如果没有传入 case，自动查找
        if case is None:
            case = contract.cases.select_related(
                "contract",
            ).prefetch_related(
                "supervising_authorities", "case_numbers", "assignments__lawyer", "parties__client",
            ).first()

        return self._generate_single_document(contract, target_item, case)

    def download_archive_item(
        self,
        contract: Contract,
        archive_item_code: str,
    ) -> dict[str, Any]:
        """
        下载归档检查项对应的材料文件。

        如果同一检查项下有多个文件，合并为一个 PDF 后返回。
        如果是模板类型的项且材料不存在，自动先生成再下载。

        Args:
            contract: 合同实例
            archive_item_code: 归档检查清单编号

        Returns:
            {"content": bytes, "filename": str, "content_type": str} 或 {"error": str}
        """
        materials = list(
            FinalizedMaterial.objects.filter(
                contract=contract,
                archive_item_code=archive_item_code,
            ).order_by("order", "-uploaded_at")
        )

        # 如果没有 archive_item_code，也检查通过 _map 逻辑关联的材料
        if not materials:
            from apps.contracts.models.finalized_material import MaterialCategory

            # 委托合同项：CONTRACT_ORIGINAL / SUPPLEMENTARY_AGREEMENT
            if "委托" in archive_item_code or self._is_contract_item(contract, archive_item_code):
                materials = list(
                    FinalizedMaterial.objects.filter(
                        contract=contract,
                        category__in=(MaterialCategory.CONTRACT_ORIGINAL, MaterialCategory.SUPPLEMENTARY_AGREEMENT),
                    ).order_by("order", "-uploaded_at")
                )

        # 如果仍没有材料，尝试自动生成（模板类型的项）
        if not materials:
            gen_result = self.generate_single_archive_document(contract, archive_item_code)
            if not gen_result.get("error") and gen_result.get("material_id"):
                materials = list(
                    FinalizedMaterial.objects.filter(
                        contract=contract,
                        archive_item_code=archive_item_code,
                    ).order_by("order", "-uploaded_at")
                )

        if not materials:
            return {"error": "未找到对应的归档材料"}

        # 单个文件直接返回
        if len(materials) == 1:
            return self._read_material_file(materials[0])

        # 多个文件：合并为 PDF
        return self._merge_materials_to_pdf(materials, archive_item_code)

    def _is_contract_item(self, contract: Contract, archive_item_code: str) -> bool:
        """判断 archive_item_code 是否为"委托合同"相关的检查项"""
        archive_category = get_archive_category(contract.case_type)
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
        for item in checklist_items:
            if item["code"] == archive_item_code and item["source"] == "contract" and "委托" in item["name"]:
                return True
        return False

    def _read_material_file(self, material: FinalizedMaterial) -> dict[str, Any]:
        """读取单个材料文件的内容"""
        from django.conf import settings as django_settings

        file_path = Path(material.file_path)
        if not file_path.is_absolute():
            file_path = Path(django_settings.MEDIA_ROOT) / file_path

        if not file_path.exists():
            return {"error": f"文件不存在: {material.original_filename}"}

        content = file_path.read_bytes()
        # 判断文件类型
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            content_type = "application/pdf"
        elif suffix == ".docx":
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            content_type = "application/octet-stream"

        return {
            "content": content,
            "filename": material.original_filename,
            "content_type": content_type,
        }

    def _merge_materials_to_pdf(
        self,
        materials: list[FinalizedMaterial],
        archive_item_code: str,
    ) -> dict[str, Any]:
        """将多个材料文件合并为一个 PDF"""
        import fitz  # PyMuPDF
        from django.conf import settings as django_settings

        merged_doc = fitz.open()
        filenames: list[str] = []

        try:
            for material in materials:
                file_path = Path(material.file_path)
                if not file_path.is_absolute():
                    file_path = Path(django_settings.MEDIA_ROOT) / file_path

                if not file_path.exists():
                    logger.warning("合并时文件不存在: %s", material.original_filename)
                    continue

                suffix = file_path.suffix.lower()

                if suffix == ".pdf":
                    try:
                        src_doc = fitz.open(str(file_path))
                        merged_doc.insert_pdf(src_doc)
                        src_doc.close()
                        filenames.append(material.original_filename)
                    except Exception as e:
                        logger.warning("合并PDF失败: %s, error: %s", material.original_filename, e)
                elif suffix == ".docx":
                    # DOCX 需要先转为 PDF
                    try:
                        from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf

                        pdf_bytes = convert_docx_to_pdf(str(file_path))
                        if pdf_bytes:
                            src_doc = fitz.open("pdf", pdf_bytes)
                            merged_doc.insert_pdf(src_doc)
                            src_doc.close()
                            filenames.append(material.original_filename)
                    except Exception as e:
                        logger.warning("DOCX转PDF失败: %s, error: %s", material.original_filename, e)
                else:
                    logger.warning("不支持的文件类型: %s", suffix)

            if len(merged_doc) == 0:
                return {"error": "没有可合并的文件"}

            # 保存合并后的 PDF
            buffer = BytesIO()
            merged_doc.save(buffer)
            content = buffer.getvalue()

            # 生成文件名
            from apps.contracts.services.archive.constants import ARCHIVE_CHECKLIST
            from .category_mapping import get_archive_category

            item_name = archive_item_code
            archive_category = get_archive_category(materials[0].contract.case_type)
            for item in ARCHIVE_CHECKLIST.get(archive_category, []):
                if item["code"] == archive_item_code:
                    item_name = item["name"]
                    break

            filename = f"{item_name}_合并.pdf"

            return {
                "content": content,
                "filename": filename,
                "content_type": "application/pdf",
            }
        finally:
            merged_doc.close()

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

        template_path = self.get_template_path(template_subtype, contract)
        if not template_path:
            return {"template_subtype": template_subtype, "error": f"模板文件不存在: {template_subtype}"}

        try:
            from apps.documents.services.generation.pipeline import DocxRenderer, PipelineContextBuilder

            # 构建上下文
            context_builder = PipelineContextBuilder()
            context = context_builder.build_archive_context(contract, case)

            # 合并用户覆盖值
            self._apply_overrides(context, contract, template_subtype)

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
