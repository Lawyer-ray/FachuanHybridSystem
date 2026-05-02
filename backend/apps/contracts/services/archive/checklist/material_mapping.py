"""材料映射逻辑：合同材料、授权委托材料、监督卡材料到检查清单的映射。"""

from __future__ import annotations

import logging
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial, MaterialCategory

from ..constants import ARCHIVE_CHECKLIST, CASE_MATERIAL_KEYWORD_MAPPING

logger = logging.getLogger("apps.contracts.archive")


def map_contract_materials(
    archive_category: str,
    materials: list[FinalizedMaterial],
) -> dict[str, list[int]]:
    """将 MaterialCategory (合同正本/补充协议/发票) 映射到检查清单编号。"""
    from .checklist_query import find_code_by_name, find_code_by_source

    result: dict[str, list[int]] = {}

    contract_code = find_code_by_source(archive_category, "contract")
    invoice_code = find_code_by_name(archive_category, "收费凭证")

    for m in materials:
        if m.archive_item_code:
            continue

        if m.category in (MaterialCategory.CONTRACT_ORIGINAL, MaterialCategory.SUPPLEMENTARY_AGREEMENT) and contract_code:
            result.setdefault(contract_code, []).append(m.id)
        elif m.category == MaterialCategory.INVOICE and invoice_code:
            result.setdefault(invoice_code, []).append(m.id)

    return result


def map_case_authorization_materials(
    contract: Contract,
    archive_category: str,
    materials: list[FinalizedMaterial],
) -> dict[str, list[int]]:
    """从关联合同案件中提取授权委托材料，映射到检查清单编号。"""
    from .checklist_query import find_code_by_name

    result: dict[str, list[int]] = {}

    auth_code = find_code_by_name(archive_category, "授权委托")
    if not auth_code:
        return result

    for m in materials:
        if m.archive_item_code:
            continue
        if m.category == MaterialCategory.AUTHORIZATION_MATERIAL:
            result.setdefault(auth_code, []).append(m.id)

    try:
        from apps.cases.models import CaseMaterial

        for case in contract.cases.all():
            if CaseMaterial.objects.filter(case=case, type_name__contains="授权").exists():
                logger.info(
                    "案件 %s 存在授权委托材料，可提取到归档",
                    case.id,
                    extra={"contract_id": contract.id},
                )
                break
    except Exception as e:
        logger.warning("检查案件授权委托材料失败: %s", e)

    return result


def map_supervision_card_materials(
    archive_category: str,
    materials: list[FinalizedMaterial],
) -> dict[str, list[int]]:
    """将没有 archive_item_code 的监督卡材料映射到检查清单编号。"""
    result: dict[str, list[int]] = {}

    supervision_code = ""
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    for item in checklist_items:
        if item.get("auto_detect") == "supervision_card":
            supervision_code = item["code"]
            break

    if not supervision_code:
        return result

    for m in materials:
        if m.archive_item_code:
            continue
        if m.category == MaterialCategory.SUPERVISION_CARD:
            result.setdefault(supervision_code, []).append(m.id)

    return result


def find_case_material_match_codes(
    contract: Contract,
    archive_category: str,
) -> set[str]:
    """查找合同关联案件中有匹配 CaseMaterial 的清单项 code 集合。"""
    keyword_map = CASE_MATERIAL_KEYWORD_MAPPING.get(archive_category, {})
    if not keyword_map:
        return set()

    try:
        from apps.cases.models import CaseMaterial

        type_names = list(
            CaseMaterial.objects.filter(
                case__in=contract.cases.all(),
            ).values_list("type_name", flat=True)
        )

        matched_codes: set[str] = set()
        for type_name in type_names:
            code = match_type_name_to_code(type_name, keyword_map)
            if code:
                matched_codes.add(code)
        return matched_codes
    except Exception as e:
        logger.warning("查询案件材料匹配失败: %s", e)
        return set()


def match_type_name_to_code(
    type_name: str,
    keyword_map: dict[str, list[str]],
) -> str | None:
    """根据 CaseMaterial.type_name 匹配 archive_item_code。"""
    if not type_name:
        return None
    for code, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword in type_name:
                return code
    return None


def fill_material_details_from_ids(
    code_to_material_details: dict[str, list[dict[str, Any]]],
    code_to_mat_ids: dict[str, list[int]],
    materials: list[FinalizedMaterial],
) -> None:
    """根据 material ID 列表，将材料详情填充到 code_to_material_details。"""
    from .checklist_query import _get_source_label

    mat_id_to_obj: dict[int, FinalizedMaterial] = {m.id: m for m in materials}
    for code, mat_ids in code_to_mat_ids.items():
        for mid in mat_ids:
            m = mat_id_to_obj.get(mid)
            if not m:
                continue
            existing_ids = {d["id"] for d in code_to_material_details.get(code, [])}
            if mid in existing_ids:
                continue
            code_to_material_details.setdefault(code, []).append({
                "id": m.id,
                "original_filename": m.original_filename,
                "category": m.category,
                "source_label": _get_source_label(m.category),
                "order": m.order,
                "file_path": m.file_path,
            })
