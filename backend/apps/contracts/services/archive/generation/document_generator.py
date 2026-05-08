"""归档文书生成 + 预览。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial, MaterialCategory

from ..category_mapping import get_archive_category
from ..constants import ARCHIVE_CHECKLIST, ChecklistItem
from .template_finder import get_template_path

logger = logging.getLogger("apps.contracts.archive")


def preview_archive_template(contract_id: int, template_subtype: str) -> dict[str, Any]:
    """预览归档文书占位符替换词。"""
    contract = Contract.objects.filter(pk=contract_id).first()
    if not contract:
        return {"success": False, "error": "合同不存在"}

    template_path = get_template_path(template_subtype, contract)
    if not template_path:
        return {"success": False, "error": f"模板文件不存在: {template_subtype}"}

    from apps.documents.services.generation.pipeline import DocxPreviewService, PipelineContextBuilder

    case = contract.cases.select_related(
        "contract",
    ).prefetch_related(
        "supervising_authorities", "case_numbers", "assignments__lawyer", "parties__client",
    ).first()

    context_builder = PipelineContextBuilder()
    context = context_builder.build_archive_context(contract, case)

    from apps.contracts.models.archive_override import ArchivePlaceholderOverride

    override_obj = ArchivePlaceholderOverride.objects.filter(
        contract=contract,
        template_subtype=template_subtype,
    ).first()
    has_overrides = bool(override_obj and override_obj.overrides)

    _apply_overrides(context, contract, template_subtype)

    rows = DocxPreviewService().preview(str(template_path), context)
    return {"success": True, "data": rows, "has_overrides": has_overrides}


def generate_archive_documents(
    contract: Contract,
    case: Any | None = None,
) -> list[dict[str, Any]]:
    """批量生成归档文书。"""
    if case is None:
        case = contract.cases.select_related(
            "contract",
        ).prefetch_related(
            "supervising_authorities", "case_numbers", "assignments__lawyer", "parties__client",
        ).first()

    archive_category = get_archive_category(contract.case_type)
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

    template_items = [item for item in checklist_items if item["template"] is not None]

    results: list[dict[str, Any]] = []
    for item in template_items:
        result = _generate_single_document(contract, item, case)
        results.append(result)

    return results


def generate_single_archive_document(
    contract: Contract,
    archive_item_code: str,
    case: Any | None = None,
) -> dict[str, Any]:
    """生成单个归档文书。"""
    archive_category = get_archive_category(contract.case_type)
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

    target_item = None
    for item in checklist_items:
        if item["code"] == archive_item_code:
            target_item = item
            break

    if not target_item:
        return {"template_subtype": None, "error": f"未找到检查清单项: {archive_item_code}"}

    if not target_item["template"]:
        return {"template_subtype": None, "error": "该检查项不支持模板生成"}

    if case is None:
        case = contract.cases.select_related(
            "contract",
        ).prefetch_related(
            "supervising_authorities", "case_numbers", "assignments__lawyer", "parties__client",
        ).first()

    return _generate_single_document(contract, target_item, case)


def _apply_overrides(context: dict[str, Any], contract: Contract, template_subtype: str) -> None:
    """将用户覆盖值合并到 context 中。"""
    from apps.contracts.models.archive_override import ArchivePlaceholderOverride

    override_obj = ArchivePlaceholderOverride.objects.filter(
        contract=contract,
        template_subtype=template_subtype,
    ).first()

    if override_obj and override_obj.overrides:
        for key, value in override_obj.overrides.items():
            if value is not None and value != "":
                context[key] = value


def _generate_single_document(
    contract: Contract,
    item: ChecklistItem,
    case: Any | None = None,
) -> dict[str, Any]:
    """生成单个归档文书。"""
    template_subtype = item["template"]
    if not template_subtype:
        return {"template_subtype": None, "error": "非模板生成项"}

    template_path = get_template_path(template_subtype, contract)
    if not template_path:
        return {"template_subtype": template_subtype, "error": f"模板文件不存在: {template_subtype}"}

    try:
        from apps.documents.services.generation.pipeline import DocxRenderer, PipelineContextBuilder

        context_builder = PipelineContextBuilder()
        context = context_builder.build_archive_context(contract, case)

        _apply_overrides(context, contract, template_subtype)

        content = DocxRenderer().render(str(template_path), context)

        filename = _generate_filename(contract, item)

        material = _save_as_material(
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


def _generate_filename(contract: Contract, item: ChecklistItem) -> str:
    """生成归档文书文件名。"""
    from datetime import date

    contract_name = contract.name or "未命名合同"
    item_name = item["name"]
    today_str = date.today().strftime("%Y%m%d")

    return f"{item_name}（{contract_name}）_{today_str}.docx"


def _save_as_material(
    contract: Contract,
    content: bytes,
    filename: str,
    archive_item_code: str,
) -> FinalizedMaterial | None:
    """将生成的文书保存为 FinalizedMaterial 记录。"""
    from django.core.files.base import ContentFile

    try:
        existing = FinalizedMaterial.objects.filter(
            contract=contract,
            archive_item_code=archive_item_code,
        ).first()

        if existing:
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
