"""Data repository layer."""

from __future__ import annotations

from apps.cases.models import CaseAccessGrant


class CaseAccessRepo:
    def get_user_extra_case_access(self, user_id: int) -> list[int]:
        return list(CaseAccessGrant.objects.filter(grantee_id=user_id).values_list("case_id", flat=True))
