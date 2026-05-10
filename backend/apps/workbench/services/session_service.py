"""工作台会话服务"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Count, F, OuterRef, Subquery
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.security.permissions import AccessContext, PermissionMixin

from ..models import WorkbenchMessage, WorkbenchSession

logger = logging.getLogger(__name__)


def _calc_message_bytes(
    content: str = "",
    tool_input: dict | None = None,
    tool_output: dict | None = None,
    metadata: dict | None = None,
) -> int:
    """Calculate UTF-8 byte size of a message's variable-size fields."""
    total = len((content or "").encode("utf-8"))
    total += len(str(tool_input or {}).encode("utf-8"))
    total += len(str(tool_output or {}).encode("utf-8"))
    total += len(str(metadata or {}).encode("utf-8"))
    return total


class WorkbenchSessionService(PermissionMixin):
    """工作台会话管理服务"""

    def create_session(
        self,
        *,
        title: str = "",
        llm_model: str = "",
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> WorkbenchSession:
        """创建工作台会话"""
        return WorkbenchSession.objects.create(
            user=user if user and getattr(user, "is_authenticated", False) else None,
            title=title,
            llm_model=llm_model,
        )

    def list_sessions(
        self,
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """获取当前用户的工作台会话列表"""
        if not user or not getattr(user, "is_authenticated", False):
            return {"items": [], "count": 0}

        qs = WorkbenchSession.objects.filter(user=user).order_by("-updated_at")

        offset = (page - 1) * page_size
        total = qs.count()

        last_msg_subquery = (
            WorkbenchMessage.objects.filter(session_id=OuterRef("id"), role="assistant")
            .order_by("-created_at")
            .values("content")[:1]
        )
        items = list(
            qs[offset : offset + page_size].annotate(
                _last_msg=Subquery(last_msg_subquery),
            )
        )

        session_ids = [item.id for item in items]
        message_stats: dict[int, dict[str, int]] = {}
        if session_ids:
            # 单次查询获取所有消息的统计信息（避免 N+1）
            stats = (
                WorkbenchMessage.objects.filter(session_id__in=session_ids)
                .values("session_id")
                .annotate(message_count=Count("id"))
            )
            count_map: dict[int, int] = {s["session_id"]: s["message_count"] for s in stats}

            for sid in session_ids:
                message_stats[sid] = {
                    "message_count": count_map.get(sid, 0),
                }

        result = []
        for item in items:
            from ..schemas import SessionOut

            data = SessionOut.model_validate(item).model_dump()
            raw = getattr(item, "_last_msg", None) or ""
            data["last_message_preview"] = raw[:50] if raw else ""
            session_stats = message_stats.get(item.id, {"message_count": 0})
            data["message_count"] = session_stats["message_count"]
            data["storage_bytes"] = item.storage_bytes
            result.append(data)

        return {"items": result, "count": total}

    def get_session(
        self,
        session_id: int,
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> WorkbenchSession:
        """获取会话详情"""
        return self.get_user_session(user, session_id)

    def update_session(
        self,
        session_id: int,
        *,
        title: str | None = None,
        llm_model: str | None = None,
        status: str | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> WorkbenchSession:
        """更新会话"""
        session = self.get_user_session(user, session_id)
        if title is not None:
            session.title = title
        if llm_model is not None:
            session.llm_model = llm_model
        if status is not None:
            session.status = status
        session.save()
        return session

    def delete_session(
        self,
        session_id: int,
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        """删除会话"""
        session = self.get_user_session(user, session_id)
        session.delete()

    def get_user_session(self, user: Any, session_id: int) -> WorkbenchSession:
        """获取用户的会话，不存在或无权限时抛 NotFoundError"""
        try:
            return WorkbenchSession.objects.get(id=session_id, user=user)
        except WorkbenchSession.DoesNotExist:
            raise NotFoundError(_("会话不存在")) from None

    @staticmethod
    def increment_storage(session_id: int, delta: int) -> None:
        """Atomically update session storage_bytes."""
        if delta:
            from ..models import WorkbenchSession

            WorkbenchSession.objects.filter(id=session_id).update(
                storage_bytes=F("storage_bytes") + delta,
            )

    @staticmethod
    async def aincrement_storage(session_id: int, delta: int) -> None:
        """Async version for use in async contexts."""
        if delta:
            from ..models import WorkbenchSession

            await WorkbenchSession.objects.filter(id=session_id).aupdate(
                storage_bytes=F("storage_bytes") + delta,
            )
