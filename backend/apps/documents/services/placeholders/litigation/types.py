"""Business logic services."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, NotRequired, TypedDict


class LitigationCaseDetails(TypedDict, total=False):
    specified_date: date | datetime | str | None
    case_parties: NotRequired[list[dict[str, Any]]]
