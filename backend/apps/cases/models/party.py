"""Module for party."""

from typing import Any

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import LegalStatus

from .case import Case


class CaseParty(models.Model):
    id: int
    case: Any = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="parties", verbose_name=_("案件"))
    id: int
    client: Any = models.ForeignKey(
        "client.Client", on_delete=models.CASCADE, related_name="case_parties", verbose_name=_("当事人")
    )
    legal_status: Any = models.CharField(
        max_length=32, choices=LegalStatus.choices, blank=True, null=True, verbose_name=_("诉讼地位")
    )

    class Meta:
        unique_together: tuple[Any, ...] = ("case", "client")
        verbose_name = _("案件当事人")
        verbose_name_plural = _("案件当事人")

    def __str__(self) -> str:
        return f"{self.case_id}-{self.client_id}-{self.legal_status}"


class CaseAssignment(models.Model):
    id: int
    case_id: int  # 外键ID字段
    case_id: int  # 外键ID字段
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="assignments", verbose_name=_("案件"))
    id: int
    lawyer = models.ForeignKey(
        "organization.Lawyer", on_delete=models.CASCADE, related_name="case_assignments", verbose_name=_("律师")
    )

    class Meta:
        verbose_name = _("案件指派")
        verbose_name_plural = _("案件指派")

    def __str__(self) -> None:
        return f"{self.case_id}-{self.lawyer_id}"


class CaseAccessGrant(models.Model):
    id: int
    case_id: int  # 外键ID字段
    case_id: int  # 外键ID字段
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="access_grants", verbose_name=_("案件"))
    id: int
    grantee = models.ForeignKey(
        "organization.Lawyer", on_delete=models.CASCADE, related_name="case_access_grants", verbose_name=_("获授权律师")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("案件访问授权")
        verbose_name_plural = _("案件访问授权")

    def __str__(self) -> None:
        return f"{self.case_id}->{self.grantee_id}"
