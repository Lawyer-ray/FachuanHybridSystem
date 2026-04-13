"""Module for process sms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProcessSmsUsecase:
    court_sms_service: Any

    def execute(self, *, sms_id: int, process_options: dict[str, Any] | None = None) -> Any:
        return self.court_sms_service.process_sms(sms_id, process_options=process_options)


@dataclass(frozen=True)
class ProcessSmsFromMatchingUsecase:
    court_sms_service: Any

    def execute(self, *, sms_id: int) -> Any:
        return self.court_sms_service._process_from_matching(sms_id)


@dataclass(frozen=True)
class ProcessSmsFromRenamingUsecase:
    court_sms_service: Any

    def execute(self, *, sms_id: int) -> Any:
        return self.court_sms_service._process_from_renaming(sms_id)
