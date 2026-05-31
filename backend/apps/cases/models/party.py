"""Module for party."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.core.models.enums import LegalStatus

from .case import Case

class CaseParty(models.Model):
    id: int
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="parties", verbose_name="案件")
    client = models.ForeignKey(
        "client.Client", on_delete=models.CASCADE, related_name="case_parties", verbose_name="当事人"
    )
    legal_status = models.CharField(
        max_length=32, choices=LegalStatus.choices, blank=True, null=True, verbose_name="诉讼地位"
    )

    class Meta:
        unique_together: ClassVar[tuple[tuple[str, str], ...]] = (("case", "client"),)
        verbose_name = "案件当事人"
        verbose_name_plural = "案件当事人"
        indexes: ClassVar = [
            models.Index(fields=["client"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}-{self.client_id}-{self.legal_status}"

class CaseAssignment(models.Model):
    id: int
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="assignments", verbose_name="案件")
    lawyer = models.ForeignKey(
        "organization.Lawyer", on_delete=models.CASCADE, related_name="case_assignments", verbose_name="律师"
    )

    class Meta:
        unique_together: ClassVar[tuple[tuple[str, str], ...]] = (("case", "lawyer"),)
        verbose_name = "案件指派"
        verbose_name_plural = "案件指派"
        indexes: ClassVar = [
            models.Index(fields=["lawyer"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}-{self.lawyer_id}"

class CaseAccessGrant(models.Model):
    id: int
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="access_grants", verbose_name="案件")
    grantee = models.ForeignKey(
        "organization.Lawyer", on_delete=models.CASCADE, related_name="case_access_grants", verbose_name="获授权律师"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together: ClassVar[tuple[tuple[str, str], ...]] = (("case", "grantee"),)
        verbose_name = "案件访问授权"
        verbose_name_plural = "案件访问授权"
        indexes: ClassVar = [
            models.Index(fields=["grantee"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}->{self.grantee_id}"
