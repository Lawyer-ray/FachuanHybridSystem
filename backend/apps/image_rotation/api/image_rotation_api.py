"""图片自动旋转 API"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from types import SimpleNamespace
from typing import Any, cast

from asgiref.sync import sync_to_async
from apps.core.security.auth import JWTOrSessionAuth

from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger("apps.image_rotation")

router = Router(tags=["图片旋转"], auth=JWTOrSessionAuth())

_ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/tiff"})
_MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB

# Module-level semaphore to limit concurrent image processing threads
_IMAGE_SEM = asyncio.Semaphore(8)


def _validate_image_file(file_obj: UploadedFile) -> None:
    """验证上传的图片文件类型和大小。"""
    content_type = getattr(file_obj, "content_type", "") or ""
    if content_type not in _ALLOWED_IMAGE_TYPES:
        from apps.core.exceptions import ValidationException

        raise ValidationException(
            f"不支持的图片类型：{content_type}",
            code="INVALID_FILE_TYPE",
        )
    if file_obj.size and file_obj.size > _MAX_UPLOAD_SIZE:
        from apps.core.exceptions import ValidationException

        raise ValidationException(
            f"文件大小超过限制（最大 {_MAX_UPLOAD_SIZE // (1024 * 1024)}MB）",
            code="FILE_TOO_LARGE",
        )


def _body(request: HttpRequest) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(request.body or b"{}"))


def _decode_image_data(data: str) -> bytes:
    """从 Base64 字符串（可带 data URL 前缀）解码为字节数据。"""
    if "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


def _get_pdf_service() -> Any:
    from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService

    return PDFExtractionService()


def _get_rotation_service() -> Any:
    from apps.image_rotation.services.facade import ImageRotationService

    return ImageRotationService()


def _get_rename_service() -> Any:
    from apps.image_rotation.services.auto_rename_service import AutoRenameService

    return AutoRenameService()


@router.post("/extract-pdf-fast")
@rate_limit_from_settings("UPLOAD", by_user=True)
def extract_pdf_fast(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    payload = _body(request)
    filename: str = payload.get("filename", "file.pdf")
    data: str = payload.get("data", "")
    if not data:
        return {"success": False, "message": "缺少 data 参数"}
    try:
        return cast(dict[str, Any], _get_pdf_service().extract_pages(data, filename))
    except Exception as exc:
        logger.error("extract_pdf_fast 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.post("/detect-page-orientation")
def detect_page_orientation(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    payload = _body(request)
    data: str = payload.get("data", "")
    if not data:
        return {"rotation": 0, "confidence": 0}
    try:
        t0 = time.perf_counter()
        result = cast(dict[str, Any], _get_pdf_service().detect_single_page_orientation(data))
        result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return result
    except Exception as exc:
        logger.error("detect_page_orientation 失败: %s", exc, exc_info=True)
        return {"rotation": 0, "confidence": 0}


@router.post("/detect-orientation")
async def detect_orientation(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    payload = _body(request)
    images: list[dict[str, Any]] = payload.get("images", [])
    method: str = payload.get("method", "onnx")  # "onnx" | "ocr_voting"
    if not images:
        return {"success": False, "results": []}
    total_start = time.perf_counter()

    async def _process_image(img: dict[str, Any]) -> dict[str, Any]:
        async with _IMAGE_SEM:
            try:
                image_bytes = _decode_image_data(img.get("data", ""))
                t0 = time.perf_counter()
                if method == "ocr_voting":
                    from apps.image_rotation.services.orientation.service import OrientationDetectionService

                    result = await sync_to_async(
                        OrientationDetectionService().detect_orientation_with_text, thread_sensitive=False
                    )(image_bytes)
                else:
                    from apps.image_rotation.services.orientation.onnx_service import get_onnx_orientation_service

                    result = await sync_to_async(
                        get_onnx_orientation_service().detect_orientation, thread_sensitive=False
                    )(image_bytes)
                result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                result["filename"] = img.get("filename", "")
                return result
            except Exception as exc:
                logger.error("detect_orientation 失败: %s", exc, exc_info=True)
                return {
                    "filename": img.get("filename", ""),
                    "rotation": 0,
                    "confidence": 0,
                    "ocr_text": "",
                    "elapsed_ms": 0,
                }

    results = await asyncio.gather(*[_process_image(img) for img in images])
    total_elapsed_ms = round((time.perf_counter() - total_start) * 1000, 1)
    return {"success": True, "results": list(results), "total_elapsed_ms": total_elapsed_ms}


@router.post("/extract-text")
async def extract_text(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """提取图片文字（不检测方向），用于 OCR 重命名。"""
    payload = _body(request)
    images: list[dict[str, Any]] = payload.get("images", [])
    provider: str = payload.get("provider", "local")  # "local" | "paddleocr_api"
    if not images:
        return {"success": True, "results": []}
    from apps.automation.services.ocr.ocr_service import OCRService

    ocr = OCRService(use_v5=True, provider=provider)

    async def _extract_one(img: dict[str, Any]) -> dict[str, Any]:
        async with _IMAGE_SEM:
            try:
                image_bytes = _decode_image_data(img.get("data", ""))
                text_result = await sync_to_async(ocr.extract_text, thread_sensitive=False)(image_bytes)
                return {
                    "filename": img.get("filename", ""),
                    "ocr_text": text_result.text,
                    "raw_texts": text_result.raw_texts,
                }
            except Exception as exc:
                logger.error("extract_text 失败: %s", exc, exc_info=True)
                return {"filename": img.get("filename", ""), "ocr_text": "", "raw_texts": []}

    results = await asyncio.gather(*[_extract_one(img) for img in images])
    return {"success": True, "results": list(results)}


@router.post("/suggest-rename")
@rate_limit_from_settings("LLM", by_user=True)
async def suggest_rename(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
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
                except (TypeError, ValueError):
                    logger.warning("image_data Base64 解码失败: %s", i.get("filename", ""))
            requests.append(ns)
        suggestions = await sync_to_async(service.suggest_rename_batch, thread_sensitive=False)(requests)
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
def export_pdf(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
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
            return cast(dict[str, Any], _get_rotation_service().export_as_pdf(pages, paper_size))
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
                file_obj: UploadedFile = request.FILES[key]  # type: ignore[assignment]
                _validate_image_file(file_obj)
                filename = request.POST.get(f"filename_{idx}", file_obj.name)

                image_data = base64.b64encode(file_obj.read()).decode("utf-8")
                rotation = int(request.POST.get(f"rotation_{idx}", "0") or "0")
                pages.append(
                    {
                        "filename": filename,
                        "data": image_data,
                        "rotation": rotation,
                    }
                )

        if not pages:
            return {"success": False, "message": "没有页面数据"}

        return cast(dict[str, Any], _get_rotation_service().export_as_pdf(pages, paper_size))
    except Exception as exc:
        logger.error("multipart export-pdf 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.post("/export")
@rate_limit_from_settings("EXPORT", by_user=True)
def export_images(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
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
            return cast(dict[str, Any], _get_rotation_service().export_images(images, paper_size, rename_map))
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
                file_obj: UploadedFile = request.FILES[key]  # type: ignore[assignment]
                _validate_image_file(file_obj)
                filename = request.POST.get(f"filename_{idx}", file_obj.name)
                format_type = request.POST.get(f"format_{idx}", "jpeg")

                image_data = base64.b64encode(file_obj.read()).decode("utf-8")
                rotation = int(request.POST.get(f"rotation_{idx}", "0") or "0")
                images.append(
                    {
                        "filename": filename,
                        "data": image_data,
                        "format": format_type,
                        "rotation": rotation,
                    }
                )

        if not images:
            return {"success": False, "message": "没有图片数据"}

        return cast(dict[str, Any], _get_rotation_service().export_images(images, paper_size, rename_map))
    except Exception as exc:
        logger.error("multipart 导出失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


# ---------------------------------------------------------------------------
# 历史任务端点
# ---------------------------------------------------------------------------


def _get_job_service() -> Any:
    from apps.image_rotation.services.job_service import ImageRotationJobService

    return ImageRotationJobService()


def _serialize_job(job: Any) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "name": job.name,
        "display_name": job.name or "未命名任务",
        "status": job.status,
        "total_pages": job.total_pages,
        "has_export_zip": bool(job.export_zip_url),
        "has_export_pdf": bool(job.export_pdf_url),
        "created_at": job.created_at.isoformat() if job.created_at else "",
    }


def _serialize_page(page: Any) -> dict[str, Any]:
    return {
        "id": str(page.id),
        "original_filename": page.original_filename,
        "source_image_url": page.source_image.url if page.source_image else "",
        "page_number": page.page_number,
        "detected_rotation": page.detected_rotation,
        "onnx_rotation": getattr(page, "onnx_rotation", 0),
        "detection_confidence": round(page.detection_confidence, 4),
        "ocr_text": page.ocr_text,
        "suggested_filename": page.suggested_filename,
        "source_type": page.source_type,
    }


@router.post("/jobs")
def create_job(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """创建历史任务（multipart: name + pages JSON + source_N 文件）"""
    try:
        name = request.POST.get("name", "").strip()
        pages_json = request.POST.get("pages", "[]")
        pages_meta: list[dict[str, Any]] = json.loads(pages_json)

        if not pages_meta:
            return {"success": False, "message": "没有页面数据"}

        source_files = []
        for idx in range(len(pages_meta)):
            key = f"source_{idx}"
            if key in request.FILES:
                source_files.append(request.FILES[key])
            else:
                return {"success": False, "message": f"缺少 {key} 文件"}

        service = _get_job_service()
        job = service.create_job(
            name=name,
            pages_meta=pages_meta,
            source_files=source_files,
            created_by=request.user if request.user.is_authenticated else None,
        )
        page_ids = [str(p.id) for p in job.pages.all()]
        return {"success": True, "job_id": str(job.id), "display_name": job.name or "未命名任务", "page_ids": page_ids}
    except Exception as exc:
        logger.error("create_job 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.get("/jobs")
def list_jobs(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """分页列出历史任务"""
    try:
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 20))
        result = _get_job_service().list_jobs(page=page, page_size=page_size)
        return {
            "success": True,
            "jobs": [_serialize_job(j) for j in result["jobs"]],
            "total_count": result["total_count"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    except Exception as exc:
        logger.error("list_jobs 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.get("/jobs/{job_id}")
def get_job_detail(request: HttpRequest, job_id: str) -> dict[str, Any]:  # pragma: no cover
    """获取任务详情"""
    try:
        service = _get_job_service()
        job, pages = service.get_job_detail(job_id)
        job_data = _serialize_job(job)
        job_data["export_zip_url"] = job.export_zip_url
        job_data["export_pdf_url"] = job.export_pdf_url
        return {
            "success": True,
            "job": job_data,
            "pages": [_serialize_page(p) for p in pages],
        }
    except Exception as exc:
        logger.error("get_job_detail 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.post("/jobs/{job_id}/ocr")
async def run_job_ocr(request: HttpRequest, job_id: str) -> dict[str, Any]:  # pragma: no cover
    """对任务所有页面重跑 OCR"""
    try:
        payload = _body(request)
        provider: str = payload.get("provider", "local")
        service = _get_job_service()
        pages = await sync_to_async(service.run_ocr, thread_sensitive=False)(job_id, provider=provider)
        return {
            "success": True,
            "pages": [_serialize_page(p) for p in pages],
        }
    except Exception as exc:
        logger.error("run_job_ocr 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.patch("/jobs/{job_id}/pages")
def update_job_pages(request: HttpRequest, job_id: str) -> dict[str, Any]:  # pragma: no cover
    """批量更新页面旋转角度和文件名"""
    try:
        payload = _body(request)
        updates: list[dict[str, Any]] = payload.get("pages", [])
        if not updates:
            return {"success": True}

        job = _get_job_service().get_job(job_id)
        pages_map = {str(p.id): p for p in job.pages.all()}

        for upd in updates:
            page = pages_map.get(upd.get("page_id", ""))
            if not page:
                continue
            changed = False
            if "detected_rotation" in upd:
                page.detected_rotation = upd["detected_rotation"]
                changed = True
            if "suggested_filename" in upd:
                page.suggested_filename = upd["suggested_filename"]
                changed = True
            if "ocr_text" in upd:
                page.ocr_text = upd["ocr_text"]
                changed = True
            if changed:
                page.save(update_fields=["detected_rotation", "suggested_filename", "ocr_text", "updated_at"])

        return {"success": True}
    except Exception as exc:
        logger.error("update_job_pages 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.post("/jobs/{job_id}/save-export-url")
def save_export_url(request: HttpRequest, job_id: str) -> dict[str, Any]:  # pragma: no cover
    """保存导出文件 URL 到任务"""
    try:
        payload = _body(request)
        file_type: str = payload.get("file_type", "")
        media_url: str = payload.get("media_url", "")
        if not file_type or not media_url:
            return {"success": False, "message": "缺少 file_type 或 media_url"}
        job = _get_job_service().get_job(job_id)
        if file_type == "zip":
            job.export_zip_url = media_url
            job.save(update_fields=["export_zip_url", "updated_at"])
        elif file_type == "pdf":
            job.export_pdf_url = media_url
            job.save(update_fields=["export_pdf_url", "updated_at"])
        return {"success": True}
    except Exception as exc:
        logger.error("save_export_url 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.get("/jobs/{job_id}/download/{file_type}")
def download_job_export(request: HttpRequest, job_id: str, file_type: str) -> Any:  # pragma: no cover
    """下载任务导出文件"""
    from pathlib import Path

    from django.conf import settings
    from django.http import FileResponse

    job = _get_job_service().get_job(job_id)
    media_url = job.export_zip_url if file_type == "zip" else job.export_pdf_url if file_type == "pdf" else ""

    if not media_url:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError(message="导出文件不存在", code="EXPORT_NOT_FOUND", errors={})

    # 从 flat 路径直接读取文件
    rel = media_url.removeprefix("/media/")
    file_path = Path(str(settings.MEDIA_ROOT)) / rel

    if not file_path.exists():
        from apps.core.exceptions import NotFoundError

        raise NotFoundError(message="导出文件已被删除", code="EXPORT_FILE_GONE", errors={})

    content_type = "application/zip" if file_type == "zip" else "application/pdf"
    return FileResponse(
        open(file_path, "rb"),
        as_attachment=True,
        filename=f"image_rotation_{job_id}.{file_type}",
        content_type=content_type,
    )


@router.patch("/jobs/{job_id}")
def update_job_name(request: HttpRequest, job_id: str) -> dict[str, Any]:  # pragma: no cover
    """更新任务名称"""
    try:
        payload = _body(request)
        new_name: str = payload.get("name", "").strip()
        job = _get_job_service().get_job(job_id)
        job.name = new_name
        job.save(update_fields=["name", "updated_at"])
        return {"success": True, "display_name": job.name or "未命名任务"}
    except Exception as exc:
        logger.error("update_job_name 失败: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc)}


@router.delete("/jobs/{job_id}")
def delete_job(request: HttpRequest, job_id: str) -> dict[str, str]:  # pragma: no cover
    """删除任务"""
    _get_job_service().delete_job(job_id)
    return {"status": "deleted"}
