"""Module for supplementary."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .contract import Contract
from .party import PartyRole

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


class SupplementaryAgreement(models.Model):
    """补充协议模型"""

    id: int
    contract_id: int
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="supplementary_agreements", verbose_name=_("合同")
    )
    name = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("补充协议名称"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("修改时间"))

    if TYPE_CHECKING:
        parties: RelatedManager[SupplementaryAgreementParty]

    class Meta:
        verbose_name = _("补充协议")
        verbose_name_plural = _("补充协议")
        indexes: ClassVar = [
            models.Index(fields=["contract", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract.name} - {self.name or '未命名补充协议'}"


class SupplementaryAgreementParty(models.Model):
    """补充协议当事人模型"""

    id: int
    supplementary_agreement_id: int
    client_id: int
    supplementary_agreement = models.ForeignKey(
        SupplementaryAgreement, on_delete=models.CASCADE, related_name="parties", verbose_name=_("补充协议")
    )
    client = models.ForeignKey(
        "client.Client", on_delete=models.CASCADE, related_name="supplementary_agreements", verbose_name=_("当事人")
    )
    role = models.CharField(
        max_length=16, choices=PartyRole.choices, default=PartyRole.PRINCIPAL, verbose_name=_("身份")
    )

    class Meta:
        unique_together = ("supplementary_agreement", "client")
        verbose_name = _("补充协议当事人")
        verbose_name_plural = _("补充协议当事人")

    def __str__(self) -> str:
        return f"{self.supplementary_agreement_id}-{self.client_id}-{self.role}"
