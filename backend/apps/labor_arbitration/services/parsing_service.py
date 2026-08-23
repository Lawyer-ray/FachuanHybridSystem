"""调用文档解析服务（document_parsing）对仲裁文书图片做 OCR。"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from apps.document_parsing.services import get_document_parser
from apps.labor_arbitration.models import ArbitrationDocument, ParseStatus

logger = logging.getLogger(__name__)


def parse_arbitration_document(doc: ArbitrationDocument, backend: str) -> dict[str, Any]:
    """逐页解析文书图片，拼接文本与 Markdown，写回模型。

    Args:
        doc: 目标仲裁文书（需已爬取到图片）。
        backend: 解析后端（local / mineru / textin / auto）。

    Returns:
        解析结果字典，含 success / doc_id / pages / error。
    """
    doc.parse_status = ParseStatus.PROCESSING
    doc.parse_backend = backend
    doc.parse_error = ""
    doc.save(update_fields=["parse_status", "parse_backend", "parse_error"])

    texts: list[str] = []
    marks: list[str] = []
    try:
        images = list(doc.images.order_by("page_index"))
        if not images:
            raise RuntimeError("该文书还没有爬取到的图片，无法解析")

        parser = get_document_parser(backend=backend)
        for img in images:
            local_path = img.image.path
            ext = local_path.rsplit(".", 1)[-1].lower() if "." in local_path else "png"
            result = parser.parse_document(
                file_path=local_path,
                file_type=ext,
                extract_tables=True,
                extract_images=False,
                return_markdown=True,
            )
            texts.append(result.text or "")
            marks.append(result.markdown or "")

        doc.parsed_text = "\n\n".join(texts)
        doc.parsed_markdown = "\n\n".join(marks)
        doc.parse_status = ParseStatus.DONE
        doc.parsed_at = timezone.now()
        doc.save(update_fields=["parsed_text", "parsed_markdown", "parse_status", "parsed_at"])
        logger.info("[劳动仲裁] 文档 %s 解析完成，共 %d 页", doc.id, len(images))
        return {"success": True, "doc_id": doc.id, "pages": len(images)}
    except Exception as exc:
        logger.error("[劳动仲裁] 解析文档 %s 失败: %s", doc.id, exc, exc_info=True)
        doc.parse_status = ParseStatus.FAILED
        doc.parse_error = str(exc)[:2000]
        doc.save(update_fields=["parse_status", "parse_error"])
        return {"success": False, "doc_id": doc.id, "error": str(exc)}
