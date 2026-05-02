"""归档材料下载 + 材料排序。"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial, MaterialCategory

from ..category_mapping import get_archive_category
from ..constants import ARCHIVE_CHECKLIST, ARCHIVE_SUBITEM_ORDER_RULES, ChecklistItem
from .document_generator import generate_single_archive_document

logger = logging.getLogger("apps.contracts.archive")


def download_archive_item(
    contract: Contract,
    archive_item_code: str,
) -> dict[str, Any]:
    """下载归档检查项对应的材料文件。

    模板类型项始终重新生成以确保与预览一致。
    非模板类型项直接返回已有文件。
    """
    checklist_item = _find_checklist_item(contract, archive_item_code)
    if checklist_item and checklist_item.get("template"):
        return _download_template_item(contract, archive_item_code, checklist_item)

    return _download_uploaded_item(contract, archive_item_code)


def _find_checklist_item(contract: Contract, archive_item_code: str) -> ChecklistItem | None:
    """查找检查清单中指定编号的项。"""
    archive_category = get_archive_category(contract.case_type)
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    for item in checklist_items:
        if item["code"] == archive_item_code:
            return item
    return None


def _download_template_item(
    contract: Contract,
    archive_item_code: str,
    checklist_item: ChecklistItem,
) -> dict[str, Any]:
    """下载模板类型的归档项 — 始终重新生成以确保与预览一致。"""
    gen_result = generate_single_archive_document(contract, archive_item_code)
    if gen_result.get("error"):
        return {"error": gen_result["error"]}

    content = gen_result.get("content")
    filename = gen_result.get("filename", "")
    if content:
        return {
            "content": content,
            "filename": filename,
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

    return {"error": "生成失败：无文件内容"}


def _download_uploaded_item(
    contract: Contract,
    archive_item_code: str,
) -> dict[str, Any]:
    """下载非模板类型的归档项（已上传的材料文件）。"""
    materials = list(
        FinalizedMaterial.objects.filter(
            contract=contract,
            archive_item_code=archive_item_code,
        ).order_by("order", "-uploaded_at")
    )

    if not materials:
        if "委托" in archive_item_code or _is_item_by_name(contract, archive_item_code, "委托"):
            materials = list(
                FinalizedMaterial.objects.filter(
                    contract=contract,
                    category__in=(MaterialCategory.CONTRACT_ORIGINAL, MaterialCategory.SUPPLEMENTARY_AGREEMENT),
                ).order_by("order", "-uploaded_at")
            )

        if not materials and _is_item_by_name(contract, archive_item_code, "收费"):
            materials = list(
                FinalizedMaterial.objects.filter(
                    contract=contract,
                    category=MaterialCategory.INVOICE,
                ).order_by("order", "-uploaded_at")
            )

        if not materials and _is_item_by_name(contract, archive_item_code, "授权"):
            materials = list(
                FinalizedMaterial.objects.filter(
                    contract=contract,
                    category=MaterialCategory.AUTHORIZATION_MATERIAL,
                ).order_by("order", "-uploaded_at")
            )

    materials = _apply_subitem_sort(materials, archive_item_code)

    if not materials:
        return {"error": "未找到对应的归档材料"}

    if len(materials) == 1:
        return _read_material_file(materials[0])

    return _merge_materials_to_pdf(materials, archive_item_code)


def _apply_subitem_sort(
    materials: list[FinalizedMaterial],
    archive_item_code: str,
) -> list[FinalizedMaterial]:
    """对有排序规则的清单项，按关键词顺序重排 order=0 的材料。"""
    keywords = ARCHIVE_SUBITEM_ORDER_RULES.get(archive_item_code)
    if not keywords or len(materials) <= 1:
        return materials

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


def _is_item_by_name(contract: Contract, archive_item_code: str, name_keyword: str) -> bool:
    """判断 archive_item_code 对应的检查项名称是否包含指定关键词。"""
    archive_category = get_archive_category(contract.case_type)
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
    for item in checklist_items:
        if item["code"] == archive_item_code and name_keyword in item.get("name", ""):
            return True
    return False


def _read_material_file(material: FinalizedMaterial) -> dict[str, Any]:
    """读取单个材料文件的内容。"""
    from django.conf import settings as django_settings

    file_path = Path(material.file_path)
    if not file_path.is_absolute():
        file_path = Path(django_settings.MEDIA_ROOT) / file_path

    if not file_path.exists():
        return {"error": f"文件不存在: {material.original_filename}"}

    content = file_path.read_bytes()
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
    materials: list[FinalizedMaterial],
    archive_item_code: str,
) -> dict[str, Any]:
    """将多个材料文件合并为一个 PDF。"""
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

        buffer = BytesIO()
        merged_doc.save(buffer)
        content = buffer.getvalue()

        from ..category_mapping import get_archive_category
        from ..constants import ARCHIVE_CHECKLIST

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
