"""归档检查清单查询 + 排序 + 工具方法。"""

from __future__ import annotations

import logging
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial, MaterialCategory

from ..category_mapping import ArchiveCategory, get_archive_category
from ..constants import ARCHIVE_CHECKLIST, ARCHIVE_SUBITEM_ORDER_RULES, ChecklistItem
from .material_mapping import (
    fill_material_details_from_ids,
    find_case_material_match_codes,
    map_case_authorization_materials,
    map_contract_materials,
    map_supervision_card_materials,
)

logger = logging.getLogger("apps.contracts.archive")


def get_checklist_with_status(contract: Contract) -> dict[str, Any]:
    """获取合同的归档检查清单及各项完成状态。"""
    archive_category = get_archive_category(contract.case_type)
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

    materials = list(
        FinalizedMaterial.objects.filter(contract=contract).only(
            "id", "archive_item_code", "category", "original_filename", "order", "file_path",
        ).order_by("order", "-uploaded_at")
    )

    code_to_materials: dict[str, list[int]] = {}
    for m in materials:
        if m.archive_item_code:
            code_to_materials.setdefault(m.archive_item_code, []).append(m.id)

    code_to_material_details: dict[str, list[dict[str, Any]]] = {}
    for m in materials:
        if m.archive_item_code:
            code_to_material_details.setdefault(m.archive_item_code, []).append({
                "id": m.id,
                "original_filename": m.original_filename,
                "category": m.category,
                "source_label": _get_source_label(m.category),
                "order": m.order,
                "file_path": m.file_path,
            })

    contract_category_codes = map_contract_materials(archive_category, materials)
    for code, mat_ids in contract_category_codes.items():
        code_to_materials.setdefault(code, []).extend(mat_ids)
    fill_material_details_from_ids(code_to_material_details, contract_category_codes, materials)

    case_material_codes = map_case_authorization_materials(contract, archive_category, materials)
    for code, mat_ids in case_material_codes.items():
        code_to_materials.setdefault(code, []).extend(mat_ids)
    fill_material_details_from_ids(code_to_material_details, case_material_codes, materials)

    supervision_codes = map_supervision_card_materials(archive_category, materials)
    for code, mat_ids in supervision_codes.items():
        code_to_materials.setdefault(code, []).extend(mat_ids)
    fill_material_details_from_ids(code_to_material_details, supervision_codes, materials)

    _apply_subitem_order(code_to_material_details)

    case_material_match_codes = find_case_material_match_codes(contract, archive_category)

    items_with_status: list[dict[str, Any]] = []
    for item in checklist_items:
        mat_ids = code_to_materials.get(item["code"], [])
        items_with_status.append({
            **item,
            "completed": len(mat_ids) > 0,
            "material_ids": mat_ids,
            "materials": code_to_material_details.get(item["code"], []),
            "has_case_material": item["source"] == "case" and item["code"] in case_material_match_codes,
        })

    non_template_items = [item for item in items_with_status if not item["template"]]

    if contract.compact_archive:
        effective_items = [item for item in non_template_items if item["completed"]]
    else:
        effective_items = non_template_items

    total_count = len(effective_items)
    completed_count = sum(1 for item in effective_items if item["completed"])
    required_items = [item for item in effective_items if item["required"]]
    required_total_count = len(required_items)
    required_completed_count = sum(1 for item in required_items if item["completed"])

    archive_category_label = ArchiveCategory(archive_category).label

    return {
        "archive_category": archive_category,
        "archive_category_label": archive_category_label,
        "compact_archive": contract.compact_archive,
        "items": items_with_status,
        "completed_count": completed_count,
        "total_count": total_count,
        "required_completed_count": required_completed_count,
        "required_total_count": required_total_count,
        "completion_percentage": round(completed_count / total_count * 100, 1) if total_count > 0 else 0,
    }


def get_template_items(archive_category: str) -> list[ChecklistItem]:
    """获取指定归档分类中需要模板生成的清单项。"""
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    return [item for item in checklist_items if item["template"] is not None]


def get_auto_detect_items(archive_category: str) -> list[ChecklistItem]:
    """获取指定归档分类中支持自动检测的清单项。"""
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    return [item for item in checklist_items if item["auto_detect"] is not None]


def find_code_by_source(archive_category: str, source: str) -> str | None:
    """根据 source 类型找到对应的检查清单 code。"""
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    for item in checklist_items:
        if item["source"] == source and "委托" in item["name"]:
            return item["code"]
    return None


def find_code_by_name(archive_category: str, name_keyword: str) -> str | None:
    """根据名称关键词找到对应的检查清单 code。"""
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    for item in checklist_items:
        if name_keyword in item["name"]:
            return item["code"]
    return None


def _apply_subitem_order(code_to_material_details: dict[str, list[dict[str, Any]]]) -> None:
    """对有排序规则的清单项，按关键词顺序重排子项（仅影响 order=0 的材料）。"""
    for code, keywords in ARCHIVE_SUBITEM_ORDER_RULES.items():
        details = code_to_material_details.get(code)
        if not details or len(details) <= 1:
            continue

        ordered_mats = [d for d in details if d.get("order", 0) > 0]
        unordered_mats = [d for d in details if d.get("order", 0) == 0]

        if not unordered_mats:
            continue

        def _sort_key(mat: dict[str, Any], _keywords: tuple[str, ...] = tuple(keywords)) -> tuple[int, int]:
            filename = mat.get("original_filename", "")
            for i, keyword in enumerate(_keywords):
                if keyword in filename:
                    return (0, i)
            return (1, 0)

        unordered_mats.sort(key=_sort_key)
        code_to_material_details[code] = ordered_mats + unordered_mats


def _get_source_label(category: str) -> str:
    """根据材料分类返回来源标签。"""
    label_map: dict[str, str] = {
        MaterialCategory.CONTRACT_ORIGINAL: "合同正本",
        MaterialCategory.SUPPLEMENTARY_AGREEMENT: "补充协议",
        MaterialCategory.INVOICE: "发票",
        MaterialCategory.ARCHIVE_DOCUMENT: "自动生成",
        MaterialCategory.SUPERVISION_CARD: "监督卡",
        MaterialCategory.AUTHORIZATION_MATERIAL: "授权委托",
        MaterialCategory.CASE_MATERIAL: "案件同步",
        MaterialCategory.ARCHIVE_UPLOAD: "手动上传",
    }
    return label_map.get(category, "手动上传")
