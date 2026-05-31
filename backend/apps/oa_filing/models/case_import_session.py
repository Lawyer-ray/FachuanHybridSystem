"""Module for case import session."""

from django.db import models

class CaseImportStatus(models.TextChoices):
    PENDING = "pending", "待开始"
    IN_PROGRESS = "in_progress", "进行中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"

class CaseImportPhase(models.TextChoices):
    PENDING = "pending", "待开始"
    PARSING = "parsing", "解析中"
    PREVIEW = "preview", "预览中"
    DISCOVERING = "discovering", "查找中"
    IMPORTING = "importing", "导入中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"

class CaseImportSession(models.Model):
    """OA案件导入记录"""

    lawyer = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        related_name="case_import_sessions",
        verbose_name="发起用户",
    )
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.SET_NULL,
        null=True,
        related_name="case_import_sessions",
        verbose_name="OA凭证",
    )
    status = models.CharField(
        max_length=16,
        choices=CaseImportStatus.choices,
        default=CaseImportStatus.PENDING,
        verbose_name="状态",
    )
    phase = models.CharField(
        max_length=16,
        choices=CaseImportPhase.choices,
        default=CaseImportPhase.PENDING,
        verbose_name="阶段",
    )
    uploaded_filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="上传文件名",
    )
    total_count = models.IntegerField(default=0, verbose_name="总案件数")
    matched_count = models.IntegerField(default=0, verbose_name="已匹配数")
    unmatched_count = models.IntegerField(default=0, verbose_name="未匹配数")
    success_count = models.IntegerField(default=0, verbose_name="成功数量")
    skip_count = models.IntegerField(default=0, verbose_name="跳过数量")
    error_count = models.IntegerField(default=0, verbose_name="错误数量")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    progress_message = models.CharField(max_length=255, blank=True, default="", verbose_name="进度描述")
    result_data = models.JSONField(default=dict, verbose_name="结果数据")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "案件导入记录"
        verbose_name_plural = "案件导入记录"

    def __str__(self) -> str:
        return f"CaseImportSession #{self.id} - {self.status}"
