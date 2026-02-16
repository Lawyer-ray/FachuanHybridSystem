"""API schemas and serializers."""

from pydantic import BaseModel, Field


class GoalRequestItem(BaseModel):
    description: str = Field(default="")
    amount: str | None = Field(default=None)
    target: str | None = Field(default=None)
    period: str | None = Field(default=None)


class GoalIntakeResult(BaseModel):
    goal_text: str = Field(default="")
    requests: list[GoalRequestItem] = Field(default_factory=list)
    need_clarification: bool = Field(default=False)
    clarifying_question: str = Field(default="")


class UserChoiceResult(BaseModel):
    primary_document_type: str = Field(default="")
    pending_document_types: list[str] = Field(default_factory=list)
    notes: str = Field(default="")
