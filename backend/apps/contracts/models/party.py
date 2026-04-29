"""Module for party."""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .contract import Contract


class PartyRole(models.TextChoices):
    """当事人身份"""

    PRINCIPAL = "PRINCIPAL", _("委托人")
    BENEFICIARY = "BENEFICIARY", _("受益人")
    OPPOSING = "OPPOSING", _("对方当事人")


class ContractParty(models.Model):
    id: int
    contract_id: int
    client_id: int
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="contract_parties", verbose_name=_("合同")
    )
    client = models.ForeignKey(
        "client.Client", on_delete=models.CASCADE, related_name="contracts", verbose_name=_("当事人")
    )
    role = models.CharField(
        max_length=16, choices=PartyRole.choices, default=PartyRole.PRINCIPAL, verbose_name=_("身份")
    )

    class Meta:
        unique_together = ("contract", "client")
        verbose_name = _("合同当事人")
        verbose_name_plural = _("合同当事人")
        indexes: ClassVar = [
            models.Index(fields=["client"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract_id}-{self.client_id}-{self.role}"


class ContractAssignment(models.Model):
    id: int
    contract_id: int
    lawyer_id: int
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="assignments", verbose_name=_("合同"))
    lawyer = models.ForeignKey(
        "organization.Lawyer", on_delete=models.CASCADE, related_name="contract_assignments", verbose_name=_("律师")
    )
    is_primary = models.BooleanField(default=False, verbose_name=_("是否主办律师"))
    order = models.IntegerField(default=0, verbose_name=_("排序"))

    class Meta:
        verbose_name = _("合同指派")
        verbose_name_plural = _("合同指派")
        unique_together = ("contract", "lawyer")
        ordering: ClassVar = ["-is_primary", "order"]

    def __str__(self) -> str:
        return f"{self.contract_id}-{self.lawyer_id}"
