"""证据 OCR 提取与全文搜索服务"""

from __future__ import annotations

import io
import logging
from typing import Any

from django.db.models import Q, QuerySet

logger = logging.getLogger("apps.evidence")


class EvidenceOCRService:
    """从证据文件提取 OCR 文本并保存"""

    def extract_and_save(self, item_id: int) -> None:
        from apps.evidence.models import EvidenceItem

        try:
            item = EvidenceItem.objects.get(pk=item_id)
        except EvidenceItem.DoesNotExist:
            logger.warning("OCR: 证据项不存在 %s", item_id)
            return

        if not item.file:
            return

        text = self._extract_text(item)
        if text:
            EvidenceItem.objects.filter(pk=item_id).update(ocr_text=text)
            logger.info("OCR 完成: item=%s, len=%s", item_id, len(text))

    def _extract_text(self, item: Any) -> str:
        """从文件提取文本，PDF 逐页转图片后 OCR，图片直接 OCR"""
        from apps.core.path import Path

        ext = Path(item.file_name).suffix.lower() if item.file_name else ""

        if ext == ".pdf":
            return self._extract_from_pdf(item.file)
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp"}:
            return self._extract_from_image(item.file)
        return ""

    def _extract_from_pdf(self, file_field: Any) -> str:
        """PDF 逐页转图片后 OCR"""
        try:
            import fitz

            file_field.seek(0)
            data = file_field.read()
            file_field.seek(0)

            doc = fitz.open(stream=data, filetype="pdf")
            texts: list[str] = []
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                text = self._ocr_image_bytes(img_bytes)
                if text:
                    texts.append(text)
            doc.close()
            return "\n".join(texts)
        except Exception:
            logger.exception("PDF OCR 失败")
            return ""

    def _extract_from_image(self, file_field: Any) -> str:
        """图片直接 OCR"""
        try:
            file_field.seek(0)
            data = file_field.read()
            file_field.seek(0)
            return self._ocr_image_bytes(data)
        except Exception:
            logger.exception("图片 OCR 失败")
            return ""

    @staticmethod
    def _ocr_image_bytes(image_bytes: bytes) -> str:
        from apps.core.interfaces import ServiceLocator

        ocr_svc = ServiceLocator.get_ocr_service()
        result = ocr_svc.extract_text(image_bytes)
        return result.text if hasattr(result, "text") else str(result)


class EvidenceSearchService:
    """证据全文搜索"""

    def search(self, *, case_id: int, query: str) -> QuerySet[Any]:
        """在案件的所有证据中搜索"""
        from apps.evidence.models import EvidenceItem

        return EvidenceItem.objects.filter(
            evidence_list__case_id=case_id,
        ).filter(
            Q(name__icontains=query)
            | Q(purpose__icontains=query)
            | Q(ocr_text__icontains=query)
        ).select_related("evidence_list").order_by("evidence_list__order", "order")
