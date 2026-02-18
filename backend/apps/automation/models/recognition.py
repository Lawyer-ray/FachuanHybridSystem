"""文书识别相关模型"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentRecognitionStatus(models.TextChoices):
    """文书识别任务状态"""

    PENDING = "pending", _("待处理")
    PROCESSING = "processing", _("识别中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class DocumentRecognitionTask(models.Model):
    """文书识别任务"""

    id: int
    file_path = models.CharField(max_length=1024, verbose_name=_("文件路径"))
    original_filename = models.CharField(max_length=256, verbose_name=_("原始文件名"))
    status = models.CharField(
        max_length=32,
        choices=DocumentRecognitionStatus.choices,
        default=DocumentRecognitionStatus.PENDING,
        verbose_name=_("任务状态"),
    )
    # 识别结果
    document_type = models.CharField(max_length=32, null=True, blank=True, verbose_name=_("文书类型"))
    case_number = models.CharField(max_length=128, null=True, blank=True, verbose_name=_("案号"))
    key_time = models.DateTimeField(null=True, blank=True, verbose_name=_("关键时间"))
    confidence = models.FloatField(null=True, blank=True, verbose_name=_("置信度"))
    extraction_method = models.CharField(max_length=32, null=True, blank=True, verbose_name=_("提取方式"))
    raw_text = models.TextField(null=True, blank=True, verbose_name=_("原始文本"))
    renamed_file_path = models.CharField(max_length=1024, null=True, blank=True, verbose_name=_("重命名后路径"))
    # 绑定结果
    binding_success = models.BooleanField(null=True, verbose_name=_("绑定成功"))
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recognition_tasks",
        verbose_name=_("关联案件"),
    )
    case_log = models.ForeignKey(
        "cases.CaseLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recognition_tasks",
        verbose_name=_("案件日志"),
    )
    binding_message = models.CharField(max_length=512, null=True, blank=True, verbose_name=_("绑定消息"))
    binding_error_code = models.CharField(max_length=64, null=True, blank=True, verbose_name=_("绑定错误码"))
    # 错误信息
    error_message = models.TextField(null=True, blank=True, verbose_name=_("错误信息"))
    # 通知状态字段
    notification_sent = models.BooleanField(default=False, verbose_name=_("通知已发送"))
    notification_sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("通知发送时间"))
    notification_error = models.TextField(null=True, blank=True, verbose_name=_("通知错误信息"))
    notification_file_sent = models.BooleanField(default=False, verbose_name=_("文件已发送"))
    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))

    class Meta:
        app_label: str = "automation"
        verbose_name = _("文书识别任务")
        verbose_name_plural = _("文书识别任务")
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["case"]),
            models.Index(fields=["notification_sent"]),
        ]

    def __str__(self) -> str:
        return f"识别任务 #{self.id} - {self.get_status_display()}"
