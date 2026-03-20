"""Module for case."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import AuthorityType, CaseStage, CaseStatus, SimpleCaseType

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .chat import CaseChat, ChatAuditLog
    from .log import CaseLog
    from .material import CaseFolderBinding, CaseMaterial, CaseMaterialGroupOrder
    from .party import CaseAccessGrant, CaseAssignment, CaseParty
    from .template_binding import CaseTemplateBinding


class Case(models.Model):
    id: int
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cases",
        verbose_name=_("关联合同"),
    )
    is_archived = models.BooleanField(default=False, verbose_name=_("是否已建档"))
    filing_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        verbose_name=_("建档编号"),
        help_text=_("格式: {年份}_{案件类型}_{AJ}_{序号}"),
    )
    name = models.CharField(max_length=255, verbose_name=_("案件名称"))
    status = models.CharField(
        max_length=32, choices=CaseStatus.choices, default=CaseStatus.ACTIVE, verbose_name=_("案件状态")
    )
    start_date = models.DateField(auto_now_add=True, verbose_name=_("收案日期"))
    effective_date = models.DateField(blank=True, null=True, verbose_name=_("生效日期"))
    specified_date = models.DateField(blank=True, null=True, verbose_name=_("指定日期"))
    cause_of_action = models.CharField(max_length=128, blank=True, null=True, verbose_name=_("案由"))
    target_amount = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True, verbose_name=_("涉案金额")
    )
    preservation_amount = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True, verbose_name=_("财产保全金额")
    )
    case_type = models.CharField(
        max_length=32,
        choices=SimpleCaseType.choices,
        default=SimpleCaseType.CIVIL,
        blank=True,
        null=True,
        verbose_name=_("案件类型"),
    )
    current_stage = models.CharField(
        max_length=64, choices=CaseStage.choices, blank=True, null=True, verbose_name=_("当前阶段")
    )

    if TYPE_CHECKING:
        case_numbers: RelatedManager[CaseNumber]
        supervising_authorities: RelatedManager[SupervisingAuthority]
        parties: RelatedManager[CaseParty]
        assignments: RelatedManager[CaseAssignment]
        access_grants: RelatedManager[CaseAccessGrant]
        logs: RelatedManager[CaseLog]
        chats: RelatedManager[CaseChat]
        chat_audit_logs: RelatedManager[ChatAuditLog]
        materials: RelatedManager[CaseMaterial]
        material_group_orders: RelatedManager[CaseMaterialGroupOrder]
        folder_binding: CaseFolderBinding
        template_bindings: RelatedManager[CaseTemplateBinding]

    class Meta:
        verbose_name = _("案件")
        verbose_name_plural = _("案件")
        indexes: ClassVar = [
            models.Index(fields=["contract"]),
            models.Index(fields=["is_archived"]),
            models.Index(fields=["filing_number"]),
            models.Index(fields=["start_date"]),
            models.Index(fields=["current_stage"]),
            models.Index(fields=["-start_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.name}"

    def clean(self) -> None:
        """
        基础数据验证
        复杂业务逻辑已移至 CaseService
        """
        from django.core.exceptions import ValidationError

        if self.current_stage:
            valid_stages = {c[0] for c in CaseStage.choices}
            if self.current_stage not in valid_stages:
                raise ValidationError({"current_stage": _("无效的案件阶段")})


class CaseFilingNumberSequence(models.Model):
    id: int
    year = models.IntegerField(unique=True, verbose_name=_("年份"))
    next_value = models.IntegerField(default=1, verbose_name=_("下一个序号"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("案件建档编号序列")
        verbose_name_plural = _("案件建档编号序列")
        indexes: ClassVar = [models.Index(fields=["year"])]


class CaseNumber(models.Model):
    id: int
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="case_numbers", verbose_name=_("案件"))
    number = models.CharField(max_length=128, verbose_name=_("案号"))
    document_name = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        verbose_name=_("文书名称"),
        help_text=_("如：民事判决书、民事调解书、执行证书等"),
    )
    document_file = models.FileField(
        upload_to="case_documents/%Y/%m/",
        blank=True,
        null=True,
        verbose_name=_("裁判文书文件"),
        help_text=_("上传PDF格式的裁判文书，用于自动提取执行依据主文"),
    )
    document_content = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("执行依据主文"),
        help_text=_("从裁判文书自动提取的判决/调解主文内容"),
    )
    is_active = models.BooleanField(default=False, verbose_name=_("是否已生效"))
    remarks = models.TextField(blank=True, null=True, verbose_name=_("备注"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("案件案号")
        verbose_name_plural = _("案件案号")
        ordering: ClassVar = ["created_at"]

    def __str__(self) -> str:
        return f"{self.number}"

    def get_full_number(self) -> str:
        """获取完整案号（案号+文书名称）"""
        if self.document_name:
            return f"{self.number}《{self.document_name}》"
        return self.number


class SupervisingAuthority(models.Model):
    """主管机关"""

    id: int
    case = models.ForeignKey(
        Case, on_delete=models.CASCADE, related_name="supervising_authorities", verbose_name=_("案件")
    )
    name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("名称"))
    authority_type = models.CharField(
        max_length=32,
        choices=AuthorityType.choices,
        default=AuthorityType.TRIAL,
        blank=True,
        null=True,
        verbose_name=_("性质"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    if TYPE_CHECKING:
        materials: RelatedManager[CaseMaterial]
        material_group_orders: RelatedManager[CaseMaterialGroupOrder]

    class Meta:
        verbose_name = _("主管机关")
        verbose_name_plural = _("主管机关")
        ordering: ClassVar = ["created_at"]
        indexes: ClassVar = [
            models.Index(fields=["case"]),
            models.Index(fields=["authority_type"]),
        ]

    def __str__(self) -> str:
        authority_type_display = self.get_authority_type_display()
        if self.name and self.authority_type:
            return f"{authority_type_display} - {self.name}"
        elif self.name:
            return self.name
        elif self.authority_type:
            return str(authority_type_display)
        return f"主管机关 #{self.id}"
