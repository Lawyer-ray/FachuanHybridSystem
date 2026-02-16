"""Business logic services."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ConversationStep(str, Enum):
    INIT = "init"
    DOCUMENT_TYPE = "document_type"
    DOC_PLAN = "doc_plan"
    LITIGATION_GOAL = "litigation_goal"
    EVIDENCE_SELECTION = "evidence_selection"
    GENERATING = "generating"
    REFINING = "refining"
    COMPLETED = "completed"


@dataclass
class FlowContext:
    session_id: str
    case_id: int
    user_id: int
    current_step: ConversationStep
    document_type: str | None = None
    litigation_goal: str | None = None
    evidence_list_ids: list[int] | None = None
    evidence_item_ids: list[int] | None = None
    metadata: dict[str, Any] | None = None
