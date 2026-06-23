"""工作台消息服务"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.security.permissions import AccessContext, PermissionMixin

from ..models import WorkbenchMessage, WorkbenchSession
from .session_service import WorkbenchSessionService, _calc_message_bytes

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
        before_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """获取会话的消息列表

        Args:
            before_id: 游标分页——返回该 ID 之前的消息（用于向上滚动加载历史）
        """
        self._session_service.get_user_session(user, session_id)
        qs = WorkbenchMessage.objects.filter(session_id=session_id)

        if before_id is not None:
            try:
                ref_msg = WorkbenchMessage.objects.get(id=before_id, session_id=session_id)
            except WorkbenchMessage.DoesNotExist:
                return {"items": [], "count": 0, "has_more": False}
            qs = qs.filter(created_at__lt=ref_msg.created_at)
            total = qs.count()
            items = list(qs.order_by("-created_at")[: page_size + 1])
            items.reverse()
            return {
                "items": [self._message_to_dict(item) for item in items[:page_size]],
                "count": total,
                "has_more": len(items) > page_size,
            }

        # 原有 page-based 分页逻辑
        qs = qs.order_by("created_at")
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
    ) -> None:  # pragma: no cover
        """删除指定消息及其之后的所有消息（用于编辑重发）"""
        self._session_service.get_user_session(user, session_id)
        try:
            msg = WorkbenchMessage.objects.get(id=message_id, session_id=session_id)
        except WorkbenchMessage.DoesNotExist:
            raise NotFoundError("消息不存在") from None
        WorkbenchMessage.objects.filter(
            session_id=session_id,
            created_at__gte=msg.created_at,
        ).delete()
        # 重新计算 storage_bytes（删除是低频操作，全量重算可接受）
        # 用 values() 只取 4 列，避免加载完整 model 实例
        remaining_bytes = sum(
            _calc_message_bytes(m["content"], m["tool_input"], m["tool_output"], m["metadata"])
            for m in WorkbenchMessage.objects.filter(session_id=session_id).values(
                "content", "tool_input", "tool_output", "metadata"
            )
        )
        WorkbenchSession.objects.filter(id=session_id).update(storage_bytes=remaining_bytes)

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
                "rating 必须是 good 或 bad",
                errors={"rating": f"无效的 rating 值: {rating}"},
            )

        try:
            msg = WorkbenchMessage.objects.get(id=message_id)
        except WorkbenchMessage.DoesNotExist:
            raise NotFoundError("消息不存在") from None

        self._session_service.get_user_session(user, msg.session_id)

        old_meta = dict(msg.metadata or {})
        meta = dict(old_meta)
        meta["feedback"] = {"rating": rating, "comment": comment}
        msg.metadata = meta
        msg.save(update_fields=["metadata"])
        # 更新 storage_bytes（仅 metadata 变化）
        delta = _calc_message_bytes(metadata=meta) - _calc_message_bytes(metadata=old_meta)
        WorkbenchSessionService.increment_storage(msg.session_id, delta)

    @staticmethod
    def _message_to_dict(msg: WorkbenchMessage) -> dict[str, Any]:
        """将消息转换为字典"""
        from ..schemas import MessageOut

        return MessageOut.model_validate(msg).model_dump()
