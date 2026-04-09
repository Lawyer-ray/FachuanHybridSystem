"""财产保全询价相关模型"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from apps.cases.models import Case


class QuoteStatus(models.TextChoices):
    """询价任务状态"""

    PENDING = "pending", _("等待中")
    RUNNING = "running", _("执行中")
    SUCCESS = "success", _("成功")
    PARTIAL_SUCCESS = "partial_success", _("部分成功")
    FAILED = "failed", _("失败")


class QuoteItemStatus(models.TextChoices):
    """单个报价状态"""

    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class PreservationQuote(models.Model):
    """财产保全询价任务"""

    id: int
    if TYPE_CHECKING:
        quotes: RelatedManager[InsuranceQuote]
    preserve_amount = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name=_("保全金额"), help_text=_("需要保全的财产金额")
    )
    corp_id = models.CharField(
        max_length=32, default="2550", verbose_name=_("法院ID"), help_text=_("法院系统中的法院标识")
    )
    category_id = models.CharField(
        max_length=32, default="127000", verbose_name=_("分类ID"), help_text=_("保全分类ID (cPid)")
    )
    credential_id = models.IntegerField(
        null=True, blank=True, verbose_name=_("凭证ID"), help_text=_("关联的账号凭证ID(可选,系统会自动获取Token)")
    )
    status = models.CharField(
        max_length=32, choices=QuoteStatus.choices, default=QuoteStatus.PENDING, verbose_name=_("任务状态")
    )
    total_companies = models.IntegerField(default=0, verbose_name=_("保险公司总数"))
    success_count = models.IntegerField(default=0, verbose_name=_("成功查询数"))
    failed_count = models.IntegerField(default=0, verbose_name=_("失败查询数"))
    error_message = models.TextField(null=True, blank=True, verbose_name=_("错误信息"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))

    class Meta:
        app_label = "automation"
        verbose_name = _("财产保全询价")
        verbose_name_plural = _("财产保全询价")
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["credential_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"询价任务 #{self.id} - {self.preserve_amount}元 - {self.get_status_display()}"

    def get_success_rate(self) -> float:
        """获取成功率"""
        if self.total_companies == 0:
            return 0.0
        return (self.success_count / self.total_companies) * 100


class InsuranceQuote(models.Model):
    """保险公司报价记录"""

    id: int
    preservation_quote = models.ForeignKey(
        PreservationQuote, on_delete=models.CASCADE, related_name="quotes", verbose_name=_("询价任务")
    )
    company_id = models.CharField(max_length=64, verbose_name=_("保险公司ID"), help_text=_("cId"))
    company_code = models.CharField(max_length=64, verbose_name=_("保险公司编码"), help_text=_("cCode"))
    company_name = models.CharField(max_length=256, verbose_name=_("保险公司名称"), help_text=_("cName"))
    premium = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("报价金额"),
        help_text=_("保险公司给出的担保费报价(通常使用 minPremium)"),
    )
    # 费率信息字段
    min_premium = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("最低收费1"), help_text=_("minPremium")
    )
    min_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("最低收费2"), help_text=_("minAmount")
    )
    max_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("最高收费"), help_text=_("maxAmount")
    )
    min_rate = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True, verbose_name=_("最低费率"), help_text=_("minRate")
    )
    max_rate = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True, verbose_name=_("最高费率"), help_text=_("maxRate")
    )
    max_apply_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("最高保全金额"),
        help_text=_("maxApplyAmount"),
    )
    status = models.CharField(max_length=32, choices=QuoteItemStatus.choices, verbose_name=_("查询状态"))
    error_message = models.TextField(null=True, blank=True, verbose_name=_("错误信息"))
    response_data = models.JSONField(
        null=True, blank=True, verbose_name=_("完整响应"), help_text=_("API 返回的完整响应数据")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        app_label = "automation"
        verbose_name = _("保险公司报价")
        verbose_name_plural = _("保险公司报价")
        ordering: ClassVar = ["min_amount"]  # 按最低报价排序
        indexes: ClassVar = [
            models.Index(fields=["preservation_quote", "status"]),
            models.Index(fields=["company_id"]),
            models.Index(fields=["premium"]),
        ]

    def __str__(self) -> str:
        if self.min_amount:
            return f"{self.company_name} - ¥{self.min_amount}"
        return f"{self.company_name} - {self.get_status_display()}"
