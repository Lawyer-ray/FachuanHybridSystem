"""办案服务质量监督卡自动检测与提取。"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial, MaterialCategory
from apps.contracts.services.contract.integrations.material_service import MaterialService

logger = logging.getLogger("apps.contracts.archive")

_SUPERVISION_CARD_KEYWORDS: tuple[str, ...] = (
    "监督卡",
    "服务质量",
    "办案质量",
    "服务质量监督卡",
    "办案服务质量监督卡",
)


class SupervisionCardExtractor:
    """办案服务质量监督卡自动检测与提取服务。"""

    def __init__(self, material_service: MaterialService | None = None) -> None:
        self._material_service = material_service or MaterialService()

    def detect_and_extract(self, contract: Contract) -> dict[str, Any]:
        """检测合同原件 PDF 末尾是否包含监督卡，并在命中后提取为归档材料。"""
        pdf_materials = list(
            FinalizedMaterial.objects.filter(
                contract=contract,
                category=MaterialCategory.CONTRACT_ORIGINAL,
            ).order_by("order", "-uploaded_at")
        )

        if not pdf_materials:
            return {"found": False, "page_number": None, "material_id": None, "error": "未找到合同正本 PDF"}

        for material in pdf_materials:
            resolved = self._material_service.resolve_material_file(material)
            if not resolved.exists or not resolved.abs_path:
                continue

            full_path = Path(resolved.abs_path)
            if full_path.suffix.lower() != ".pdf":
                continue

            try:
                result = self._check_pdf_for_supervision_card(full_path)
                if not result["found"]:
                    continue

                extracted_pdf = self._extract_page(full_path, result["page_number"])
                if not extracted_pdf:
                    continue

                extracted_material = self._save_extracted_card(
                    contract=contract,
                    pdf_content=extracted_pdf,
                    original_material=material,
                    page_number=result["page_number"],
                )
                return {
                    "found": True,
                    "page_number": result["page_number"],
                    "material_id": extracted_material.id if extracted_material else None,
                    "error": None,
                }
            except Exception as e:
                logger.warning("检测监督卡失败: %s", e, extra={"file_path": str(full_path)})

        return {"found": False, "page_number": None, "material_id": None, "error": "未在合同 PDF 末尾检测到监督卡"}

    def _check_pdf_for_supervision_card(self, pdf_path: Path) -> dict[str, Any]:
        import fitz

        doc = fitz.open(str(pdf_path))
        try:
            total_pages = len(doc)
            if total_pages == 0:
                return {"found": False, "page_number": None}

            pages_to_check = [total_pages - 2, total_pages - 1] if total_pages >= 2 else [total_pages - 1]
            for page_idx in pages_to_check:
                ocr_text = self._ocr_page(doc[page_idx])
                if ocr_text and any(keyword in ocr_text for keyword in _SUPERVISION_CARD_KEYWORDS):
                    return {"found": True, "page_number": page_idx + 1}
            return {"found": False, "page_number": None}
        finally:
            doc.close()

    def _ocr_page(self, page: Any) -> str:
        try:
            from apps.automation.services.ocr.ocr_service import OCRService

            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes(output="png")
            return OCRService().recognize_bytes(img_bytes)
        except Exception as e:
            logger.warning("OCR 检测失败: %s", e)
            return ""

    def _extract_page(self, pdf_path: Path, page_number: int) -> bytes | None:
        import fitz

        doc = fitz.open(str(pdf_path))
        try:
            if page_number < 1 or page_number > len(doc):
                return None

            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=page_number - 1, to_page=page_number - 1)
            buffer = BytesIO()
            new_doc.save(buffer)
            new_doc.close()
            return buffer.getvalue()
        except Exception:
            logger.exception("提取 PDF 页面失败: page=%d", page_number)
            return None
        finally:
            doc.close()

    def _save_extracted_card(
        self,
        contract: Contract,
        pdf_content: bytes,
        original_material: FinalizedMaterial,
        page_number: int,
    ) -> FinalizedMaterial | None:
        from django.core.files.base import ContentFile

        try:
            from .category_mapping import get_archive_category
            from .constants import ARCHIVE_CHECKLIST

            archive_category = get_archive_category(contract.case_type)
            checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

            supervision_code = ""
            for item in checklist_items:
                if item.get("auto_detect") == "supervision_card":
                    supervision_code = item["code"]
                    break

            filename = f"办案服务质量监督卡_{original_material.original_filename}_第{page_number}页.pdf"
            saved = self._material_service.save_business_material_file(
                uploaded_file=ContentFile(pdf_content, name=filename),
                contract_id=contract.id,
                target_subdir="监督卡",
                allowed_extensions=[".pdf"],
                max_size_bytes=20 * 1024 * 1024,
            )

            existing = FinalizedMaterial.objects.filter(
                contract=contract,
                archive_item_code=supervision_code,
            ).first()

            if existing:
                existing.file_path = saved.legacy_file_path
                existing.storage_root_type = saved.root_type
                existing.subdir_path = saved.subdir_path
                existing.relative_file_path = saved.relative_file_path
                existing.original_filename = filename
                existing.save(
                    update_fields=[
                        "file_path",
                        "storage_root_type",
                        "subdir_path",
                        "relative_file_path",
                        "original_filename",
                    ]
                )
                return existing

            return FinalizedMaterial.objects.create(
                contract=contract,
                file_path=saved.legacy_file_path,
                storage_root_type=saved.root_type,
                subdir_path=saved.subdir_path,
                relative_file_path=saved.relative_file_path,
                original_filename=filename,
                category=MaterialCategory.SUPERVISION_CARD,
                archive_item_code=supervision_code,
            )
        except Exception:
            logger.exception("保存监督卡材料失败")
            return None
