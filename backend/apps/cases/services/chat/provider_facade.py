"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ChatCreationException, MessageSendException
from apps.core.enums import ChatPlatform

logger = logging.getLogger(__name__)


class ChatProviderFacade:
    def __init__(self, *, factory: Any | None = None) -> None:
        if factory is None:
            from apps.cases.dependencies import get_chat_provider_factory

            factory = get_chat_provider_factory()
        self.factory = factory

    def get_provider_for_creation(self, *, platform: ChatPlatform) -> Any:
        try:
            provider = self.factory.get_provider(platform)
        except Exception as e:
            raise ChatCreationException(
                message=_("无法获取群聊提供者: %(platform)s") % {"platform": platform.label},
                code="PROVIDER_UNAVAILABLE",
                platform=platform.value,
                errors={"original_error": str(e)},
            ) from e

        if not provider.is_available():
            raise ChatCreationException(
                message=_("群聊平台不可用: %(platform)s") % {"platform": platform.label},
                code="PROVIDER_NOT_AVAILABLE",
                platform=platform.value,
                errors={"platform_status": "配置不完整或服务不可用"},
            )
        return provider

    def get_provider_for_messaging(self, *, platform: ChatPlatform, chat_id: str) -> Any:
        try:
            provider = self.factory.get_provider(platform)
        except Exception as e:
            raise MessageSendException(
                message=_("无法获取群聊提供者: %(platform)s") % {"platform": platform.label},
                code="PROVIDER_UNAVAILABLE",
                platform=platform.value,
                chat_id=chat_id,
                errors={"original_error": str(e)},
            ) from e
        return provider

    def try_get_chat_name(self, *, platform: ChatPlatform, chat_id: str) -> Any:
        try:
            provider = self.factory.get_provider(platform)
            if not provider.is_available():
                return None
            result = provider.get_chat_info(chat_id)
            if result.success and result.chat_name:
                return result.chat_name
            return None
        except Exception:
            logger.debug(
                "try_get_chat_name_failed", exc_info=True, extra={"platform": platform.value, "chat_id": chat_id}
            )
            return None

    def create_chat(self, *, provider: Any, chat_name: str, owner_id: str | None) -> Any:
        return provider.create_chat(chat_name, owner_id)

    def send_message(self, *, provider: Any, chat_id: str, content: Any) -> Any:
        return provider.send_message(chat_id, content)

    def send_file(self, *, provider: Any, chat_id: str, file_path: str) -> Any:
        return provider.send_file(chat_id, file_path)
