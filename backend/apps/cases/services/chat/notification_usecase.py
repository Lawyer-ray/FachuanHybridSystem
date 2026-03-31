"""Business logic services."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.models.enums import ChatPlatform
from apps.core.exceptions import MessageSendException

from .provider_facade import ChatProviderFacade
from .recreate_policy import ChatRecreatePolicy
from .repo import CaseChatRepository

logger = logging.getLogger(__name__)


class SendNotificationUsecase:
    def __init__(
        self,
        *,
        repo: CaseChatRepository,
        provider_facade: ChatProviderFacade,
        recreate_policy: ChatRecreatePolicy,
        chat_creator: Callable[[int, ChatPlatform], Any],
    ) -> None:
        self.repo = repo
        self.provider_facade = provider_facade
        self.recreate_policy = recreate_policy
        self.chat_creator = chat_creator

    def execute(
        self,
        *,
        case_id: int,
        platform: ChatPlatform,
        chat: Any,
        content: Any,
        document_paths: list[str] | None,
    ) -> Any:
        provider = self.provider_facade.get_provider_for_messaging(platform=platform, chat_id=chat.chat_id)
        result = self.provider_facade.send_message(provider=provider, chat_id=chat.chat_id, content=content)

        if not result.success and self.recreate_policy.should_recreate(result=result):
            logger.warning("群聊可能已解散,尝试创建新群聊: chat_id=%s", chat.chat_id)
            self.repo.mark_inactive(case_chat=chat)
            try:
                new_chat = self.chat_creator(case_id, platform)
                result = self.provider_facade.send_message(provider=provider, chat_id=new_chat.chat_id, content=content)
                chat = new_chat
            except Exception as retry_error:
                raise MessageSendException(
                    message=_("群聊已解散,重新创建群聊失败: %(error)s") % {"error": str(retry_error)},
                    code="CHAT_RECREATE_FAILED",
                    platform=platform.value,
                    chat_id=chat.chat_id,
                    error_code=result.error_code,
                    errors={
                        "original_error": result.message,
                        "retry_error": str(retry_error),
                        "provider_response": result.raw_response,
                    },
                ) from retry_error

        if not result.success:
            raise MessageSendException(
                message=result.message or "消息发送失败",
                code="MESSAGE_SEND_FAILED",
                platform=platform.value,
                chat_id=chat.chat_id,
                error_code=result.error_code,
                errors={"provider_response": result.raw_response, "content_title": content.title},
            )

        if document_paths:
            successful_files = 0
            failed_files = 0
            for file_path in document_paths:
                try:
                    file_result = self.provider_facade.send_file(
                        provider=provider, chat_id=chat.chat_id, file_path=file_path
                    )
                    if file_result.success:
                        successful_files += 1
                    else:
                        failed_files += 1
                except Exception:
                    logger.exception("操作失败")

                    failed_files += 1

            if successful_files == len(document_paths):
                result.message = str(_("消息和所有文件发送成功 (%(count)s 个文件)") % {"count": successful_files})
            elif successful_files > 0:
                result.message = str(
                    _("消息发送成功,部分文件发送成功 (%(ok)s/%(total)s 个文件)")
                    % {"ok": successful_files, "total": len(document_paths)}
                )
            else:
                result.message = str(_("消息发送成功,但所有文件发送失败 (%(count)s 个文件)") % {"count": failed_files})

        return result
