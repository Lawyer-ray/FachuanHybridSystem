"""Module for contract."""

import contextlib
from datetime import date
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import CaseStatus, CaseType

if TYPE_CHECKING:
    from apps.organization.models import Lawyer


class FeeMode(models.TextChoices):
    FIXED = "FIXED", _("固定收费")
    SEMI_RISK = "SEMI_RISK", _("半风险收费")
    FULL_RISK = "FULL_RISK", _("全风险收费")
    CUSTOM = "CUSTOM", _("自定义")


class Contract(models.Model):
    id: int
    name: str = models.CharField(max_length=100, verbose_name=_("合同名称"))
    id: int
    case_type: str = models.CharField(max_length=32, choices=CaseType.choices, verbose_name=_("合同类型"))
    status = models.CharField(
        max_length=32, choices=CaseStatus.choices, default=CaseStatus.ACTIVE, verbose_name=_("合同状态")
    )
    specified_date: date = models.DateField(default=timezone.localdate, verbose_name=_("指定日期"))
    start_date: date | None = models.DateField(blank=True, null=True, verbose_name=_("开始日期"))
    end_date: date | None = models.DateField(blank=True, null=True, verbose_name=_("结束日期"))
    is_archived: bool = models.BooleanField(default=False, verbose_name=_("是否已建档"))
    filing_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        verbose_name=_("建档编号"),
        help_text=_("格式: {年份}_{合同类型}_{HT}_{序号}"),
    )
    fee_mode = models.CharField(
        max_length=16, choices=FeeMode.choices, default=FeeMode.FIXED, verbose_name=_("收费模式")
    )
    fixed_amount = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True, verbose_name=_("固定/前期律师费")
    )
    risk_rate = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True, verbose_name=_("风险比例(%)")
    )
    custom_terms: str | None = models.TextField(blank=True, null=True, verbose_name=_("自定义收费条款"))
    representation_stages: dict[str, Any] | None = models.JSONField(
        default=list, blank=True, verbose_name=_("代理阶段")
    )

    class Meta:
        verbose_name = _("合同")
        verbose_name_plural = _("合同")
        indexes: ClassVar = [
            # 单字段索引 - 用于基本过滤
            models.Index(fields=["case_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["is_archived"]),
            models.Index(fields=["specified_date"]),
            models.Index(fields=["-specified_date"]),
            models.Index(fields=["filing_number"]),
            # 复合索引 - 用于常见的组合查询
            # 按案件类型和状态查询(常用于列表过滤)
            models.Index(fields=["case_type", "status"]),
            # 按状态和指定日期查询(常用于时间范围过滤)
            models.Index(fields=["status", "-specified_date"]),
            # 按是否建档和指定日期查询(常用于归档管理)
            models.Index(fields=["is_archived", "-specified_date"]),
            # 按案件类型、状态和指定日期查询(常用于复杂过滤)
            models.Index(fields=["case_type", "status", "-specified_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.name}"

    def clean(self) -> None:
        from apps.contracts.validators import normalize_representation_stages

        ctype = getattr(self, "case_type", None)
        rep = getattr(self, "representation_stages", None)
        with contextlib.suppress(Exception):
            self.representation_stages = normalize_representation_stages(ctype, rep, strict=False)

    @property
    def primary_lawyer(self) -> Optional["Lawyer"]:
        """
        获取主办律师

        通过关联的 ContractAssignment 查询标记为主办律师的记录.
        这是一个简单的关联查询,保留在 Model 层.

        性能优化建议:
            在列表查询时应使用 prefetch_related 预加载关联对象:
            >>> contracts = Contract.objects.prefetch_related(
            ...     Prefetch('assignments',
            ...              queryset=ContractAssignment.objects.filter(is_primary=True).select_related('lawyer'))
            ... )

        Returns:
            Optional[Lawyer]: 主办律师对象,如果没有则返回 None

        Requirements: 3.1, 7.4, 8.3
        """
        assignment = self.assignments.filter(is_primary=True).first()
        return assignment.lawyer if assignment else None

    @property
    def all_lawyers(self) -> list["Lawyer"]:
        """
        获取所有律师列表

        返回所有关联的律师,按 is_primary 降序、order 升序排列.
        这是一个简单的关联查询,保留在 Model 层.

        性能优化建议:
            在列表查询时应使用 prefetch_related 预加载关联对象:
            >>> contracts = Contract.objects.prefetch_related(
            ...     'assignments__lawyer'
            ... )

        Returns:
            List[Lawyer]: 律师对象列表,如果没有则返回空列表

        Note:
            返回的律师列表已按 ContractAssignment 的 Meta.ordering 排序:
            - 主办律师优先(is_primary=True)
            - 相同优先级按 order 字段升序

        Requirements: 3.1, 7.4, 8.3
        """
        return [assignment.lawyer for assignment in self.assignments.all()]
