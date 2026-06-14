"""Models for image rotation tools."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.conf import settings
from django.db import models

from apps.core.utils.path import Path


# ---------------------------------------------------------------------------
# upload_to 路径函数（实现 deconstruct 以支持迁移序列化）
# ---------------------------------------------------------------------------


class _JobSourcePath:
    """生成 `image_rotation/jobs/{job_id}/source/{uuid}{ext}` 路径。"""

    def __call__(self, instance: Any, filename: str) -> str:
        ext = Path(filename).suffix.lower() or ".jpg"
        return f"image_rotation/jobs/{instance.job_id}/source/{uuid.uuid4().hex}{ext}"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return ("apps.image_rotation.models._JobSourcePath", (), {})


class _JobExportPath:
    """生成 `image_rotation/jobs/{job_id}/exports/{uuid}{ext}` 路径。"""

    def __call__(self, instance: Any, filename: str) -> str:
        ext = Path(filename).suffix.lower() or ".bin"
        return f"image_rotation/jobs/{instance.job_id}/exports/{uuid.uuid4().hex}{ext}"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return ("apps.image_rotation.models._JobExportPath", (), {})


_job_source_path = _JobSourcePath()
_job_export_path = _JobExportPath()


# ---------------------------------------------------------------------------
# 虚拟模型（Admin 侧边栏入口，managed=False）
# ---------------------------------------------------------------------------


class ImageRotationTool(models.Model):
    """Admin entry model for image rotation."""

    id: int
    name: str = models.CharField(max_length=64, default="Image Rotation")  # type: ignore[assignment]

    class Meta:
        managed = False
        verbose_name = "图片自动旋转"
        verbose_name_plural = "图片自动旋转"


# ---------------------------------------------------------------------------
# 历史任务模型
# ---------------------------------------------------------------------------


class ImageRotationJobStatus(models.TextChoices):
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"


class ImageRotationJob(models.Model):
    """图片旋转历史任务"""

    id: uuid.UUID = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # type: ignore[assignment]
    name = models.CharField("任务名称", max_length=200, blank=True, default="")
    status = models.CharField(
        "状态",
        max_length=20,
        choices=ImageRotationJobStatus.choices,
        default=ImageRotationJobStatus.COMPLETED,
    )
    total_pages = models.PositiveIntegerField("总页数", default=0)
    export_zip_url = models.CharField("导出 ZIP URL", max_length=500, blank=True, default="")
    export_pdf_url = models.CharField("导出 PDF URL", max_length=500, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="image_rotation_jobs",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "image_rotation_job"
        verbose_name = "图片旋转任务"
        verbose_name_plural = "图片旋转任务"
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        display = self.name or "未命名任务"
        return f"{display} ({self.get_status_display()})"


class ImageRotationPage(models.Model):
    """图片旋转任务中的单页"""

    id: uuid.UUID = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # type: ignore[assignment]
    job = models.ForeignKey(
        ImageRotationJob,
        on_delete=models.CASCADE,
        related_name="pages",
        verbose_name="任务",
    )
    original_filename = models.CharField("原始文件名", max_length=500)
    source_image = models.FileField(
        "源图",
        upload_to=_job_source_path,
    )
    page_number = models.PositiveIntegerField("页码", default=0)
    detected_rotation = models.IntegerField("检测角度", default=0)
    onnx_rotation = models.IntegerField("ONNX自动旋转角度", default=0)
    detection_confidence = models.FloatField("置信度", default=0.0)
    ocr_text = models.TextField("OCR 文本", blank=True, default="")
    suggested_filename = models.CharField("建议文件名", max_length=500, blank=True, default="")
    source_type = models.CharField(
        "来源类型",
        max_length=20,
        default="image",
        help_text="'image' 或 'pdf_page'",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "image_rotation_page"
        verbose_name = "图片旋转页面"
        verbose_name_plural = "图片旋转页面"
        ordering: ClassVar[list[str]] = ["page_number"]

    def __str__(self) -> str:
        return self.original_filename
