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
from .constants import (
    ARCHIVE_CHECKLIST,
    ARCHIVE_FILE_NUMBERING,
    ARCHIVE_FOLDER_NAME,
    ARCHIVE_SKIP_CODES,
    ARCHIVE_SKIP_TEMPLATES,
    ARCHIVE_SUBITEM_ORDER_RULES,
    ARCHIVE_TEMPLATE_DOC_TYPES,
    ChecklistItem,
)

logger = logging.getLogger("apps.contracts.archive")


# 归档模板子类型 → 文件名映射
_ARCHIVE_TEMPLATE_FILES: dict[str, str] = {
    "case_cover": "1-案卷封面.docx",
    "closing_archive_register": "2-结案归档登记表.docx",
    "inner_catalog": "3-卷内目录.docx",
    "lawyer_work_log": "5-律师工作日志.docx",
    "case_summary": "7-办案小结.docx",
}

# 归档分类 → 案卷目录清单编号映射（用于延迟重新生成）
_ARCHIVE_CATALOG_CODES: dict[str, str] = {
    "non_litigation": "nl_3",
    "litigation": "lt_3",
    "criminal": "cr_3",
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

        # 检查是否存在用户覆盖值
        from apps.contracts.models.archive_override import ArchivePlaceholderOverride

        override_obj = ArchivePlaceholderOverride.objects.filter(
            contract=contract,
            template_subtype=template_subtype,
        ).first()
        has_overrides = bool(override_obj and override_obj.overrides)

        # 合并用户覆盖值
        self._apply_overrides(context, contract, template_subtype)

        rows = DocxPreviewService().preview(str(template_path), context)
        return {"success": True, "data": rows, "has_overrides": has_overrides}

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
        # 如果没有传入 case，自动查找关联合同的首个案件
        if case is None:
            case = contract.cases.select_related(
                "contract",
            ).prefetch_related(
                "supervising_authorities", "case_numbers", "assignments__lawyer", "parties__client",
            ).first()

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
        对于模板类型的项，始终重新生成以确保与预览一致（占位符值可能已更新）。
        非模板类型的项（上传的材料）直接返回已有文件。

        Args:
            contract: 合同实例
            archive_item_code: 归档检查清单编号

        Returns:
            {"content": bytes, "filename": str, "content_type": str} 或 {"error": str}
        """
        # 检查是否为模板类型的项 — 始终重新生成以确保与预览一致
        checklist_item = self._find_checklist_item(contract, archive_item_code)
        if checklist_item and checklist_item.get("template"):
            return self._download_template_item(contract, archive_item_code, checklist_item)

        # 非模板类型：直接返回已上传的材料文件
        return self._download_uploaded_item(contract, archive_item_code)

    def _find_checklist_item(self, contract: Contract, archive_item_code: str) -> ChecklistItem | None:
        """查找检查清单中指定编号的项"""
        archive_category = get_archive_category(contract.case_type)
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
        for item in checklist_items:
            if item["code"] == archive_item_code:
                return item
        return None

    def _download_template_item(
        self,
        contract: Contract,
        archive_item_code: str,
        checklist_item: ChecklistItem,
    ) -> dict[str, Any]:
        """下载模板类型的归档项 — 始终重新生成以确保与预览一致"""
        gen_result = self.generate_single_archive_document(contract, archive_item_code)
        if gen_result.get("error"):
            return {"error": gen_result["error"]}

        # 直接从生成结果中获取文件内容（避免再次从磁盘读取）
        content = gen_result.get("content")
        filename = gen_result.get("filename", "")
        if content:
            return {
                "content": content,
                "filename": filename,
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }

        return {"error": "生成失败：无文件内容"}

    @staticmethod
    def _apply_subitem_sort(
        materials: list[FinalizedMaterial],
        archive_item_code: str,
    ) -> list[FinalizedMaterial]:
        """对有排序规则的清单项，按关键词顺序重排 order=0 的材料。

        同步时已为材料设置 order 值，此处仅兜底处理 order=0（未排序）的材料。
        用户手动调整后 order>0，本方法不再干预。
        """
        keywords = ARCHIVE_SUBITEM_ORDER_RULES.get(archive_item_code)
        if not keywords or len(materials) <= 1:
            return materials

        # 检查是否所有材料都有 order > 0（已排序），如果是则无需再排
        if all(m.order > 0 for m in materials):
            return materials

        ordered_mats = [m for m in materials if m.order > 0]
        unordered_mats = [m for m in materials if m.order == 0]

        if not unordered_mats:
            return materials

        def _sort_key(mat: FinalizedMaterial) -> tuple[int, int]:
            for i, keyword in enumerate(keywords):
                if keyword in mat.original_filename:
                    return (0, i)
            return (1, 0)

        unordered_mats.sort(key=_sort_key)
        return ordered_mats + unordered_mats

    def _download_uploaded_item(
        self,
        contract: Contract,
        archive_item_code: str,
    ) -> dict[str, Any]:
        """下载非模板类型的归档项（已上传的材料文件）"""
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

            # 收费凭证项：匹配发票
            if not materials and self._is_fee_voucher_item(contract, archive_item_code):
                materials = list(
                    FinalizedMaterial.objects.filter(
                        contract=contract,
                        category=MaterialCategory.INVOICE,
                    ).order_by("order", "-uploaded_at")
                )

            # 授权委托项：匹配授权委托材料
            if not materials and self._is_authorization_item(contract, archive_item_code):
                materials = list(
                    FinalizedMaterial.objects.filter(
                        contract=contract,
                        category=MaterialCategory.AUTHORIZATION_MATERIAL,
                    ).order_by("order", "-uploaded_at")
                )

        # 对 order=0 的材料应用关键词排序（order>0 的已由同步/用户设定，不再干预）
        materials = self._apply_subitem_sort(materials, archive_item_code)

        if not materials:
            return {"error": "未找到对应的归档材料"}

        # 单个文件直接返回
        if len(materials) == 1:
            return self._read_material_file(materials[0])

        # 多个文件：合并为 PDF
        return self._merge_materials_to_pdf(materials, archive_item_code)

    def _is_contract_item(self, contract: Contract, archive_item_code: str) -> bool:
        """判断 archive_item_code 是否为"委托合同"相关的检查项"""
        return self._is_item_by_name(contract, archive_item_code, "委托")

    def _is_fee_voucher_item(self, contract: Contract, archive_item_code: str) -> bool:
        """判断 archive_item_code 是否为"收费凭证"相关的检查项"""
        return self._is_item_by_name(contract, archive_item_code, "收费")

    def _is_authorization_item(self, contract: Contract, archive_item_code: str) -> bool:
        """判断 archive_item_code 是否为"授权委托"相关的检查项"""
        return self._is_item_by_name(contract, archive_item_code, "授权")

    @staticmethod
    def _is_item_by_name(contract: Contract, archive_item_code: str, name_keyword: str) -> bool:
        """判断 archive_item_code 对应的检查项名称是否包含指定关键词"""
        archive_category = get_archive_category(contract.case_type)
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
        for item in checklist_items:
            if item["code"] == archive_item_code and name_keyword in item.get("name", ""):
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

    # ================================================================
    # 归档文件夹生成
    # ================================================================

    def generate_archive_folder(self, contract: Contract) -> dict[str, Any]:
        """
        生成归档文件夹到合同绑定的文件夹根目录。

        流程：
        1. 先调用 generate_archive_documents() 生成模板文书到 DB
        2. 在合同绑定文件夹下创建"归档文件夹"目录
        3. 将1-3号模板文书写入（仅 docx），文件名带合同名称和日期
        4. 将剩余材料项合并为"4-案卷材料（{合同名称}）_{日期}.pdf"（带页码）

        Args:
            contract: 合同实例

        Returns:
            {"success": bool, "archive_dir": str, "generated_docs": list,
             "errors": list, "folder_path": str}
        """
        from apps.contracts.models.folder_binding import ContractFolderBinding

        # 1. 检查文件夹绑定
        try:
            binding = contract.folder_binding
        except ContractFolderBinding.DoesNotExist:
            binding = None

        if not binding or not binding.folder_path:
            return {"success": False, "error": "合同未绑定文件夹"}

        folder_path = Path(binding.folder_path)
        if not folder_path.exists():
            return {"success": False, "error": f"绑定文件夹不存在: {binding.folder_path}"}

        # 2. 先生成模板文书到 DB（复用已有逻辑）
        doc_results = self.generate_archive_documents(contract)

        # 2.1 重新生成案卷目录：generate_archive_documents 按清单顺序逐个生成，
        # 案卷目录（inner_catalog）排在律师工作日志、办案小结之前，
        # 导致首次生成时这两项尚未写入 DB，案卷目录会遗漏它们。
        # 所有模板文书生成完毕后，重新生成案卷目录以确保内容完整。
        archive_category = get_archive_category(contract.case_type)
        catalog_code = _ARCHIVE_CATALOG_CODES.get(archive_category)
        if catalog_code:
            catalog_result = self.generate_single_archive_document(contract, catalog_code)
            # 替换 doc_results 中的案卷目录结果
            for i, r in enumerate(doc_results):
                if r.get("template_subtype") == "inner_catalog":
                    doc_results[i] = catalog_result
                    break

        # 3. 创建归档文件夹
        archive_dir = folder_path / ARCHIVE_FOLDER_NAME
        archive_dir.mkdir(parents=True, exist_ok=True)

        from datetime import date

        generated_docs: list[str] = []
        errors: list[str] = []

        # 4. 写入1-3号模板文书（仅 docx）
        contract_name = contract.name or "未命名合同"
        today_str = date.today().strftime("%Y%m%d")
        for seq_num, (template_subtype, doc_name) in ARCHIVE_FILE_NUMBERING.items():
            if template_subtype == "case_materials":
                continue  # 4-案卷材料单独处理

            base_name = f"{seq_num}-{doc_name}（{contract_name}）_{today_str}"
            try:
                self._write_template_doc_to_folder(
                    contract=contract,
                    template_subtype=template_subtype,
                    seq_num=seq_num,
                    doc_name=doc_name,
                    archive_dir=archive_dir,
                )
                generated_docs.append(base_name)
            except Exception as e:
                error_msg = f"{base_name}: {e}"
                errors.append(error_msg)
                logger.exception("写入归档文书失败: %s", error_msg)

        # 5. 生成"4-案卷材料.pdf"
        case_materials_name = f"4-案卷材料（{contract_name}）_{today_str}"
        try:
            mat_result = self._compile_case_materials_pdf(contract, archive_dir)
            if mat_result.get("written"):
                generated_docs.append(case_materials_name)
            elif mat_result.get("skipped"):
                logger.info("无可合并的案卷材料，跳过%s.pdf", case_materials_name)
            else:
                errors.append(f"{case_materials_name}: {mat_result.get('error', '未知错误')}")
        except Exception as e:
            errors.append(f"{case_materials_name}: {e}")
            logger.exception("生成案卷材料PDF失败")

        logger.info(
            "归档文件夹生成完成: %s, 成功 %d 项, 失败 %d 项",
            archive_dir,
            len(generated_docs),
            len(errors),
            extra={"contract_id": contract.id, "archive_dir": str(archive_dir)},
        )

        return {
            "success": True,
            "archive_dir": str(archive_dir),
            "generated_docs": generated_docs,
            "errors": errors,
            "folder_path": str(folder_path),
            "doc_results": doc_results,
        }

    def _write_template_doc_to_folder(
        self,
        contract: Contract,
        template_subtype: str,
        seq_num: int,
        doc_name: str,
        archive_dir: Path,
    ) -> None:
        """
        将单个模板文书写入归档文件夹（仅 docx）。

        从 FinalizedMaterial 读取已生成的docx，只写入docx。
        文件名格式：{序号}-{文档名}（{合同名称}）_{日期}.docx
        """
        from datetime import date

        archive_category = get_archive_category(contract.case_type)
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

        # 找到对应的清单项 code
        item_code = None
        for item in checklist_items:
            if item.get("template") == template_subtype:
                item_code = item["code"]
                break

        if not item_code:
            raise ValueError(f"未找到模板子类型 {template_subtype} 对应的清单项")

        # 从 DB 读取已生成的 docx
        material = FinalizedMaterial.objects.filter(
            contract=contract,
            archive_item_code=item_code,
        ).first()

        if not material:
            raise ValueError(f"模板文书尚未生成: {template_subtype}")

        docx_path = Path(material.file_path)
        if not docx_path.is_absolute():
            from django.conf import settings as django_settings
            docx_path = Path(django_settings.MEDIA_ROOT) / docx_path

        if not docx_path.exists():
            raise ValueError(f"docx文件不存在: {docx_path}")

        # 生成带合同名称和日期的文件名
        contract_name = contract.name or "未命名合同"
        today_str = date.today().strftime("%Y%m%d")
        base_name = f"{seq_num}-{doc_name}（{contract_name}）_{today_str}"

        # 写入 docx
        dest_docx = archive_dir / f"{base_name}.docx"
        dest_docx.write_bytes(docx_path.read_bytes())

    def _compile_case_materials_pdf(
        self,
        contract: Contract,
        archive_dir: Path,
    ) -> dict[str, Any]:
        """
        将归档检查清单中非1-3号的已上传材料合并为"4-案卷材料（{合同名称}）_{日期}.pdf"。

        合并顺序与检查清单顺序一致，从第1页开始添加页码。

        Returns:
            {"written": bool, "page_count": int, "skipped": bool, "error": str|None}
        """
        import fitz  # PyMuPDF

        archive_category = get_archive_category(contract.case_type)
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

        # 按 checklist 顺序收集需要合并的材料
        materials_to_merge: list[FinalizedMaterial] = []

        for item in checklist_items:
            code = item["code"]
            template = item.get("template")

            # 跳过1-3号模板项
            if code in ARCHIVE_SKIP_CODES or template in ARCHIVE_SKIP_TEMPLATES:
                continue

            # 查找该清单项关联的 FinalizedMaterial
            item_materials = list(
                FinalizedMaterial.objects.filter(
                    contract=contract,
                    archive_item_code=code,
                ).order_by("order", "-uploaded_at")
            )

            # 特殊处理：委托合同项 — 追加无 archive_item_code 的合同正本/补充协议
            if item.get("source") == "contract" and "委托" in item.get("name", ""):
                existing_ids = {m.id for m in item_materials}
                extra = list(
                    FinalizedMaterial.objects.filter(
                        contract=contract,
                        category__in=(MaterialCategory.CONTRACT_ORIGINAL, MaterialCategory.SUPPLEMENTARY_AGREEMENT),
                        archive_item_code="",
                    ).order_by("order", "-uploaded_at")
                )
                for m in extra:
                    if m.id not in existing_ids:
                        item_materials.append(m)

            # 特殊处理：授权委托项 — 追加无 archive_item_code 的授权委托材料
            if "授权" in item.get("name", ""):
                existing_ids = {m.id for m in item_materials}
                extra = list(
                    FinalizedMaterial.objects.filter(
                        contract=contract,
                        category=MaterialCategory.AUTHORIZATION_MATERIAL,
                        archive_item_code="",
                    ).order_by("order", "-uploaded_at")
                )
                for m in extra:
                    if m.id not in existing_ids:
                        item_materials.append(m)

            # 特殊处理：监督卡项 — 追加无 archive_item_code 的监督卡材料
            if item.get("auto_detect") == "supervision_card":
                existing_ids = {m.id for m in item_materials}
                extra = list(
                    FinalizedMaterial.objects.filter(
                        contract=contract,
                        category=MaterialCategory.SUPERVISION_CARD,
                        archive_item_code="",
                    ).order_by("order", "-uploaded_at")
                )
                for m in extra:
                    if m.id not in existing_ids:
                        item_materials.append(m)

            # 特殊处理：收费凭证项 — 追加无 archive_item_code 的发票材料
            if "收费" in item.get("name", ""):
                existing_ids = {m.id for m in item_materials}
                extra = list(
                    FinalizedMaterial.objects.filter(
                        contract=contract,
                        category=MaterialCategory.INVOICE,
                        archive_item_code="",
                    ).order_by("order", "-uploaded_at")
                )
                for m in extra:
                    if m.id not in existing_ids:
                        item_materials.append(m)

            if item_materials:
                # 对 order=0 的材料应用关键词排序
                item_materials = self._apply_subitem_sort(item_materials, code)
                materials_to_merge.extend(item_materials)

        if not materials_to_merge:
            return {"written": False, "skipped": True, "page_count": 0, "error": None}

        # 合并所有材料为一个 PDF
        from django.conf import settings as django_settings

        merged_doc = fitz.open()

        try:
            for material in materials_to_merge:
                file_path = Path(material.file_path)
                if not file_path.is_absolute():
                    file_path = Path(django_settings.MEDIA_ROOT) / file_path

                if not file_path.exists():
                    logger.warning("案卷材料文件不存在: %s", material.original_filename)
                    continue

                suffix = file_path.suffix.lower()

                if suffix == ".pdf":
                    try:
                        src_doc = fitz.open(str(file_path))
                        merged_doc.insert_pdf(src_doc)
                        src_doc.close()
                    except Exception as e:
                        logger.warning("合并PDF失败: %s, error: %s", material.original_filename, e)
                elif suffix == ".docx":
                    try:
                        from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf

                        pdf_result = convert_docx_to_pdf(str(file_path))
                        if pdf_result and Path(pdf_result).exists():
                            src_doc = fitz.open(pdf_result)
                            merged_doc.insert_pdf(src_doc)
                            src_doc.close()
                            # 清理临时文件
                            try:
                                Path(pdf_result).unlink()
                            except OSError:
                                pass
                        else:
                            logger.warning("DOCX转PDF失败: %s", material.original_filename)
                    except Exception as e:
                        logger.warning("DOCX转PDF失败: %s, error: %s", material.original_filename, e)
                else:
                    logger.warning("不支持的文件类型: %s (%s)", suffix, material.original_filename)

            if len(merged_doc) == 0:
                return {"written": False, "skipped": True, "page_count": 0, "error": "没有可合并的文件"}

            # 添加页码（从第1页开始，居中底部）
            self._add_page_numbers(merged_doc)

            # 保存到归档文件夹（带合同名称和日期）
            from datetime import date

            contract_name = contract.name or "未命名合同"
            today_str = date.today().strftime("%Y%m%d")
            dest_pdf = archive_dir / f"4-案卷材料（{contract_name}）_{today_str}.pdf"
            merged_doc.save(str(dest_pdf))
            page_count = len(merged_doc)

            logger.info(
                "案卷材料PDF生成完成: %d 页, %d 份材料",
                page_count,
                len(materials_to_merge),
                extra={"contract_id": contract.id, "dest": str(dest_pdf)},
            )

            return {"written": True, "page_count": page_count, "skipped": False, "error": None}

        except Exception as e:
            logger.exception("合并案卷材料PDF失败")
            return {"written": False, "skipped": False, "page_count": 0, "error": str(e)}
        finally:
            merged_doc.close()

    @staticmethod
    def _add_page_numbers(doc: Any, start_page: int = 1) -> None:
        """
        为PDF文档的每一页添加页码（居中底部）。

        Args:
            doc: fitz.Document 实例
            start_page: 页码起始编号（默认1）
        """
        import fitz

        for i, page in enumerate(doc):
            page_num = start_page + i
            rect = page.rect
            # 页码位置：居中底部，距底边 30pt
            point = fitz.Point(rect.width / 2, rect.height - 30)
            font = fitz.Font("helv")  # 内置 Helvetica 字体
            page.insert_text(
                point,
                str(page_num),
                fontname="helv",
                fontsize=9,
                color=(0, 0, 0),
            )

    def scale_pages_to_a4(self, contract: Contract) -> dict[str, Any]:
        """
        将合同所有已上传的归档 PDF 材料按 A4 尺寸缩放。

        遍历合同的 FinalizedMaterial 中所有 PDF 文件，
        对非 A4 尺寸的页面进行缩放，使其适配 A4 (595×842 pt)。
        缩放后原地覆盖保存。

        Returns:
            {"success": bool, "scaled_count": int, "skipped_count": int, "errors": list}
        """
        import fitz

        A4_W, A4_H = 595.0, 842.0
        TOLERANCE = 1.0  # 容差 1pt

        # 查找所有 PDF 材料
        pdf_materials = list(
            FinalizedMaterial.objects.filter(
                contract=contract,
                original_filename__iendswith=".pdf",
            ).order_by("order", "-uploaded_at")
        )

        if not pdf_materials:
            return {"success": True, "scaled_count": 0, "skipped_count": 0, "errors": []}

        from django.conf import settings as django_settings

        scaled_count = 0
        skipped_count = 0
        errors: list[str] = []

        for material in pdf_materials:
            file_path = Path(material.file_path)
            if not file_path.is_absolute():
                file_path = Path(django_settings.MEDIA_ROOT) / file_path

            if not file_path.exists():
                errors.append(f"{material.original_filename}: 文件不存在")
                continue

            try:
                src_doc = fitz.open(str(file_path))
            except Exception as e:
                errors.append(f"{material.original_filename}: 无法打开PDF - {e}")
                continue

            try:
                # 先检查是否有需要缩放的页面
                has_non_a4 = False
                for page in src_doc:
                    page_w, page_h = page.rect.width, page.rect.height
                    is_a4 = (
                        abs(page_w - A4_W) < TOLERANCE and abs(page_h - A4_H) < TOLERANCE
                    ) or (
                        abs(page_w - A4_H) < TOLERANCE and abs(page_h - A4_W) < TOLERANCE
                    )
                    if not is_a4:
                        has_non_a4 = True
                        break

                if not has_non_a4:
                    skipped_count += 1
                    continue

                # 创建新文档，逐页缩放
                out_doc = fitz.open()

                for page in src_doc:
                    page_w, page_h = page.rect.width, page.rect.height
                    is_a4 = (
                        abs(page_w - A4_W) < TOLERANCE and abs(page_h - A4_H) < TOLERANCE
                    ) or (
                        abs(page_w - A4_H) < TOLERANCE and abs(page_h - A4_W) < TOLERANCE
                    )

                    if is_a4:
                        # 已经是 A4，直接复制
                        out_doc.insert_pdf(src_doc, from_page=page.number, to_page=page.number)
                    else:
                        # 非 A4 页面：缩放居中到 A4
                        if page_w > page_h:
                            target_w, target_h = A4_H, A4_W  # 横向
                        else:
                            target_w, target_h = A4_W, A4_H  # 纵向

                        scale = min(target_w / page_w, target_h / page_h)
                        new_page = out_doc.new_page(width=target_w, height=target_h)

                        x0 = (target_w - page_w * scale) / 2
                        y0 = (target_h - page_h * scale) / 2
                        target_rect = fitz.Rect(x0, y0, x0 + page_w * scale, y0 + page_h * scale)

                        new_page.show_pdf_page(target_rect, src_doc, page.number)

                out_doc.save(str(file_path), deflate=True)
                out_doc.close()
                scaled_count += 1

                logger.info(
                    "PDF页面缩放为A4: %s",
                    material.original_filename,
                    extra={"contract_id": contract.id, "material_id": material.id},
                )

            except Exception as e:
                errors.append(f"{material.original_filename}: 缩放失败 - {e}")
                logger.exception("PDF缩放A4失败: %s", material.original_filename)
            finally:
                src_doc.close()

        logger.info(
            "A4裁切完成: contract_id=%s, scaled=%d, skipped=%d, errors=%d",
            contract.id,
            scaled_count,
            skipped_count,
            len(errors),
        )

        return {
            "success": True,
            "scaled_count": scaled_count,
            "skipped_count": skipped_count,
            "errors": errors,
        }
