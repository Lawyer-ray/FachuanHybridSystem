"""Data repository layer."""

from __future__ import annotations

"""诉讼 AI 会话仓储层,封装 LitigationSession 的数据库操作."""


from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async

if TYPE_CHECKING:
    from apps.litigation_ai.models import LitigationSession


class LitigationSessionRepository:
    def _model(self) -> type[LitigationSession]:
        from apps.litigation_ai.models import LitigationSession

        return LitigationSession

    def get_session_sync(self, session_id: str) -> Any:
        return self._model().objects.filter(session_id=session_id).first()

    def get_session_with_case_sync(self, session_id: str) -> Any:
        return self._model().objects.filter(session_id=session_id).select_related("case").first()

    def get_session_for_update_sync(self, session_id: str) -> Any:
        return self._model().objects.select_for_update().filter(session_id=session_id).first()

    def list_sessions_sync(self, *, filters: dict[str, Any], limit: int, offset: int) -> tuple[int, list[Any]]:
        qs = self._model().objects.filter(**(filters or {})).order_by("-created_at")
        total = qs.count()
        return total, list(qs[offset : offset + limit])

    async def get_session(self, session_id: str) -> Any:
        model = self._model()
        return await sync_to_async(
            model.objects.filter(session_id=session_id).first,
            thread_sensitive=True,
        )()

    async def get_session_or_raise(self, session_id: str) -> Any:
        model = self._model()
        return await sync_to_async(model.objects.get, thread_sensitive=True)(session_id=session_id)

    async def get_metadata(self, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        return (session.metadata or {}) if session else {}

    async def update_metadata(self, session_id: str, patch: dict[str, Any]) -> None:
        session = await self.get_session(session_id)
        if not session:
            return
        metadata = session.metadata or {}
        metadata.update(patch)
        model = self._model()
        await sync_to_async(
            model.objects.filter(session_id=session_id).update,
            thread_sensitive=True,
        )(metadata=metadata)

    async def update_metadata_or_raise(self, session_id: str, patch: dict[str, Any]) -> None:
        session = await self.get_session_or_raise(session_id)
        metadata = session.metadata or {}
        metadata.update(patch)
        await sync_to_async(
            session.__class__.objects.filter(session_id=session_id).update,
            thread_sensitive=True,
        )(metadata=metadata)

    async def set_document_type(self, session_id: str, document_type: str) -> None:
        model = self._model()
        await sync_to_async(
            model.objects.filter(session_id=session_id).update,
            thread_sensitive=True,
        )(document_type=document_type)

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

    def set_step_sync(self, session_id: str, step_value: str) -> None:
        session = self.get_session_sync(session_id)
        if not session:
            return
        metadata = session.metadata or {}
        metadata["current_step"] = step_value
        session.__class__.objects.filter(session_id=session_id).update(metadata=metadata)
