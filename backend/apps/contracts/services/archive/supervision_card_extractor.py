"""办案服务质量监督卡自动检测与剥离服务

从合同PDF最后2页中通过 OCR 识别 + 关键词匹配检测监督卡页面，
匹配成功则提取该页为独立PDF并自动创建 FinalizedMaterial 记录。
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial, MaterialCategory

logger = logging.getLogger("apps.contracts.archive")

# 监督卡检测关键词
_SUPERVISION_CARD_KEYWORDS: tuple[str, ...] = (
    "监督卡",
    "服务质量",
    "办案质量",
    "服务质量监督卡",
    "办案服务质量监督卡",
)


class SupervisionCardExtractor:
    """办案服务质量监督卡自动检测与剥离服务"""

    def detect_and_extract(self, contract: Contract) -> dict[str, Any]:
        """
        检测合同PDF最后2页是否包含监督卡，如果找到则提取。

        Args:
            contract: 合同实例

        Returns:
            {
                "found": bool,
                "page_number": int | None,
                "material_id": int | None,
                "error": str | None,
            }
        """
        # 1. 查找合同关联的 PDF 文件
        pdf_materials = list(
            FinalizedMaterial.objects.filter(
                contract=contract,
                category=MaterialCategory.CONTRACT_ORIGINAL,
            ).order_by("order", "-uploaded_at")
        )

        if not pdf_materials:
            return {"found": False, "page_number": None, "material_id": None, "error": "未找到合同正本PDF"}

        # 2. 逐个检查PDF文件的最后2页
        for material in pdf_materials:
            file_path = material.file_path
            if not file_path:
                continue

            # 构建完整路径
            full_path = self._resolve_file_path(file_path)
            if not full_path or not full_path.exists():
                continue

            if not str(full_path).lower().endswith(".pdf"):
                continue

            try:
                result = self._check_pdf_for_supervision_card(full_path)
                if result["found"]:
                    # 3. 提取监督卡页面
                    extracted_pdf = self._extract_page(full_path, result["page_number"])
                    if extracted_pdf:
                        # 4. 保存为新的 FinalizedMaterial
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
                continue

        return {"found": False, "page_number": None, "material_id": None, "error": "未在合同PDF末尾检测到监督卡"}

    def _check_pdf_for_supervision_card(self, pdf_path: Path) -> dict[str, Any]:
        """
        检查PDF最后2页是否包含监督卡关键词（使用OCR识别）。

        Returns:
            {"found": bool, "page_number": int | None}
        """
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        try:
            total_pages = len(doc)
            if total_pages == 0:
                return {"found": False, "page_number": None}

            # 只检查最后2页
            pages_to_check: list[int] = []
            if total_pages >= 2:
                pages_to_check = [total_pages - 2, total_pages - 1]
            else:
                pages_to_check = [total_pages - 1]

            for page_idx in pages_to_check:
                page = doc[page_idx]
                ocr_text = self._ocr_page(page)
                if ocr_text:
                    for keyword in _SUPERVISION_CARD_KEYWORDS:
                        if keyword in ocr_text:
                            return {"found": True, "page_number": page_idx + 1}  # 1-based

            return {"found": False, "page_number": None}
        finally:
            doc.close()

    def _ocr_page(self, page: Any) -> str:
        """
        对 PDF 页面执行 OCR 并返回识别文本。

        Args:
            page: fitz.Page 对象

        Returns:
            OCR 识别的文本内容，失败返回空字符串
        """
        try:
            import numpy as np
            from rapidocr import RapidOCR

            # 将页面渲染为图片（150 DPI 足够 OCR）
            pix = page.get_pixmap(dpi=150)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

            ocr = RapidOCR()
            result = ocr(img_array)

            if result and result.txts:
                return " ".join(result.txts)

            return ""
        except Exception as e:
            logger.warning("OCR 检测失败: %s", e)
            return ""

    def _extract_page(self, pdf_path: Path, page_number: int) -> bytes | None:
        """
        从PDF中提取指定页面为独立PDF。

        Args:
            pdf_path: PDF文件路径
            page_number: 1-based 页码

        Returns:
            提取的PDF内容 (bytes)
        """
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
        except Exception as e:
            logger.exception("提取PDF页面失败: page=%d", page_number)
            return None
        finally:
            doc.close()

    def _resolve_file_path(self, file_path: str) -> Path | None:
        """
        解析文件路径为绝对路径。

        Args:
            file_path: 相对或绝对文件路径

        Returns:
            绝对路径，无法解析返回 None
        """
        path = Path(file_path)
        if path.is_absolute() and path.exists():
            return path

        # 尝试从 MEDIA_ROOT 解析
        from django.conf import settings

        media_root = getattr(settings, "MEDIA_ROOT", None)
        if media_root:
            full_path = Path(media_root) / file_path
            if full_path.exists():
                return full_path

        return None

    def _save_extracted_card(
        self,
        contract: Contract,
        pdf_content: bytes,
        original_material: FinalizedMaterial,
        page_number: int,
    ) -> FinalizedMaterial | None:
        """
        保存提取的监督卡为新的 FinalizedMaterial 记录。

        Args:
            contract: 合同实例
            pdf_content: 提取的PDF内容
            original_material: 原始材料实例
            page_number: 提取的页码

        Returns:
            保存后的 FinalizedMaterial 实例
        """
        from django.core.files.base import ContentFile

        try:
            # 确定归档清单编号 - 根据归档分类映射
            from .category_mapping import get_archive_category
            from .constants import ARCHIVE_CHECKLIST

            archive_category = get_archive_category(contract.case_type)
            checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

            # 找到监督卡的 code
            supervision_code = ""
            for item in checklist_items:
                if item.get("auto_detect") == "supervision_card":
                    supervision_code = item["code"]
                    break

            filename = f"办案服务质量监督卡_{original_material.original_filename}_第{page_number}页.pdf"

            # 检查是否已有同编号的材料
            existing = FinalizedMaterial.objects.filter(
                contract=contract,
                archive_item_code=supervision_code,
            ).first()

            from apps.core.services import storage_service as storage

            rel_path, _ = storage.save_uploaded_file(
                uploaded_file=ContentFile(pdf_content, name=filename),
                rel_dir=f"contracts/finalized/{contract.id}",
                allowed_extensions=[".pdf"],
                max_size_bytes=20 * 1024 * 1024,
            )

            if existing:
                existing.file_path = rel_path
                existing.original_filename = filename
                existing.save(update_fields=["file_path", "original_filename"])
                return existing
            else:
                material = FinalizedMaterial.objects.create(
                    contract=contract,
                    file_path=rel_path,
                    original_filename=filename,
                    category=MaterialCategory.SUPERVISION_CARD,
                    archive_item_code=supervision_code,
                )
                return material

        except Exception as e:
            logger.exception("保存监督卡材料失败")
            return None
