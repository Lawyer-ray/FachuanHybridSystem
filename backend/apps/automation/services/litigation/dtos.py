"""Data transfer objects."""

from pydantic import BaseModel, Field


class CourtPleadingSignals(BaseModel):
    has_complaint: bool = Field(default=False)
    has_defense: bool = Field(default=False)
    has_counterclaim: bool = Field(default=False)
    has_counterclaim_defense: bool = Field(default=False)
    notes: str = Field(default="")
