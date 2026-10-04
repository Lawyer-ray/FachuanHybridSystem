"""litigation_ai/flow/session_repository.py 单元测试（真实测试库）.

覆盖 metadata 读改写（锁内合并）、step 读写、会话不存在分支、
list_sessions_sync 分页与 update_metadata_or_raise 语义。
异步用例内用 async ORM（acreate / arefresh_from_db）构造与断言数据。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.cases.models import Case
from apps.litigation_ai.models import LitigationSession
from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository


@pytest.fixture()
def repo() -> LitigationSessionRepository:
    return LitigationSessionRepository()


@pytest.fixture()
def case(db) -> Case:
    return Case.objects.create(name="仓储测试案件")


async def _amake_session(case: Case, metadata: dict | None = None) -> LitigationSession:
    return await LitigationSession.objects.acreate(
        case=case,
        session_id=uuid.uuid4(),
        metadata=metadata if metadata is not None else {},
    )


def _make_session(case: Case, metadata: dict | None = None) -> LitigationSession:
    return LitigationSession.objects.create(
        case=case,
        session_id=uuid.uuid4(),
        metadata=metadata if metadata is not None else {},
    )


def _page_items(page: Any) -> list[Any]:
    if isinstance(page, dict):
        for key in ("items", "results"):
            if key in page:
                return list(page[key])
        raise AssertionError(f"未知分页返回结构: {list(page.keys())}")
    return list(page)


@pytest.mark.django_db(transaction=True)
class TestMetadataReadWrite:
    @pytest.mark.asyncio
    async def test_get_metadata_existing(self, repo: LitigationSessionRepository, case: Case) -> None:
        session = await _amake_session(case, {"mode": "judge"})
        assert await repo.get_metadata(str(session.session_id)) == {"mode": "judge"}

    @pytest.mark.asyncio
    async def test_get_metadata_missing_session_returns_empty(self, repo: LitigationSessionRepository) -> None:
        assert await repo.get_metadata(str(uuid.uuid4())) == {}

    @pytest.mark.asyncio
    async def test_update_metadata_merges_keys(self, repo: LitigationSessionRepository, case: Case) -> None:
        session = await _amake_session(case, {"a": 1, "keep": True})
        await repo.update_metadata(str(session.session_id), {"a": 2, "b": 3})
        await session.arefresh_from_db()
        assert session.metadata == {"a": 2, "b": 3, "keep": True}

    @pytest.mark.asyncio
    async def test_update_metadata_missing_session_noop(self, repo: LitigationSessionRepository) -> None:
        missing = str(uuid.uuid4())
        await repo.update_metadata(missing, {"x": 1})  # 不抛错
        assert await repo.get_metadata(missing) == {}

    @pytest.mark.asyncio
    async def test_update_metadata_or_raise_raises_for_missing(self, repo: LitigationSessionRepository) -> None:
        with pytest.raises(LitigationSession.DoesNotExist):
            await repo.update_metadata_or_raise(str(uuid.uuid4()), {"x": 1})

    @pytest.mark.asyncio
    async def test_update_metadata_or_raise_succeeds(self, repo: LitigationSessionRepository, case: Case) -> None:
        session = await _amake_session(case, {})
        await repo.update_metadata_or_raise(str(session.session_id), {"k": "v"})
        await session.arefresh_from_db()
        assert session.metadata == {"k": "v"}


@pytest.mark.django_db(transaction=True)
class TestStepHelpers:
    @pytest.mark.asyncio
    async def test_set_step_writes_metadata_key(self, repo: LitigationSessionRepository, case: Case) -> None:
        session = await _amake_session(case, {"other": 1})
        await repo.set_step(str(session.session_id), "document_type")
        await session.arefresh_from_db()
        assert session.metadata["current_step"] == "document_type"
        assert session.metadata["other"] == 1  # 不覆盖其他键

    @pytest.mark.asyncio
    async def test_set_step_missing_session_noop(self, repo: LitigationSessionRepository) -> None:
        missing = str(uuid.uuid4())
        await repo.set_step(missing, "init")  # 不抛错
        assert await repo.get_step_value(missing) is None

    @pytest.mark.asyncio
    async def test_get_step_value(self, repo: LitigationSessionRepository, case: Case) -> None:
        session = await _amake_session(case, {"current_step": "evidence_selection"})
        assert await repo.get_step_value(str(session.session_id)) == "evidence_selection"

    @pytest.mark.asyncio
    async def test_get_step_value_missing_returns_none(self, repo: LitigationSessionRepository) -> None:
        assert await repo.get_step_value(str(uuid.uuid4())) is None

    def test_get_step_value_sync(self, repo: LitigationSessionRepository, case: Case) -> None:
        session = _make_session(case, {"current_step": "init"})
        assert repo.get_step_value_sync(str(session.session_id)) == "init"
        assert repo.get_step_value_sync(str(uuid.uuid4())) is None

    def test_set_step_sync_locked_rmw(self, repo: LitigationSessionRepository, case: Case) -> None:
        session = _make_session(case, {"payload": "x"})
        repo.set_step_sync(str(session.session_id), "generating")
        session.refresh_from_db()
        assert session.metadata == {"payload": "x", "current_step": "generating"}


@pytest.mark.django_db(transaction=True)
class TestDocumentType:
    @pytest.mark.asyncio
    async def test_set_document_type(self, repo: LitigationSessionRepository, case: Case) -> None:
        session = await _amake_session(case, {})
        await repo.set_document_type(str(session.session_id), "complaint")
        await session.arefresh_from_db()
        assert session.document_type == "complaint"

    @pytest.mark.asyncio
    async def test_set_document_type_missing_noop(self, repo: LitigationSessionRepository) -> None:
        missing = str(uuid.uuid4())
        await repo.set_document_type(missing, "complaint")  # 不抛错
        assert await repo.get_metadata(missing) == {}


@pytest.mark.django_db(transaction=True)
class TestSyncQueries:
    def test_get_session_for_update_sync(self, repo: LitigationSessionRepository, case: Case) -> None:
        from django.db import transaction

        session = _make_session(case, {})
        with transaction.atomic():
            found = repo.get_session_for_update_sync(str(session.session_id))
            assert found is not None and found.pk == session.pk
            assert repo.get_session_for_update_sync(str(uuid.uuid4())) is None

    def test_list_sessions_sync_orders_and_paginates(self, repo: LitigationSessionRepository, case: Case) -> None:
        _make_session(case, {})
        newest = _make_session(case, {})
        page = repo.list_sessions_sync(filters={}, page=1, page_size=1)
        items = _page_items(page)
        # created_at 倒序：最新在前
        assert len(items) == 1
        assert items[0].pk == newest.pk

    def test_list_sessions_sync_with_filters(self, repo: LitigationSessionRepository, case: Case) -> None:
        _make_session(case, {})
        page = repo.list_sessions_sync(filters={"session_id": uuid.uuid4()}, page=1, page_size=20)
        assert _page_items(page) == []
