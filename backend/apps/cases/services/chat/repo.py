"""Data repository layer."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.cases.models import Case, CaseChat
from apps.core.enums import ChatPlatform
from apps.core.exceptions import NotFoundError, ValidationException


class CaseChatRepository:
    def get_case(self, *, case_id: int) -> Case:
        if not case_id or not isinstance(case_id, int) or case_id <= 0:
            raise ValidationException(
                message=_("无效的案件ID"),
                code="INVALID_CASE_ID",
                errors={"case_id": "案件ID必须是正整数"},
            )
        try:
            return Case.objects.get(id=case_id)
        except ObjectDoesNotExist:
            raise NotFoundError(
                message=_("案件不存在: ID=%(id)s") % {"id": case_id},
                code="CASE_NOT_FOUND",
                errors={"case_id": case_id},
            ) from None

    def get_active_chat(self, *, case_id: int, platform: ChatPlatform) -> CaseChat | None:
        return CaseChat.objects.filter(case_id=case_id, platform=platform, is_active=True).first()

    def mark_inactive(self, *, case_chat: CaseChat) -> None:
        case_chat.is_active = False
        case_chat.save(update_fields=["is_active"])

    def unbind_chat(self, *, chat_id: int) -> bool:
        if not chat_id or not isinstance(chat_id, int) or chat_id <= 0:
            raise ValidationException(
                message=_("无效的群聊ID"),
                code="INVALID_CHAT_ID",
                errors={"chat_id": "群聊ID必须是正整数"},
            )

        updated_count = CaseChat.objects.filter(id=chat_id, is_active=True).update(is_active=False)
        return updated_count > 0

    def ensure_not_bound(self, *, case_id: int, platform: ChatPlatform, chat_id: str) -> None:
        existing = CaseChat.objects.filter(case_id=case_id, platform=platform, chat_id=chat_id, is_active=True).first()
        if existing:
            raise ValidationException(
                message=_("该群聊已绑定到此案件"),
                code="CHAT_ALREADY_BOUND",
                errors={"case_id": case_id, "chat_id": chat_id, "existing_binding_id": existing.id},
            )

    def create_binding(
        self,
        *,
        case: Case,
        platform: ChatPlatform,
        chat_id: str,
        name: str,
        is_active: bool = True,
    ) -> CaseChat:
        with transaction.atomic():
            return CaseChat.objects.create(
                case=case, platform=platform, chat_id=chat_id, name=name, is_active=is_active
            )
