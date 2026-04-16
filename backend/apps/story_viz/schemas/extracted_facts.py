from __future__ import annotations

from pydantic import BaseModel, Field


class FactParty(BaseModel):
    name: str = Field(default="")
    role: str = Field(default="")
    aliases: list[str] = Field(default_factory=list)


class FactEvent(BaseModel):
    sequence: int = Field(default=0)
    time_label: str = Field(default="")
    summary: str = Field(default="")
    participants: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)


class FactRelationship(BaseModel):
    source: str = Field(default="")
    target: str = Field(default="")
    relation_type: str = Field(default="")


class ExtractedFacts(BaseModel):
    case_title: str = Field(default="")
    parties: list[FactParty] = Field(default_factory=list)
    events: list[FactEvent] = Field(default_factory=list)
    relationships: list[FactRelationship] = Field(default_factory=list)
    judgment_result: str = Field(default="")
    confidence_notes: str = Field(default="")
