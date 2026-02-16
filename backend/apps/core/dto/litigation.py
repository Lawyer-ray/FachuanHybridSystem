"""Module for litigation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CourtPleadingSignalsDTO:
    has_complaint: bool = False
    has_defense: bool = False
    has_counterclaim: bool = False
    has_counterclaim_defense: bool = False
    notes: str = ""
