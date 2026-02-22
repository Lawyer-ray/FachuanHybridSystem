"""Data repository layer."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet


class CaseLogQueryRepo:
    def filter_by_allowed_case_ids(
        self, qs: QuerySet[Any, Any], allowed_case_ids_qs: QuerySet[Any, Any]
    ) -> QuerySet[Any, Any]:
        return qs.filter(case_id__in=allowed_case_ids_qs)
