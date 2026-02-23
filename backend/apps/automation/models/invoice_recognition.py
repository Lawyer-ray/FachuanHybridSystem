"""发票识别相关模型"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class InvoiceCategory(models.TextChoices):
    """发票类目"""

    VAT_SPECIAL = "vat_special", _("增值税专用发票")
    VAT_NORMAL = "vat_normal", _("增值税普通发票")
    VAT_ELECTRONIC = "vat_electronic", _("增值税电子普通发票")
    VEHICLE_SALES = "vehicle_sales", _("机动车销售统一发票")
    TRAIN_TICKET = "train_ticket", _("火车票")
    TAXI_RECEIPT = "taxi_receipt", _("出租车发票")
    QUOTA_INVOICE = "quota_invoice", _("定额发票")
    AIR_ITINERARY = "air_itinerary", _("飞机行程单")
    TOLL_RECEIPT = "toll_receipt", _("过路费发票")
    OTHER = "other", _("其他")


class InvoiceRecognitionTaskStatus(models.TextChoices):
    """发票识别任务状态"""

    PENDING = "pending", _("待处理")
    PROCESSING = "processing", _("处理中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")


class InvoiceRecordStatus(models.TextChoices):
    """发票记录识别状态"""

    PENDING = "pending", _("待识别")
    SUCCESS = "success", _("识别成功")
    FAILED = "failed", _("识别失败")


class InvoiceRecognitionTask(models.Model):
    """发票识别任务"""

    id: int
    name = models.CharField(max_length=255, verbose_name=_("任务名称"))
    status = models.CharField(
        max_length=32,
        choices=InvoiceRecognitionTaskStatus.choices,
        default=InvoiceRecognitionTaskStatus.PENDING,
        verbose_name=_("任务状态"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_recognition_tasks",
        verbose_name=_("创建人"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    merge_config = models.JSONField(default=list, blank=True, verbose_name=_("分组合并配置"))

    class Meta:
        app_label = "automation"
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"]),
        ]
        verbose_name = _("发票识别任务")
        verbose_name_plural = _("发票识别任务")

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"


class InvoiceRecord(models.Model):
    """发票记录"""

    id: int
    task = models.ForeignKey(
        InvoiceRecognitionTask,
        on_delete=models.CASCADE,
        related_name="records",
        verbose_name=_("所属任务"),
    )
    file_path = models.CharField(max_length=1024, verbose_name=_("文件路径"))
    original_filename = models.CharField(max_length=255, verbose_name=_("原始文件名"))
    invoice_code = models.CharField(max_length=50, blank=True, default="", verbose_name=_("发票代码"))
    invoice_number = models.CharField(max_length=50, blank=True, default="", verbose_name=_("发票号码"))
    invoice_date = models.DateField(null=True, blank=True, verbose_name=_("开票日期"))
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("金额（不含税）")
    )
    tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("税额")
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("价税合计")
    )
    buyer_name = models.CharField(max_length=255, blank=True, default="", verbose_name=_("购买方名称"))
    seller_name = models.CharField(max_length=255, blank=True, default="", verbose_name=_("销售方名称"))
    project_name = models.CharField(max_length=255, blank=True, default="", verbose_name=_("项目名称"))
    category = models.CharField(
        max_length=32,
        choices=InvoiceCategory.choices,
        default=InvoiceCategory.OTHER,
        verbose_name=_("发票类目"),
    )
    raw_text = models.TextField(blank=True, default="", verbose_name=_("OCR 原始文本"))
    is_duplicate = models.BooleanField(default=False, verbose_name=_("是否重复"))
    duplicate_of_id = models.IntegerField(null=True, blank=True, verbose_name=_("重复的原始记录ID"))
    status = models.CharField(
        max_length=32,
        choices=InvoiceRecordStatus.choices,
        default=InvoiceRecordStatus.PENDING,
        verbose_name=_("识别状态"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        app_label = "automation"
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["invoice_code", "invoice_number"]),
            models.Index(fields=["task", "category"]),
        ]
        verbose_name = _("发票记录")
        verbose_name_plural = _("发票记录")

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_status_display()})"
