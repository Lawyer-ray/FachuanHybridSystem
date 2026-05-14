"""案件材料同步到归档。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial, MaterialCategory
from apps.contracts.services.contract.integrations.material_service import MaterialService

from ..category_mapping import get_archive_category
from ..constants import ARCHIVE_CHECKLIST, ARCHIVE_SUBITEM_ORDER_RULES, CASE_MATERIAL_KEYWORD_MAPPING
from .material_mapping import match_type_name_to_code

logger = logging.getLogger("apps.contracts.archive")


def _get_archive_item_name(archive_category: str, archive_item_code: str) -> str:
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    for item in checklist_items:
        if item["code"] == archive_item_code:
            return str(item["name"])
    return archive_item_code


def _build_archive_subdir(prefix: str, archive_category: str, archive_item_code: str) -> str:
    return f"{prefix}/{_get_archive_item_name(archive_category, archive_item_code)}"


def get_case_material_match_map(contract: Contract) -> dict[str, Any]:
    """获取合同关联案件中 CaseMaterial 到 archive_item_code 的匹配映射。"""
    archive_category = get_archive_category(contract.case_type)
    keyword_map = CASE_MATERIAL_KEYWORD_MAPPING.get(archive_category, {})
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

    case_source_items = {item["code"]: item for item in checklist_items if item["source"] == "case"}

    existing_codes = set(
        FinalizedMaterial.objects.filter(
            contract=contract,
            archive_item_code__in=case_source_items.keys(),
        ).values_list("archive_item_code", flat=True)
    )

    synced_case_material_codes = set(
        FinalizedMaterial.objects.filter(
            contract=contract,
            archive_item_code__in=case_source_items.keys(),
            category=MaterialCategory.CASE_MATERIAL,
        ).values_list("archive_item_code", flat=True)
    )

    from apps.cases.models import CaseMaterial

    cases = list(contract.cases.all().only("id", "name"))

    cases_result: list[dict[str, Any]] = []
    summary_code_to_info: dict[str, dict[str, Any]] = {}
    all_matched_material_ids: set[int] = set()
    all_unmatched: list[dict[str, Any]] = []

    for case in cases:
        case_materials = list(CaseMaterial.objects.filter(case=case).only("id", "type_name", "category"))

        case_matches: list[dict[str, Any]] = []
        case_code_to_material_ids: dict[str, list[int]] = {}

        for cm in case_materials:
            matched_code = match_type_name_to_code(cm.type_name, keyword_map)
            if matched_code and matched_code in case_source_items:
                case_code_to_material_ids.setdefault(matched_code, []).append(cm.id)
                all_matched_material_ids.add(cm.id)
            else:
                all_unmatched.append(
                    {
                        "id": cm.id,
                        "type_name": cm.type_name,
                        "category": cm.category,
                        "case_id": case.id,
                        "case_name": case.name,
                    }
                )

        for code, item in case_source_items.items():
            cm_ids = case_code_to_material_ids.get(code, [])
            if not cm_ids:
                continue

            case_matches.append(
                {
                    "archive_item_code": code,
                    "archive_item_name": item["name"],
                    "case_material_ids": cm_ids,
                    "already_synced": code in existing_codes,
                }
            )

            if code not in summary_code_to_info:
                summary_code_to_info[code] = {
                    "archive_item_code": code,
                    "archive_item_name": item["name"],
                    "total_count": 0,
                    "case_count": 0,
                    "already_synced": code in existing_codes,
                    "has_case_material_sync": code in synced_case_material_codes,
                }
            summary_code_to_info[code]["total_count"] += len(cm_ids)
            summary_code_to_info[code]["case_count"] += 1

        if case_matches:
            cases_result.append(
                {
                    "case_id": case.id,
                    "case_name": case.name,
                    "matches": case_matches,
                }
            )

    summary = [summary_code_to_info[code] for code in case_source_items if code in summary_code_to_info]

    return {
        "archive_category": archive_category,
        "cases": cases_result,
        "summary": summary,
        "unmatched_case_materials": all_unmatched,
        "synced_count": sum(1 for s in summary if s["already_synced"]),
        "matchable_count": len(all_matched_material_ids),
    }


def sync_case_materials_to_archive(
    contract: Contract,
    archive_item_codes: list[str] | None = None,
    case_ids: list[int] | None = None,
) -> dict[str, Any]:
    """将案件材料同步到归档材料。"""
    archive_category = get_archive_category(contract.case_type)
    keyword_map = CASE_MATERIAL_KEYWORD_MAPPING.get(archive_category, {})
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    case_source_items = {item["code"]: item for item in checklist_items if item["source"] == "case"}

    if archive_item_codes is not None:
        case_source_items = {k: v for k, v in case_source_items.items() if k in archive_item_codes}

    existing_codes = set(
        FinalizedMaterial.objects.filter(
            contract=contract,
            archive_item_code__in=case_source_items.keys(),
        ).values_list("archive_item_code", flat=True)
    )

    cases_qs = contract.cases.all()
    if case_ids is not None:
        cases_qs = cases_qs.filter(id__in=case_ids)
    cases = list(cases_qs.only("id", "name"))

    code_to_case_materials: dict[str, list[Any]] = {}
    case_name_map: dict[int, str] = {c.id: c.name for c in cases}
    case_id_for_code: dict[str, int] = {}

    from apps.cases.models import CaseMaterial

    for case in cases:
        case_materials = list(
            CaseMaterial.objects.filter(case=case)
            .select_related("source_attachment")
            .only(
                "id",
                "type_name",
                "category",
                "source_attachment_id",
                "source_attachment__file",
                "case_id",
            )
        )
        for cm in case_materials:
            matched_code = match_type_name_to_code(cm.type_name, keyword_map)
            if matched_code and matched_code in case_source_items:
                if matched_code not in code_to_case_materials:
                    code_to_case_materials[matched_code] = []
                    case_id_for_code[matched_code] = case.id
                if case_id_for_code[matched_code] == case.id:
                    code_to_case_materials[matched_code].append(cm)

    synced: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for code in case_source_items:
        if code in existing_codes:
            skipped.append({"archive_item_code": code, "reason": "已有归档材料"})
            continue

        cms = code_to_case_materials.get(code, [])
        if not cms:
            skipped.append({"archive_item_code": code, "reason": "案件无匹配材料"})
            continue

        source_case_id = case_id_for_code.get(code)
        source_case_name = case_name_map.get(source_case_id, "") if source_case_id else ""

        for cm in cms:
            try:
                material = _copy_case_material_to_finalized(
                    contract=contract,
                    case_material=cm,
                    archive_item_code=code,
                )
                if material:
                    synced.append(
                        {
                            "archive_item_code": code,
                            "material_id": material.id,
                            "filename": material.original_filename,
                            "case_id": source_case_id,
                            "case_name": source_case_name,
                        }
                    )
                else:
                    errors.append(
                        {
                            "archive_item_code": code,
                            "error": "文件不存在或无法复制",
                            "case_id": source_case_id,
                        }
                    )
            except Exception as e:
                logger.exception("同步案件材料失败: code=%s, cm_id=%s", code, cm.id)
                errors.append(
                    {
                        "archive_item_code": code,
                        "error": str(e),
                        "case_id": source_case_id,
                    }
                )

    _apply_initial_order_for_synced(synced)
    return {"synced": synced, "skipped": skipped, "errors": errors}


def reset_and_resync_case_materials(
    contract: Contract,
    archive_item_codes: list[str] | None = None,
) -> dict[str, Any]:
    """重置并重新同步案件材料到归档。"""
    archive_category = get_archive_category(contract.case_type)
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    case_source_items = {item["code"]: item for item in checklist_items if item["source"] == "case"}

    if archive_item_codes is not None:
        target_codes = {code for code in archive_item_codes if code in case_source_items}
    else:
        target_codes = set(
            FinalizedMaterial.objects.filter(
                contract=contract,
                category=MaterialCategory.CASE_MATERIAL,
                archive_item_code__in=case_source_items.keys(),
            ).values_list("archive_item_code", flat=True)
        )

    if not target_codes:
        return {
            "deleted_count": 0,
            "deleted_files": [],
            "sync_result": {"synced": [], "skipped": [], "errors": []},
        }

    materials_to_delete = list(
        FinalizedMaterial.objects.filter(
            contract=contract,
            archive_item_code__in=target_codes,
            category=MaterialCategory.CASE_MATERIAL,
        ).only("id", "file_path", "relative_file_path", "archive_item_code")
    )

    material_service = MaterialService()
    deleted_files: list[str] = []

    for material in materials_to_delete:
        if material_service.delete_material_file(material):
            deleted_files.append(material.relative_file_path or material.file_path)
            logger.info(
                "重置同步：删除归档文件 %s (material_id=%s, code=%s)",
                material.file_path,
                material.id,
                material.archive_item_code,
            )

    deleted_count = len(materials_to_delete)
    FinalizedMaterial.objects.filter(id__in=[m.id for m in materials_to_delete]).delete()

    logger.info(
        "重置同步：已删除 %d 个归档材料 (codes=%s)",
        deleted_count,
        target_codes,
        extra={"contract_id": contract.id},
    )

    sync_result = sync_case_materials_to_archive(contract, archive_item_codes=list(target_codes))
    return {
        "deleted_count": deleted_count,
        "deleted_files": deleted_files,
        "sync_result": sync_result,
    }


def upload_material_to_archive_item(
    contract: Contract,
    archive_item_code: str,
    uploaded_file: Any,
    target_subdir: str = "",
) -> FinalizedMaterial:
    """将用户上传的文件保存为归档材料，并关联到指定清单项。"""
    archive_category = get_archive_category(contract.case_type)
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

    valid_codes = {item["code"] for item in checklist_items}
    if archive_item_code not in valid_codes:
        raise ValueError(f"无效的归档清单编号: {archive_item_code}")

    resolved_subdir = str(target_subdir or "").strip()
    if not resolved_subdir:
        resolved_subdir = _build_archive_subdir("归档清单", archive_category, archive_item_code)

    saved = MaterialService().save_business_material_file(
        uploaded_file=uploaded_file,
        contract_id=contract.id,
        target_subdir=resolved_subdir,
        allowed_extensions=[".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".xlsx", ".xls"],
        max_size_bytes=50 * 1024 * 1024,
    )

    max_order = (
        FinalizedMaterial.objects.filter(
            contract=contract,
            archive_item_code=archive_item_code,
        )
        .order_by("-order")
        .values_list("order", flat=True)
        .first()
        or 0
    )

    material = FinalizedMaterial.objects.create(
        contract=contract,
        file_path=saved.legacy_file_path,
        storage_root_type=saved.root_type,
        subdir_path=saved.subdir_path,
        relative_file_path=saved.relative_file_path,
        original_filename=saved.original_filename,
        category=MaterialCategory.ARCHIVE_UPLOAD,
        archive_item_code=archive_item_code,
        order=max_order + 1,
    )

    logger.info(
        "归档材料上传成功: %s -> %s",
        saved.original_filename,
        archive_item_code,
        extra={"contract_id": contract.id, "material_id": material.id},
    )
    return material


def _copy_case_material_to_finalized(
    contract: Contract,
    case_material: Any,
    archive_item_code: str,
) -> FinalizedMaterial | None:
    """将 CaseMaterial 的附件文件复制为 FinalizedMaterial。"""
    from django.conf import settings as django_settings
    from django.core.files.base import ContentFile

    attachment = case_material.source_attachment
    if not attachment:
        return None

    file_field = attachment.file
    file_path = getattr(file_field, "name", "")
    if not file_path:
        return None

    abs_path = Path(django_settings.MEDIA_ROOT) / file_path
    if not abs_path.exists():
        logger.warning("案件材料文件不存在: %s", abs_path)
        return None

    original_filename = Path(file_path).name
    archive_category = get_archive_category(contract.case_type)
    saved = MaterialService().save_business_material_file(
        uploaded_file=ContentFile(abs_path.read_bytes(), name=original_filename),
        contract_id=contract.id,
        target_subdir=_build_archive_subdir("案件材料同步", archive_category, archive_item_code),
        allowed_extensions=[".docx", ".pdf", ".doc", ".jpg", ".jpeg", ".png", ".xlsx", ".xls"],
        max_size_bytes=50 * 1024 * 1024,
    )

    material = FinalizedMaterial.objects.create(
        contract=contract,
        file_path=saved.legacy_file_path,
        storage_root_type=saved.root_type,
        subdir_path=saved.subdir_path,
        relative_file_path=saved.relative_file_path,
        original_filename=saved.original_filename,
        category=MaterialCategory.CASE_MATERIAL,
        archive_item_code=archive_item_code,
    )

    logger.info(
        "案件材料已同步到归档: %s -> %s",
        original_filename,
        archive_item_code,
        extra={
            "contract_id": contract.id,
            "case_material_id": case_material.id,
            "material_id": material.id,
        },
    )
    return material


def _apply_initial_order_for_synced(synced: list[dict[str, Any]]) -> None:
    """同步完成后，按排序规则设置归档子项初始顺序。"""
    if not synced:
        return

    materials_by_id = {
        m.pk: m for m in FinalizedMaterial.objects.filter(pk__in=[item["material_id"] for item in synced])
    }

    code_to_materials: dict[str, list[FinalizedMaterial]] = {}
    for item in synced:
        material = materials_by_id.get(item["material_id"])
        if material:
            code_to_materials.setdefault(item["archive_item_code"], []).append(material)

    to_update: list[FinalizedMaterial] = []
    for code, materials in code_to_materials.items():
        keywords = ARCHIVE_SUBITEM_ORDER_RULES.get(code)
        if not keywords or len(materials) <= 1:
            continue

        def _sort_key(mat: FinalizedMaterial, _keywords: tuple[str, ...] = tuple(keywords)) -> tuple[int, int]:  # type: ignore[arg-type]
            for i, keyword in enumerate(_keywords):
                if keyword in mat.original_filename:
                    return (0, i)
            return (1, 0)

        materials.sort(key=_sort_key)

        for i, material in enumerate(materials, start=1):
            material.order = i
            to_update.append(material)

        logger.info(
            "同步材料设置初始排序: code=%s, order=%s",
            code,
            [(m.original_filename, m.order) for m in materials],
        )

    if to_update:
        FinalizedMaterial.objects.bulk_update(to_update, ["order"])
