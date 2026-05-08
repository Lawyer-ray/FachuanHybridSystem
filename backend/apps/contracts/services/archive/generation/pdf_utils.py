"""PDF 工具：A4 缩放、页码、PDF 合并。"""

from __future__ import annotations

import contextlib
import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial

from ..category_mapping import get_archive_category
from ..constants import ARCHIVE_CHECKLIST, ARCHIVE_SKIP_CODES, ARCHIVE_SKIP_TEMPLATES

logger = logging.getLogger("apps.contracts.archive")

A4_W, A4_H = 595.0, 842.0
TOLERANCE = 1.0


def scale_pages_to_a4(contract: Contract) -> dict[str, Any]:
    """将合同所有已上传的归档 PDF 材料按 A4 尺寸缩放。"""
    import fitz

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

            out_doc = fitz.open()

            for page in src_doc:
                page_w, page_h = page.rect.width, page.rect.height
                is_a4 = (
                    abs(page_w - A4_W) < TOLERANCE and abs(page_h - A4_H) < TOLERANCE
                ) or (
                    abs(page_w - A4_H) < TOLERANCE and abs(page_h - A4_W) < TOLERANCE
                )

                if is_a4:
                    out_doc.insert_pdf(src_doc, from_page=page.number, to_page=page.number)
                else:
                    if page_w > page_h:
                        target_w, target_h = A4_H, A4_W
                    else:
                        target_w, target_h = A4_W, A4_H

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


def add_page_numbers(doc: Any, start_page: int = 1) -> None:
    """为PDF文档的每一页添加页码（居中底部）。"""
    import fitz

    for i, page in enumerate(doc):
        page_num = start_page + i
        rect = page.rect
        point = fitz.Point(rect.width / 2, rect.height - 30)
        font = fitz.Font("helv")
        page.insert_text(
            point,
            str(page_num),
            fontname="helv",
            fontsize=9,
            color=(0, 0, 0),
        )


def merge_materials_to_single_pdf(materials: list[FinalizedMaterial]) -> dict[str, Any]:
    """将多个材料文件合并为一个 PDF（通用工具方法）。"""
    import fitz
    from django.conf import settings as django_settings

    merged_doc = fitz.open()

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
            return {"success": False, "error": "没有可合并的文件"}

        buffer = BytesIO()
        merged_doc.save(buffer)
        content = buffer.getvalue()

        return {"success": True, "content": content}
    finally:
        merged_doc.close()


def compile_case_materials_pdf(
    contract: Contract,
    archive_dir: Path,
) -> dict[str, Any]:
    """将归档检查清单中非1-3号的已上传材料合并为"4-案卷材料.pdf"。

    Returns:
        {"written": bool, "page_count": int, "skipped": bool, "error": str|None}
    """
    import fitz

    from apps.contracts.services.archive import ArchiveChecklistService

    checklist_service = ArchiveChecklistService()
    checklist = checklist_service.get_checklist_with_status(contract)
    checklist_items = checklist.get("items", [])

    materials_to_merge: list[FinalizedMaterial] = []
    seen_ids: set[int] = set()

    for item in checklist_items:
        code = item.get("code", "")
        template = item.get("template")

        if code in ARCHIVE_SKIP_CODES or template in ARCHIVE_SKIP_TEMPLATES:
            continue

        material_ids = item.get("material_ids", [])
        if not material_ids:
            continue

        id_to_material: dict[int, FinalizedMaterial] = {
            m.id: m
            for m in FinalizedMaterial.objects.filter(id__in=material_ids)
        }
        for mid in material_ids:
            m = id_to_material.get(mid)
            if m and m.id not in seen_ids:
                seen_ids.add(m.id)
                materials_to_merge.append(m)

    if not materials_to_merge:
        return {"written": False, "skipped": True, "page_count": 0, "error": None}

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

        add_page_numbers(merged_doc)

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
