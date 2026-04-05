from __future__ import annotations

import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class PdfSplitJobStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    PROCESSING = "processing", _("处理中")
    REVIEW_REQUIRED = "review_required", _("待复核")
    EXPORTING = "exporting", _("导出中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class PdfSplitSourceType(models.TextChoices):
    UPLOAD = "upload", _("上传文件")
    LOCAL_PATH = "local_path", _("本地路径")


class PdfSplitMode(models.TextChoices):
    CONTENT_ANALYSIS = "content_analysis", _("内容识别拆分")
    PAGE_SPLIT = "page_split", _("按页拆分")
    MANUAL_SPLIT = "manual_split", _("手动拆分")


class PdfSplitOcrProfile(models.TextChoices):
    FAST = "fast", _("快速")
    BALANCED = "balanced", _("均衡")
    ACCURATE = "accurate", _("高精度")


class PdfSplitSegmentType(models.TextChoices):
    COMPLAINT = "complaint", _("起诉状")
    EVIDENCE_LIST = "evidence_list", _("证据清单及明细")
    PRESERVATION_MATERIALS = "preservation_materials", _("财产保全资料")
    PARTY_IDENTITY = "party_identity", _("双方当事人主体信息")
    AUTHORIZATION_MATERIALS = "authorization_materials", _("授权委托材料")
    DELIVERY_ADDRESS_CONFIRMATION = "delivery_address_confirmation", _("送达地址确认书")
    REFUND_ACCOUNT_CONFIRMATION = "refund_account_confirmation", _("诉讼费用退费账户确认书")
    UNRECOGNIZED = "unrecognized", _("未识别材料")


class PdfSplitReviewFlag(models.TextChoices):
    NORMAL = "normal", _("正常")
    LOW_CONFIDENCE = "low_confidence", _("低置信度")
    UNRECOGNIZED = "unrecognized", _("未识别")
    OCR_FAILED = "ocr_failed", _("OCR失败")


class PdfSplittingTool(models.Model):
    id: int
    name = models.CharField(max_length=64, default="Pdf Splitting")

    class Meta:
        managed = False
        verbose_name = _("PDF 拆解")
        verbose_name_plural = _("PDF 拆解")


class PdfSplitJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_type = models.CharField(
        max_length=16,
        choices=PdfSplitSourceType.choices,
        verbose_name=_("来源类型"),
    )
    source_abs_path = models.CharField(max_length=2048, blank=True, default="", verbose_name=_("源绝对路径"))
    source_relpath = models.CharField(max_length=1024, blank=True, default="", verbose_name=_("源相对路径"))
    source_original_name = models.CharField(max_length=255, verbose_name=_("源文件名"))
    split_mode = models.CharField(
        max_length=32,
        choices=PdfSplitMode.choices,
        default=PdfSplitMode.CONTENT_ANALYSIS,
        verbose_name=_("拆分模式"),
    )
    template_key = models.CharField(max_length=64, default="filing_materials_v1", verbose_name=_("模板键"))
    template_version = models.CharField(max_length=32, default="1", verbose_name=_("模板版本"))
    ocr_profile = models.CharField(
        max_length=16,
        choices=PdfSplitOcrProfile.choices,
        default=PdfSplitOcrProfile.BALANCED,
        verbose_name=_("OCR 档位"),
    )
    status = models.CharField(
        max_length=32,
        choices=PdfSplitJobStatus.choices,
        default=PdfSplitJobStatus.PENDING,
        verbose_name=_("状态"),
    )
    total_pages = models.PositiveIntegerField(default=0, verbose_name=_("总页数"))
    processed_pages = models.PositiveIntegerField(default=0, verbose_name=_("已处理页数"))
    progress = models.PositiveIntegerField(default=0, verbose_name=_("进度"))
    current_page = models.PositiveIntegerField(default=0, verbose_name=_("当前页"))
    task_id = models.CharField(max_length=64, blank=True, default="", verbose_name=_("任务ID"))
    cancel_requested = models.BooleanField(default=False, verbose_name=_("请求取消"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pdf_split_jobs",
        verbose_name=_("创建人"),
    )
    summary_payload = models.JSONField(default=dict, blank=True, verbose_name=_("摘要"))
    error_message = models.TextField(blank=True, default="", verbose_name=_("错误信息"))
    export_zip_relpath = models.CharField(max_length=1024, blank=True, default="", verbose_name=_("导出ZIP路径"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("PDF 拆解任务")
        verbose_name_plural = _("PDF 拆解任务")
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_original_name} ({self.get_status_display()})"


class PdfSplitSegment(models.Model):
    job = models.ForeignKey(
        PdfSplitJob,
        on_delete=models.CASCADE,
        related_name="segments",
        verbose_name=_("任务"),
    )
    order = models.PositiveIntegerField(default=1, verbose_name=_("排序"))
    page_start = models.PositiveIntegerField(verbose_name=_("起始页"))
    page_end = models.PositiveIntegerField(verbose_name=_("结束页"))
    segment_type = models.CharField(
        max_length=48,
        choices=PdfSplitSegmentType.choices,
        default=PdfSplitSegmentType.UNRECOGNIZED,
        verbose_name=_("段类型"),
    )
    filename = models.CharField(max_length=255, verbose_name=_("文件名"))
    confidence = models.FloatField(default=0.0, verbose_name=_("置信度"))
    source_method = models.CharField(max_length=32, default="rule", verbose_name=_("来源方法"))
    review_flag = models.CharField(
        max_length=32,
        choices=PdfSplitReviewFlag.choices,
        default=PdfSplitReviewFlag.NORMAL,
        verbose_name=_("复核标记"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("PDF 拆解片段")
        verbose_name_plural = _("PDF 拆解片段")
        ordering: ClassVar[list[str]] = ["order", "id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["job", "order"], name="pdf_splitting_segment_job_order_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.job_id}:{self.page_start}-{self.page_end} {self.segment_type}"


@receiver(post_delete, sender=PdfSplitJob)
def delete_job_files(sender: type, instance: PdfSplitJob, **kwargs: object) -> None:
    """删除任务时清理关联的文件目录"""
    from apps.pdf_splitting.services.storage import PdfSplitStorage

    storage = PdfSplitStorage(instance.id)
    storage.cleanup()
