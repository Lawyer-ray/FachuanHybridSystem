"""Business logic services."""

from __future__ import annotations


from apps.core.dto import CourtPleadingSignalsDTO


class CourtPleadingSignalsServiceAdapter:
    def __init__(self, *, model: str | None = None) -> None:
        from apps.automation.services.litigation.court_pleading_signals_service import CourtPleadingSignalsService

        self._svc = CourtPleadingSignalsService(model=model)

    def get_signals_internal(self, case_id: int) -> CourtPleadingSignalsDTO:
        signals = self._svc.get_signals(case_id)
        return CourtPleadingSignalsDTO(
            has_complaint=bool(getattr(signals, "has_complaint", False)),
            has_defense=bool(getattr(signals, "has_defense", False)),
            has_counterclaim=bool(getattr(signals, "has_counterclaim", False)),
            has_counterclaim_defense=bool(getattr(signals, "has_counterclaim_defense", False)),
            notes=str(getattr(signals, "notes", "") or ""),
        )
