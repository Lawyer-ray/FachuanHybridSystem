"""工作台消息服务"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.security.permissions import AccessContext, PermissionMixin

from ..models import WorkbenchMessage, WorkbenchSession
from .session_service import WorkbenchSessionService

logger = logging.getLogger(__name__)


class WorkbenchMessageService(PermissionMixin):
    """工作台消息管理服务"""

    def __init__(self, session_service: WorkbenchSessionService | None = None) -> None:
        self._session_service = session_service or WorkbenchSessionService()

    def list_messages(
        self,
        session_id: int,
        *,
        page: int = 1,
        page_size: int = 50,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """获取会话的消息列表"""
        self._session_service.get_user_session(user, session_id)
        qs = WorkbenchMessage.objects.filter(session_id=session_id).order_by("created_at")
        offset = (page - 1) * page_size
        total = qs.count()
        items = list(qs[offset : offset + page_size])

        return {
            "items": [self._message_to_dict(item) for item in items],
            "count": total,
        }

    def truncate_messages(
        self,
        session_id: int,
        message_id: int,
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        """删除指定消息及其之后的所有消息（用于编辑重发）"""
        self._session_service.get_user_session(user, session_id)
        try:
            msg = WorkbenchMessage.objects.get(id=message_id, session_id=session_id)
        except WorkbenchMessage.DoesNotExist:
            raise NotFoundError(_("消息不存在")) from None
        WorkbenchMessage.objects.filter(
            session_id=session_id,
            created_at__gte=msg.created_at,
        ).delete()

    def submit_feedback(
        self,
        message_id: int,
        rating: str,
        comment: str = "",
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        """提交消息反馈（好评/差评）"""
        if rating not in ("good", "bad"):
            raise ValidationException(
                _("rating 必须是 good 或 bad"),
                errors={"rating": f"无效的 rating 值: {rating}"},
            )

        try:
            msg = WorkbenchMessage.objects.get(id=message_id)
        except WorkbenchMessage.DoesNotExist:
            raise NotFoundError(_("消息不存在")) from None

        self._session_service.get_user_session(user, msg.session_id)

        meta = dict(msg.metadata or {})
        meta["feedback"] = {"rating": rating, "comment": comment}
        msg.metadata = meta
        msg.save(update_fields=["metadata"])

    @staticmethod
    def _message_to_dict(msg: WorkbenchMessage) -> dict[str, Any]:
        """将消息转换为字典"""
        from ..schemas import MessageOut

        return MessageOut.model_validate(msg).model_dump()
