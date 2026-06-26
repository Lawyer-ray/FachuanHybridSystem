from __future__ import annotations

import logging
import uuid
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction

from apps.core.exceptions import NotFoundError
from apps.core.protocols import IOcrService

from ..models import ImageRotationJob, ImageRotationJobStatus, ImageRotationPage

logger = logging.getLogger("apps.image_rotation")


class ImageRotationJobService:
    """图片旋转历史任务服务"""

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def create_job(
        *,
        name: str,
        pages_meta: list[dict[str, Any]],
        source_files: list[Any],
        created_by: Any = None,
    ) -> ImageRotationJob:
        """创建任务 + 页面，存储源图。

        Args:
            name: 用户命名（可为空）
            pages_meta: 每页元数据 [{filename, detected_rotation, detection_confidence, source_type, page_number}]
            source_files: 对应的文件对象列表（UploadedFile 或 BytesIO）
            created_by: 当前用户
        """
        if len(pages_meta) != len(source_files):
            raise ValueError(f"pages_meta ({len(pages_meta)}) 与 source_files ({len(source_files)}) 数量不匹配")

        job = ImageRotationJob.objects.create(
            name=name,
            status=ImageRotationJobStatus.COMPLETED,
            total_pages=len(pages_meta),
            created_by=created_by,
        )

        for idx, (meta, file_obj) in enumerate(zip(pages_meta, source_files)):
            file_bytes = file_obj.read()
            ext = _guess_ext(meta.get("filename", ""))
            content = ContentFile(file_bytes, name=f"{uuid.uuid4().hex}{ext}")

            ImageRotationPage.objects.create(
                job=job,
                original_filename=meta.get("filename", f"image_{idx + 1}"),
                source_image=content,
                page_number=meta.get("page_number", idx),
                detected_rotation=meta.get("detected_rotation", 0),
                onnx_rotation=meta.get("onnx_rotation", 0),
                detection_confidence=meta.get("detection_confidence", 0.0),
                source_type=meta.get("source_type", "image"),
            )

        logger.info("创建图片旋转任务: %s (%d 页)", job.id, job.total_pages)
        return job

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @staticmethod
    def get_job(job_id: str | uuid.UUID) -> ImageRotationJob:
        try:
            return ImageRotationJob.objects.get(pk=job_id)
        except ImageRotationJob.DoesNotExist:
            raise NotFoundError(
                message=f"任务 {job_id} 不存在",
                code="JOB_NOT_FOUND",
                errors={},
            )

    @staticmethod
    def list_jobs(*, created_by: Any = None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        qs = ImageRotationJob.objects.all()
        if created_by is not None:
            qs = qs.filter(created_by=created_by)

        total = qs.count()
        start = (page - 1) * page_size
        jobs = list(qs[start : start + page_size])

        return {
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "jobs": jobs,
        }

    @staticmethod
    def get_job_detail(job_id: str | uuid.UUID) -> tuple[ImageRotationJob, list[ImageRotationPage]]:
        job = ImageRotationJobService.get_job(job_id)
        pages = list(job.pages.all())
        return job, pages

    # ------------------------------------------------------------------
    # OCR 重识别
    # ------------------------------------------------------------------

    @staticmethod
    def run_ocr(
        job_id: str | uuid.UUID,
        provider: str = "local",
        ocr_service: IOcrService | None = None,
    ) -> list[ImageRotationPage]:
        """对任务所有页面重跑 OCR + 建议重命名。"""
        from apps.core.interfaces import ServiceLocator
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        job, pages = ImageRotationJobService.get_job_detail(job_id)

        if ocr_service is None:
            if provider != "local":
                from apps.automation.services.ocr.ocr_service import OCRService

                ocr_service = OCRService(use_v5=True, provider=provider)
            else:
                ocr_service = ServiceLocator.get_ocr_service()

        rename_service = AutoRenameService()

        for page in pages:
            try:
                image_bytes = page.source_image.read()
                text_result = ocr_service.extract_text(image_bytes)
                page.ocr_text = text_result.text

                if text_result.text.strip():
                    suggestion = rename_service.suggest_rename(page.original_filename, text_result.text)
                    if suggestion.success:
                        page.suggested_filename = suggestion.suggested_filename

                page.save(update_fields=["ocr_text", "suggested_filename", "updated_at"])
            except Exception:
                logger.exception("OCR 重识别失败: page %s", page.id)

        return pages

    # ------------------------------------------------------------------
    # 关联导出
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    @staticmethod
    def delete_job(job_id: str | uuid.UUID) -> None:
        """删除任务（信号自动清理文件）。"""
        job = ImageRotationJobService.get_job(job_id)
        job.delete()
        logger.info("删除图片旋转任务: %s", job_id)


def _guess_ext(filename: str) -> str:
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", ".gif"):
            return ext
    return ".jpg"
