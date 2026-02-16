"""Module for submission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SubmitSmsUsecase:
    court_sms_service: Any

    def execute(self, *, content: str, received_at: datetime | None = None) -> Any:
        return self.court_sms_service.submit_sms(content=content, received_at=received_at)


@dataclass(frozen=True)
class AssignCaseUsecase:
    court_sms_service: Any

    def execute(self, *, sms_id: int, case_id: int) -> Any:
        return self.court_sms_service.assign_case(sms_id=sms_id, case_id=case_id)
