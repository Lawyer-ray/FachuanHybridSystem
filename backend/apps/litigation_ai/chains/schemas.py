"""API schemas and serializers."""

from pydantic import BaseModel, Field


class EvidenceCitation(BaseModel):
    evidence_item_id: int | None = Field(default=None)
    evidence_name: str = Field(default="")
    pages: str = Field(default="")
    used_in: str = Field(default="")


class ComplaintDraft(BaseModel):
    litigation_request: str = Field(description="诉讼请求")
    facts_and_reasons: str = Field(description="事实与理由")
    evidence_citations: list[EvidenceCitation] = Field(default_factory=list)


class DefenseDraft(BaseModel):
    defense_opinion: str = Field(default="", description="答辩意见")
    defense_reason: str = Field(description="答辩理由")
    rebuttal_to_opponent_evidence: list[str] = Field(default_factory=list)
    evidence_citations: list[EvidenceCitation] = Field(default_factory=list)
