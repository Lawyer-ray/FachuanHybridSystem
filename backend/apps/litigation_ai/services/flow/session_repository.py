"""Data repository layer."""

from __future__ import annotations

"""诉讼 AI 会话仓储层,封装 LitigationSession 的数据库操作."""

from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from django.db import transaction

if TYPE_CHECKING:
    from apps.litigation_ai.models import LitigationSession


class LitigationSessionRepository:
    def _model(self) -> type[LitigationSession]:
        from apps.litigation_ai.models import LitigationSession

        return LitigationSession

    def get_session_sync(self, session_id: str) -> Any:  # pragma: no cover
        return self._model().objects.filter(session_id=session_id).first()

    def get_session_with_case_sync(self, session_id: str) -> Any:  # pragma: no cover
        return self._model().objects.filter(session_id=session_id).select_related("case").first()

    def get_session_for_update_sync(self, session_id: str) -> Any:
        return self._model().objects.select_for_update().filter(session_id=session_id).first()

    def list_sessions_sync(self, *, filters: dict[str, Any], page: int = 1, page_size: int = 20) -> dict[str, Any]:
        from apps.core.api.pagination import paginate_queryset

        qs = self._model().objects.filter(**(filters or {})).order_by("-created_at")
        return paginate_queryset(qs, page=page, page_size=page_size)

    async def get_session(self, session_id: str) -> Any:  # pragma: no cover
        model = self._model()
        return await sync_to_async(
            model.objects.filter(session_id=session_id).first,
            thread_sensitive=True,
        )()

    async def get_session_or_raise(self, session_id: str) -> Any:  # pragma: no cover
        model = self._model()
        return await sync_to_async(model.objects.get, thread_sensitive=True)(session_id=session_id)

    async def get_metadata(self, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        return (session.metadata or {}) if session else {}

    def _update_metadata_locked_sync(self, session_id: str, patch: dict[str, Any]) -> Any:
        """锁内读改写 metadata：select_for_update 行锁串行化并发 RMW。

        无锁版本「先读 metadata → 内存合并 → update 整列」在并发下后写覆盖先写
        （丢更新）；行锁保证读到的是最新已提交值且写入互斥。
        """
        with transaction.atomic():
            session = self.get_session_for_update_sync(session_id)
            if not session:
                return None
            metadata = session.metadata or {}
            metadata.update(patch)
            session.metadata = metadata
            session.save(update_fields=["metadata"])
            return session

    async def update_metadata(self, session_id: str, patch: dict[str, Any]) -> None:  # pragma: no cover
        await sync_to_async(self._update_metadata_locked_sync, thread_sensitive=True)(session_id, patch)

    async def update_metadata_or_raise(self, session_id: str, patch: dict[str, Any]) -> None:  # pragma: no cover
        def _run() -> None:
            locked = self._update_metadata_locked_sync(session_id, patch)
            if locked is None:
                # 与 get_session_or_raise 同语义：查无此会话时抛 DoesNotExist
                raise self._model().DoesNotExist("LitigationSession matching query does not exist.")

        await sync_to_async(_run, thread_sensitive=True)()

    async def set_document_type(self, session_id: str, document_type: str) -> None:  # pragma: no cover
        def _run() -> None:
            with transaction.atomic():
                session = self.get_session_for_update_sync(session_id)
                if not session:
                    return
                session.document_type = document_type
                session.save(update_fields=["document_type"])

        await sync_to_async(_run, thread_sensitive=True)()

    async def set_step(self, session_id: str, step_value: str) -> None:
        session = await self.get_session(session_id)
        if not session:
            return
        await self.update_metadata(session_id, {"current_step": step_value})

    async def get_step_value(self, session_id: str) -> str | None:
        metadata = await self.get_metadata(session_id)
        return metadata.get("current_step")

    def get_step_value_sync(self, session_id: str) -> str | None:
        session = self.get_session_sync(session_id)
        metadata = (session.metadata or {}) if session else {}
        return metadata.get("current_step")

    def set_step_sync(self, session_id: str, step_value: str) -> None:  # pragma: no cover
        # 与 _update_metadata_locked_sync 同型的锁内 RMW（current_step 是 metadata 的一个键）
        with transaction.atomic():
            session = self.get_session_for_update_sync(session_id)
            if not session:
                return
            metadata = session.metadata or {}
            metadata["current_step"] = step_value
            session.metadata = metadata
            session.save(update_fields=["metadata"])
