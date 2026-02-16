"""Business logic services."""

from __future__ import annotations

"""
会话共享数据模型

定义 SessionDTO 和 MessageDTO,供 session_lifecycle_service 和 session_message_service 共享.
"""


from dataclasses import dataclass
from typing import Any


@dataclass
class SessionDTO:
    id: int
    session_id: str
    case_id: int
    case_name: str
    user_id: int | None
    document_type: str
    status: str
    metadata: dict[str, Any]
    created_at: Any
    updated_at: Any


@dataclass
class MessageDTO:
    id: int
    session_id: str
    role: str
    content: str
    metadata: dict[str, Any]
    created_at: Any
