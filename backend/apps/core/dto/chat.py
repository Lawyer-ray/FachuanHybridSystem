"""群聊相关 DTO"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ChatResult:
    """群聊操作结果"""

    success: bool
    chat_id: str | None = None
    chat_name: str | None = None
    message: str | None = None
    error_code: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class MessageContent:
    """消息内容"""

    title: str
    text: str
    file_path: str | None = None
