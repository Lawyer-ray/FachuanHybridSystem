"""Module for party."""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import models

from .contract import Contract

logger = logging.getLogger(__name__)


class PartyRole(models.TextChoices):
    """当事人身份"""

    PRINCIPAL = "PRINCIPAL", "委托人"
    BENEFICIARY = "BENEFICIARY", "受益人"
    OPPOSING = "OPPOSING", "对方当事人"


class ContractParty(models.Model):
    id: int
    contract_id: int
    client_id: int
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="contract_parties", verbose_name="合同"
    )
    client = models.ForeignKey(
        "client.Client", on_delete=models.CASCADE, related_name="contracts", verbose_name="当事人"
    )
    role = models.CharField(max_length=16, choices=PartyRole.choices, default=PartyRole.PRINCIPAL, verbose_name="身份")

    class Meta:
        unique_together = ("contract", "client")
        verbose_name = "合同当事人"
        verbose_name_plural = "合同当事人"
        indexes: ClassVar = [
            models.Index(fields=["client"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract_id}-{self.client_id}-{self.role}"

    def save(self, *args: object, **kwargs: object) -> None:
        """保存前自动校正 role：非我方当事人的 role 不应为 PRINCIPAL。

        防止因前端 JS 未触发、API 直接创建、或 add_party 未传 role
        等场景导致对方当事人被错误标记为 PRINCIPAL（甲方）。
        """
        if self.client_id and self.role == PartyRole.PRINCIPAL:
            # 访问 client.is_our_client，若 client 未加载则跳过
            try:
                is_our = self.client.is_our_client
            except Exception:
                is_our = None
            if is_our is False:
                logger.warning(
                    "ContractParty.role 自动校正: contract=%s, client=%s, PRINCIPAL→OPPOSING（is_our_client=False）",
                    self.contract_id,
                    self.client_id,
                )
                self.role = PartyRole.OPPOSING
        super().save(*args, **kwargs)


class ContractAssignment(models.Model):
    id: int
    contract_id: int
    lawyer_id: int
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="assignments", verbose_name="合同")
    lawyer = models.ForeignKey(
        "organization.Lawyer", on_delete=models.CASCADE, related_name="contract_assignments", verbose_name="律师"
    )
    is_primary = models.BooleanField(default=False, verbose_name="是否主办律师")
    order = models.IntegerField(default=0, verbose_name="排序")

    class Meta:
        verbose_name = "合同指派"
        verbose_name_plural = "合同指派"
        unique_together = ("contract", "lawyer")
        indexes: ClassVar = [models.Index(fields=["lawyer"])]
        ordering: ClassVar = ["-is_primary", "order"]

    def __str__(self) -> str:
        return f"{self.contract_id}-{self.lawyer_id}"
