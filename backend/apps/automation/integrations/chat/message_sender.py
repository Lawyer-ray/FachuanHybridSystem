"""External service integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from apps.automation.services.chat.base import ChatResult, MessageContent
from apps.core.models.enums import ChatPlatform


class ChatMessageSender(Protocol):
    def send_text(self, *, platform: ChatPlatform, chat_id: str, text: str) -> ChatResult: ...


@dataclass(frozen=True)
class ChatProviderMessageSender:
    def send_text(self, *, platform: ChatPlatform, chat_id: str, text: str) -> ChatResult:
        from apps.automation.services.chat.factory import ChatProviderFactory

        provider = ChatProviderFactory.get_provider(platform)
        return provider.send_message(
            chat_id,
            MessageContent(
                title="",
                text=text,
                file_path=None,
            ),
        )
