"""Business logic services."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.utils import timezone

from apps.core.error_catalog import case_not_found

from .types import LitigationCaseDetails


class LitigationCaseDetailsAccessor:
    def __init__(self, case_service: Any | None = None) -> None:
        self._case_service = case_service
        self._case_details_cache: dict[int, LitigationCaseDetails | None] = {}

    @property
    def case_service(self) -> Any:
        if self._case_service is None:
            from apps.documents.services.infrastructure.wiring import get_case_service

            self._case_service = get_case_service()
        return self._case_service

    def get_case_details(self, *, case_id: int) -> Any:
        if case_id in self._case_details_cache:
            return self._case_details_cache[case_id]
        case_details = self.case_service.get_case_with_details_internal(case_id)
        self._case_details_cache[case_id] = case_details
        return case_details

    def require_case_details(self, *, case_id: int) -> Any:
        case_details = self.get_case_details(case_id=case_id)
        if not case_details:
            raise case_not_found(case_id=case_id)
        return case_details

    def get_case_parties(self, *, case_id: int) -> list[dict[str, Any]]:
        case_details = self.require_case_details(case_id=case_id)
        return case_details.get("case_parties", []) or []

    def _coerce_date(self, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            for parser in (datetime.fromisoformat, lambda s: datetime.strptime(s, "%Y-%m-%d")):
                try:
                    return parser(value).date()
                except ValueError:
                    continue
        return None

    def get_formatted_date(self, *, case_id: int) -> str:
        case_details = self.require_case_details(case_id=case_id)
        specified_date = self._coerce_date(case_details.get("specified_date"))
        date_obj = specified_date or timezone.localdate()
        return date_obj.strftime("%Y年%m月%d日")
