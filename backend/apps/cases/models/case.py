"""Module for case."""

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import AuthorityType, CaseStage, CaseStatus, SimpleCaseType


class Case(models.Model):
    id: int
    contract: Any = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cases",
        verbose_name=_("关联合同"),
    )
    is_archived: Any = models.BooleanField(default=False, verbose_name=_("是否已建档"))
    filing_number: Any = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        verbose_name=_("建档编号"),
        help_text=_("格式: {年份}_{案件类型}_{AJ}_{序号}"),
    )
    name: Any = models.CharField(max_length=255, verbose_name=_("案件名称"))
    status: Any = models.CharField(
        max_length=32, choices=CaseStatus.choices, default=CaseStatus.ACTIVE, verbose_name=_("案件状态")
    )

    start_date: Any = models.DateField(auto_now_add=True, verbose_name=_("收案日期"))
    effective_date: Any = models.DateField(blank=True, null=True, verbose_name=_("生效日期"))
    specified_date: Any = models.DateField(blank=True, null=True, verbose_name=_("指定日期"))
    cause_of_action: Any = models.CharField(max_length=128, blank=True, null=True, verbose_name=_("案由"))
    target_amount: Any = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True, verbose_name=_("涉案金额")
    )
    preservation_amount: Any = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True, verbose_name=_("财产保全金额")
    )
    case_type: Any = models.CharField(
        max_length=32,
        choices=SimpleCaseType.choices,
        default=SimpleCaseType.CIVIL,
        blank=True,
        null=True,
        verbose_name=_("案件类型"),
    )

    current_stage: Any = models.CharField(
        max_length=64, choices=CaseStage.choices, blank=True, null=True, verbose_name=_("当前阶段")
    )

    class Meta:
        verbose_name = _("案件")
        verbose_name_plural = _("案件")
        indexes: ClassVar = [
            models.Index(fields=["contract"]),
            models.Index(fields=["is_archived"]),
            models.Index(fields=["filing_number"]),
            models.Index(fields=["start_date"]),
            models.Index(fields=["current_stage"]),
            models.Index(fields=["-start_date"]),  # 按日期倒序查询优化
        ]

    def __str__(self) -> str:
        return f"{self.name}"

    def clean(self) -> None:
        """
        基础数据验证
        复杂业务逻辑已移至 CaseService
        """
        from django.core.exceptions import ValidationError

        # 仅做基础验证,复杂的阶段验证在 Service 层处理
        if self.current_stage:
            valid_stages = {c[0] for c in CaseStage.choices}
            if self.current_stage not in valid_stages:
                raise ValidationError({"current_stage": _("无效的案件阶段")})


class CaseFilingNumberSequence(models.Model):
    year: Any = models.IntegerField(unique=True, verbose_name=_("年份"))
    id: int
    next_value: Any = models.IntegerField(default=1, verbose_name=_("下一个序号"))
    updated_at: Any = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("案件建档编号序列")
        verbose_name_plural = _("案件建档编号序列")
        indexes: ClassVar = [models.Index(fields=["year"])]


class CaseNumber(models.Model):
    id: int
    case: Any = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="case_numbers", verbose_name=_("案件"))
    id: int
    number: Any = models.CharField(max_length=128, verbose_name=_("案号"))
    remarks: Any = models.TextField(blank=True, null=True, verbose_name=_("备注"))
    created_at: Any = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("案件案号")
        verbose_name_plural = _("案件案号")
        ordering: ClassVar = ["created_at"]

    def __str__(self) -> str:
        return f"{self.number}"


class SupervisingAuthority(models.Model):
    """主管机关"""

    id: int
    case: Any = models.ForeignKey(
        Case, on_delete=models.CASCADE, related_name="supervising_authorities", verbose_name=_("案件")
    )
    name: Any = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("名称"))
    authority_type: Any = models.CharField(
        max_length=32,
        choices=AuthorityType.choices,
        default=AuthorityType.TRIAL,
        blank=True,
        null=True,
        verbose_name=_("性质"),
    )
    created_at: Any = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("主管机关")
        verbose_name_plural = _("主管机关")
        ordering: ClassVar = ["created_at"]
        indexes: ClassVar = [
            models.Index(fields=["case"]),
            models.Index(fields=["authority_type"]),
        ]

    def __str__(self) -> str:
        if self.name and self.authority_type:
            return f"{self.get_authority_type_display()} - {self.name}"
        elif self.name:
            return self.name
        elif self.authority_type:
            return self.get_authority_type_display()
        return f"主管机关 #{self.id}"
