"""`apps/agent/services/approval/write_guard.py` —— 写端点兜底（入口 C）的判定口径。

只在「调用方是 agent（带会话头）」且「该会话正在多栏并答」时拒写。两个方向
都会出事，所以成对钉住：

- 判太松 → 多栏几栏互相覆盖（兜底形同虚设，而且没有任何报错）；
- 判太严 → 律师在页面上点「生成 / 应用 / 保存」也被 409（把人工操作打穿）。

会话登记复用 `policy.mark_multi_lane_session`（与生产同一套计数键），不在测试里
自造缓存键；清理按会话 id 精确撤销，不清空整个缓存（本机 Redis 还与 dev 服务共用）。
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import RequestFactory

from apps.agent.services.approval.policy import (
    MULTI_LANE_WRITE_REFUSAL,
    clear_multi_lane_session,
    mark_multi_lane_session,
)
from apps.agent.services.approval.write_guard import (
    MULTI_LANE_WRITE_CODE,
    SESSION_HEADER,
    ensure_request_not_multi_lane,
    ensure_write_not_multi_lane,
    multi_lane_session_of,
    request_session_id,
)
from apps.core.exceptions import ConflictError

MULTI = "guard-test-multi-lane"
SINGLE = "guard-test-single-lane"


def _request(session_id: str | None) -> Any:
    headers = {SESSION_HEADER: session_id} if session_id else {}
    return RequestFactory().post("/guard", headers=headers)


@pytest.fixture
def multi_session() -> Any:
    """已登记多栏的会话（计数 1 = 有一轮多栏在跑）。"""
    mark_multi_lane_session(MULTI)
    try:
        yield MULTI
    finally:
        clear_multi_lane_session(MULTI)


@pytest.fixture
def single_session() -> Any:
    """登记后立刻收尾：计数归零＝单栏（比「从没登记过」更接近真实收尾路径）。"""
    mark_multi_lane_session(SINGLE)
    clear_multi_lane_session(SINGLE)
    return SINGLE


class TestRequestSessionId:
    def test_reads_the_session_header(self) -> None:
        assert request_session_id(_request("sess-abc")) == "sess-abc"

    def test_missing_header_is_empty(self) -> None:
        assert request_session_id(_request(None)) == ""

    def test_whitespace_is_stripped(self) -> None:
        assert request_session_id(_request("  sess-abc  ")) == "sess-abc"

    def test_non_string_header_is_empty(self) -> None:
        """`MagicMock` 当 request 时 `headers.get` 返回真值 Mock：不许当会话 id 去查缓存。"""

        class _MockLikeHeaders:
            def get(self, key: str) -> Any:
                return object()

        request = type("R", (), {"headers": _MockLikeHeaders()})()
        assert request_session_id(request) == ""

    def test_request_without_headers_attr_is_empty(self) -> None:
        assert request_session_id(object()) == ""


class TestMultiLaneSessionOf:
    def test_returns_the_multi_lane_session(self, multi_session: str, single_session: str) -> None:
        assert multi_lane_session_of([single_session, multi_session]) == multi_session

    def test_single_lane_and_empty_are_none(self, single_session: str) -> None:
        assert multi_lane_session_of([single_session, "", None]) is None

    def test_non_string_entries_are_ignored(self, multi_session: str) -> None:
        assert multi_lane_session_of([None, 42, multi_session]) == multi_session  # type: ignore[list-item]


class TestEnsureWriteNotMultiLane:
    def test_multi_lane_raises_conflict_with_actionable_message(self, multi_session: str) -> None:
        with pytest.raises(ConflictError) as exc_info:
            ensure_write_not_multi_lane(endpoint="unit.endpoint", session_ids=[multi_session])

        assert exc_info.value.code == MULTI_LANE_WRITE_CODE
        assert exc_info.value.message == MULTI_LANE_WRITE_REFUSAL
        # 模型要能据此自纠：文案必须指向正确工具，而不是只说「不行」
        assert "propose_write_patch" in str(exc_info.value.message)
        assert exc_info.value.errors["endpoint"] == "unit.endpoint"
        assert exc_info.value.errors["session_id"] == multi_session

    def test_single_lane_passes(self, single_session: str) -> None:
        # 放行的唯一证据是「没抛异常」：返回 None 而不是别的哨兵值
        assert ensure_write_not_multi_lane(endpoint="unit.endpoint", session_ids=[single_session]) is None

    def test_no_session_ids_passes(self) -> None:
        assert ensure_write_not_multi_lane(endpoint="unit.endpoint", session_ids=[]) is None

    def test_cache_failure_falls_back_to_single_lane(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """缓存不可用按单栏（与 `policy.is_multi_lane_session` 同口径，不许改成 fail-closed）。"""

        class _FailingCache:
            def get(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("redis down")

        monkeypatch.setattr("django.core.cache.cache", _FailingCache())
        assert ensure_write_not_multi_lane(endpoint="unit.endpoint", session_ids=[MULTI]) is None


class TestEnsureRequestNotMultiLane:
    @pytest.mark.asyncio
    async def test_header_on_multi_lane_session_refuses(self, multi_session: str) -> None:
        with pytest.raises(ConflictError) as exc_info:
            await ensure_request_not_multi_lane(_request(multi_session), endpoint="unit.endpoint")
        assert exc_info.value.code == MULTI_LANE_WRITE_CODE

    @pytest.mark.asyncio
    async def test_header_on_single_lane_session_passes(self, single_session: str) -> None:
        assert await ensure_request_not_multi_lane(_request(single_session), endpoint="unit.endpoint") is None

    @pytest.mark.asyncio
    async def test_no_header_passes_even_when_another_session_is_multi_lane(self, multi_session: str) -> None:
        """律师在页面上点出来的请求没有会话头：别的会话多栏与它无关。"""
        assert await ensure_request_not_multi_lane(_request(None), endpoint="unit.endpoint") is None

    @pytest.mark.asyncio
    async def test_extra_session_ids_are_checked_without_header(self, multi_session: str) -> None:
        """patch 应用就靠这条：请求不带会话头，但 patch 行属于多栏会话。"""
        with pytest.raises(ConflictError):
            await ensure_request_not_multi_lane(
                _request(None), endpoint="unit.patch_apply", session_ids=[multi_session]
            )
