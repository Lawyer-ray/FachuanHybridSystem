"""图片自动旋转 API"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from django.http import HttpRequest
from ninja import Router

logger = logging.getLogger("apps.automation")

router = Router(tags=["图片旋转"])


def _body(request: HttpRequest) -> dict[str, Any]:
    return json.loads(request.body or b"{}")


def _get_pdf_service() -> Any:
    from apps.automation.services.image_rotation.pdf_extraction_service import PDFExtractionService
    return PDFExtractionService()


def _get_rotation_service() -> Any:
    from apps.automation.services.image_rotation.facade import ImageRotationService
    return ImageRotationService()


def _get_rename_service() -> Any:
    from apps.automation.services.image_rotation.auto_rename_service import AutoRenameService
    return AutoRenameService()


@router.post("/extract-pdf-fast")
def extract_pdf_fast(request: HttpRequest) -> dict[str, Any]:
    payload = _body(request)
    filename: str = payload.get("filename", "file.pdf")
    data: str = payload.get("data", "")
    if not data:
        return {"success": False, "message": "缺少 data 参数"}
    try:
        return _get_pdf_service().extract_pages(data, filename)
    except Exception as exc:
        logger.error("extract_pdf_fast 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.post("/detect-page-orientation")
def detect_page_orientation(request: HttpRequest) -> dict[str, Any]:
    payload = _body(request)
    data: str = payload.get("data", "")
    if not data:
        return {"rotation": 0, "confidence": 0}
    try:
        return _get_pdf_service().detect_single_page_orientation(data)
    except Exception as exc:
        logger.error("detect_page_orientation 失败: %s", exc, exc_info=True)
        return {"rotation": 0, "confidence": 0}


@router.post("/detect-orientation")
def detect_orientation(request: HttpRequest) -> dict[str, Any]:
    payload = _body(request)
    images: list[dict[str, Any]] = payload.get("images", [])
    if not images:
        return {"success": False, "results": []}
    service = _get_pdf_service()
    results = []
    for img in images:
        try:
            result: dict[str, Any] = service.detect_single_page_orientation(img.get("data", ""))
            result["filename"] = img.get("filename", "")
            results.append(result)
        except Exception as exc:
            logger.error("detect_orientation 失败: %s", exc, exc_info=True)
            results.append({"filename": img.get("filename", ""), "rotation": 0, "confidence": 0})
    return {"success": True, "results": results}


@router.post("/suggest-rename")
def suggest_rename(request: HttpRequest) -> dict[str, Any]:
    payload = _body(request)
    items: list[dict[str, Any]] = payload.get("items", [])
    if not items:
        return {"success": True, "suggestions": []}
    try:
        service = _get_rename_service()
        requests = [SimpleNamespace(filename=i["filename"], ocr_text=i.get("ocr_text", "")) for i in items]
        suggestions = service.suggest_rename_batch(requests)
        return {
            "success": True,
            "suggestions": [
                {
                    "original_filename": s.original_filename,
                    "suggested_filename": s.suggested_filename,
                    "date": s.date,
                    "amount": s.amount,
                    "success": s.success,
                }
                for s in suggestions
            ],
        }
    except Exception as exc:
        logger.error("suggest_rename 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc), "suggestions": []}


@router.post("/export-pdf")
def export_pdf(request: HttpRequest) -> dict[str, Any]:
    payload = _body(request)
    pages: list[dict[str, Any]] = payload.get("pages", [])
    paper_size: str = payload.get("paper_size", "original")
    if not pages:
        return {"success": False, "message": "没有页面数据"}
    try:
        return _get_rotation_service().export_as_pdf(pages, paper_size)
    except Exception as exc:
        logger.error("export_pdf 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.post("/export")
def export_images(request: HttpRequest) -> dict[str, Any]:
    payload = _body(request)
    images: list[dict[str, Any]] = payload.get("images", [])
    paper_size: str = payload.get("paper_size", "original")
    rename_map: dict[str, str] | None = payload.get("rename_map")
    if not images:
        return {"success": False, "message": "没有图片数据"}
    try:
        return _get_rotation_service().export_images(images, paper_size, rename_map)
    except Exception as exc:
        logger.error("export_images 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}
