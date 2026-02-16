"""Module for retry download."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetryDownloadUsecase:
    court_sms_service: Any

    def execute(self, *, sms_id: int) -> Any:
        return self.court_sms_service.retry_processing(sms_id)
