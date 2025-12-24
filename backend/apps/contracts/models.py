from typing import Optional, List

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import CaseType, CaseStatus


class FeeMode(models.TextChoices):
    FIXED = "FIXED", _("固定收费")
    SEMI_RISK = "SEMI_RISK", _("半风险收费")
    FULL_RISK = "FULL_RISK", _("全风险收费")
    CUSTOM = "CUSTOM", _("自定义")


class Contract(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("合同名称"))
    case_type = models.CharField(max_length=32, choices=CaseType.choices, verbose_name=_("合同类型"))
    status = models.CharField(max_length=32, choices=CaseStatus.choices, default=CaseStatus.ACTIVE, verbose_name=_("合同状态"))
    specified_date = models.DateField(default=timezone.localdate, verbose_name=_("指定日期"))
    start_date = models.DateField(blank=True, null=True, verbose_name=_("开始日期"))
    end_date = models.DateField(blank=True, null=True, verbose_name=_("结束日期"))
    is_archived = models.BooleanField(default=False, verbose_name=_("是否已建档"))
    fee_mode = models.CharField(max_length=16, choices=FeeMode.choices, default=FeeMode.FIXED, verbose_name=_("收费模式"))
    fixed_amount = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True, verbose_name=_("固定/前期律师费"))
    risk_rate = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name=_("风险比例(%)"))
    custom_terms = models.TextField(blank=True, null=True, verbose_name=_("自定义收费条款"))
    representation_stages = models.JSONField(default=list, blank=True, verbose_name=_("代理阶段"))

    class Meta:
        verbose_name = _("合同")
        verbose_name_plural = _("合同")
        indexes = [
            models.Index(fields=["case_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["is_archived"]),
            models.Index(fields=["specified_date"]),
            models.Index(fields=["-specified_date"]),
        ]

    def __str__(self):
        return f"{self.name}"

    def clean(self):
        from apps.cases.validators import normalize_stages
        ctype = getattr(self, "case_type", None)
        rep = getattr(self, "representation_stages", None)
        try:
            rep2, _ = normalize_stages(ctype, rep, None, strict=False)
            self.representation_stages = rep2
        except Exception:
            pass

    @property
    def primary_lawyer(self) -> Optional["Lawyer"]:
        """获取主办律师"""
        assignment = self.assignments.filter(is_primary=True).first()
        return assignment.lawyer if assignment else None

    @property
    def all_lawyers(self) -> List["Lawyer"]:
        """获取所有律师列表，按 is_primary 降序、order 升序排列"""
        return [assignment.lawyer for assignment in self.assignments.all()]


class PartyRole(models.TextChoices):
    """当事人身份"""
    PRINCIPAL = "PRINCIPAL", _("委托人")
    BENEFICIARY = "BENEFICIARY", _("受益人")
    OPPOSING = "OPPOSING", _("对方当事人")


class ContractParty(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="contract_parties", verbose_name=_("合同"))
    client = models.ForeignKey("client.Client", on_delete=models.CASCADE, related_name="contracts", verbose_name=_("当事人"))
    role = models.CharField(max_length=16, choices=PartyRole.choices, default=PartyRole.PRINCIPAL, verbose_name=_("身份"))

    class Meta:
        unique_together = ("contract", "client")
        verbose_name = _("合同当事人")
        verbose_name_plural = _("合同当事人")

    def __str__(self):
        return f"{self.contract_id}-{self.client_id}-{self.role}"


class ContractAssignment(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="assignments", verbose_name=_("合同"))
    lawyer = models.ForeignKey("organization.Lawyer", on_delete=models.CASCADE, related_name="contract_assignments", verbose_name=_("律师"))
    is_primary = models.BooleanField(default=False, verbose_name=_("是否主办律师"))
    order = models.IntegerField(default=0, verbose_name=_("排序"))

    class Meta:
        verbose_name = _("合同指派")
        verbose_name_plural = _("合同指派")
        unique_together = ("contract", "lawyer")
        ordering = ['-is_primary', 'order']

    def __str__(self):
        return f"{self.contract_id}-{self.lawyer_id}"


class InvoiceStatus(models.TextChoices):
    UNINVOICED = "UNINVOICED", _("未开票")
    INVOICED_PARTIAL = "INVOICED_PARTIAL", _("部分开票")
    INVOICED_FULL = "INVOICED_FULL", _("已开票")


class ContractPayment(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="payments", verbose_name=_("合同"))
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_("收款金额"))
    received_at = models.DateField(default=timezone.localdate, verbose_name=_("收款日期"))
    invoice_status = models.CharField(max_length=32, choices=InvoiceStatus.choices, default=InvoiceStatus.UNINVOICED, verbose_name=_("开票状态"))
    invoiced_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("已开票金额"))
    note = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("备注"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("合同收款")
        verbose_name_plural = _("合同收款")
        indexes = [
            models.Index(fields=["contract", "received_at"]),
            models.Index(fields=["invoice_status"]),
        ]

    def __str__(self):
        return f"{self.contract_id}-{self.amount}"


class LogLevel(models.TextChoices):
    INFO = "INFO", _("信息")
    WARN = "WARN", _("预警")
    ERROR = "ERROR", _("错误")


class ContractFinanceLog(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="finance_logs", verbose_name=_("合同"))
    action = models.CharField(max_length=64, verbose_name=_("动作"))
    level = models.CharField(max_length=16, choices=LogLevel.choices, default=LogLevel.INFO, verbose_name=_("级别"))
    actor = models.ForeignKey("organization.Lawyer", on_delete=models.PROTECT, related_name="finance_logs", verbose_name=_("操作者"))
    payload = models.JSONField(default=dict, blank=True, verbose_name=_("数据"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("财务日志")
        verbose_name_plural = _("财务日志")
        indexes = [
            models.Index(fields=["contract", "created_at"]),
            models.Index(fields=["level"]),
        ]

    def __str__(self):
        return f"{self.contract_id}-{self.action}-{self.level}"


class ContractReminderType(models.TextChoices):
    HEARING = "hearing", _("开庭")
    ASSET_PRESERVATION = "asset_preservation", _("财产保全")
    EVIDENCE_DEADLINE = "evidence_deadline", _("举证期限")
    STATUTE_LIMITATIONS = "statute_limitations", _("时效")
    APPEAL_PERIOD = "appeal_period", _("上诉期")
    OTHER = "other", _("其他")


class ContractReminder(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="reminders", verbose_name=_("合同"))
    kind = models.CharField(max_length=32, choices=ContractReminderType.choices, verbose_name=_("类型"))
    content = models.CharField(max_length=255, verbose_name=_("提醒事项"))
    due_date = models.DateField(verbose_name=_("到期日期"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("重要日期提醒")
        verbose_name_plural = _("重要日期提醒")

    def __str__(self):
        return f"{self.contract_id}-{self.kind}-{self.due_date}"


class SupplementaryAgreement(models.Model):
    """补充协议模型"""
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="supplementary_agreements",
        verbose_name=_("合同")
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("补充协议名称")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("创建时间")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("修改时间")
    )

    class Meta:
        verbose_name = _("补充协议")
        verbose_name_plural = _("补充协议")
        indexes = [
            models.Index(fields=["contract", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.contract.name} - {self.name or '未命名补充协议'}"


class SupplementaryAgreementParty(models.Model):
    """补充协议当事人模型"""
    supplementary_agreement = models.ForeignKey(
        SupplementaryAgreement,
        on_delete=models.CASCADE,
        related_name="parties",
        verbose_name=_("补充协议")
    )
    client = models.ForeignKey(
        "client.Client",
        on_delete=models.CASCADE,
        related_name="supplementary_agreements",
        verbose_name=_("当事人")
    )
    role = models.CharField(
        max_length=16,
        choices=PartyRole.choices,
        default=PartyRole.PRINCIPAL,
        verbose_name=_("身份")
    )

    class Meta:
        unique_together = ("supplementary_agreement", "client")
        verbose_name = _("补充协议当事人")
        verbose_name_plural = _("补充协议当事人")

    def __str__(self):
        return f"{self.supplementary_agreement_id}-{self.client_id}-{self.role}"
