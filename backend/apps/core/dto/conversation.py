"""Module for conversation."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ConversationHistoryDTO:
    id: int
    session_id: str
    user_id: str
    role: str
    content: str
    metadata: dict[str, Any]
    created_at: Any
    litigation_session_id: int | None = None
    step: str = ""
