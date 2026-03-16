"""图片自动旋转 API"""

from __future__ import annotations

import base64
import json
import logging
from types import SimpleNamespace
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings

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
@rate_limit_from_settings("UPLOAD", by_user=True)
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
    pdf_service = _get_pdf_service()
    results = []
    for img in images:
        try:
            data: str = img.get("data", "")
            if "," in data:
                data = data.split(",", 1)[1]
            import base64 as _b64

            image_bytes = _b64.b64decode(data)
            result: dict[str, Any] = pdf_service.orientation_service.detect_orientation_with_text(image_bytes)
            result["filename"] = img.get("filename", "")
            results.append(result)
        except Exception as exc:
            logger.error("detect_orientation 失败: %s", exc, exc_info=True)
            results.append({"filename": img.get("filename", ""), "rotation": 0, "confidence": 0, "ocr_text": ""})
    return {"success": True, "results": results}


@router.post("/suggest-rename")
@rate_limit_from_settings("LLM", by_user=True)
def suggest_rename(request: HttpRequest) -> dict[str, Any]:
    payload = _body(request)
    items: list[dict[str, Any]] = payload.get("items", [])
    if not items:
        return {"success": True, "suggestions": []}
    try:
        service = _get_rename_service()
        requests = []
        for i in items:
            ns = SimpleNamespace(
                filename=i["filename"],
                ocr_text=i.get("ocr_text", ""),
            )
            # 可选的高精度 OCR 参数
            image_data_b64: str = i.get("image_data", "")
            if image_data_b64:
                try:
                    ns.image_data = base64.b64decode(image_data_b64)
                    ns.rotation = int(i.get("rotation", 0))
                except Exception:
                    logger.warning("image_data Base64 解码失败: %s", i.get("filename", ""))
            requests.append(ns)
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
@rate_limit_from_settings("EXPORT", by_user=True)
def export_pdf(request: HttpRequest) -> dict[str, Any]:
    content_type = request.content_type or ""

    if "multipart/form-data" in content_type:
        return _handle_multipart_export_pdf(request)
    else:
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


def _handle_multipart_export_pdf(request: HttpRequest) -> dict[str, Any]:
    """处理 multipart/form-data 格式的 PDF 导出请求"""
    try:
        paper_size = request.POST.get("paper_size", "original")

        pages = []
        for key in request.FILES:
            if key.startswith("page_"):
                idx = key.split("_")[1]
                file_obj = request.FILES[key]
                filename = request.POST.get(f"filename_{idx}", file_obj.name)

                image_data = base64.b64encode(file_obj.read()).decode("utf-8")
                pages.append(
                    {
                        "filename": filename,
                        "data": image_data,
                        "rotation": 0,
                    }
                )

        if not pages:
            return {"success": False, "message": "没有页面数据"}

        return _get_rotation_service().export_as_pdf(pages, paper_size)
    except Exception as exc:
        logger.error("multipart export-pdf 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.post("/export")
@rate_limit_from_settings("EXPORT", by_user=True)
def export_images(request: HttpRequest) -> dict[str, Any]:
    content_type = request.content_type or ""

    if "multipart/form-data" in content_type:
        return _handle_multipart_export(request)
    else:
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


def _handle_multipart_export(request: HttpRequest) -> dict[str, Any]:
    """处理 multipart/form-data 格式的导出请求"""
    try:
        paper_size = request.POST.get("paper_size", "original")
        rename_map_json = request.POST.get("rename_map")
        rename_map = json.loads(rename_map_json) if rename_map_json else None

        images = []
        for key in request.FILES:
            if key.startswith("image_"):
                idx = key.split("_")[1]
                file_obj = request.FILES[key]
                filename = request.POST.get(f"filename_{idx}", file_obj.name)
                format_type = request.POST.get(f"format_{idx}", "jpeg")

                image_data = base64.b64encode(file_obj.read()).decode("utf-8")
                images.append(
                    {
                        "filename": filename,
                        "data": image_data,
                        "format": format_type,
                    }
                )

        if not images:
            return {"success": False, "message": "没有图片数据"}

        return _get_rotation_service().export_images(images, paper_size, rename_map)
    except Exception as exc:
        logger.error("multipart 导出失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}
