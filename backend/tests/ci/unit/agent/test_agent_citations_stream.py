"""编排层的三件「刷新后还在不在」的事实：引用 / 分栏用量 / TTFT。

它们都由 ``services/chat/stream.py`` 在同一处写进 ``AgentMessage.metadata``，
所以放在一个文件里守——**加一个键忘了另外两个，是这里最可能的退化方式**：

1. ``citations``：本轮全部引用（历史回放重建 ``[Kn]`` 角标与来源卡的唯一来源，
   刷新后没有 SSE 可看）；
2. ``usage_by_lane``：``{<agent>: {output, input, cache_read, cache_write}}``。
   ``turnStatsByLane`` 原本只在内存、每轮清空，于是「哪一栏更贵更慢」这个多答的
   核心卖点在产品上是临时的；
3. ``ttft_ms``：首个 token 到请求发出的毫秒数。拿不到（一个 token 事件都没发）
   就**不写这个键**——0ms 首字是一个不可能的数，写进去会污染性能对比。

全部离线：注册表注入假后端，不调模型、不起子进程。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from apps.agent.backends import BackendCapabilities, RunContext, register
from apps.agent.backends import registry as registry_module
from apps.agent.models import AgentMessage, AgentSession
from apps.agent.services.chat import budget, multi
from apps.agent.services.chat import stream as stream_module

PRIMARY = "fake-cite-primary"
SECONDARY = "fake-cite-secondary"

_CAPS = BackendCapabilities(streaming=True, tool_calls=True, approval=False, compaction=False, steer=False)

#: ``search_cases`` 的真实信封形状（``list_result`` + ``CASE_LIST_FIELDS`` 投影）。
_CASES_RESULT = json.dumps(
    {"total": 2, "items": [{"id": 21, "name": "甲诉乙买卖合同纠纷案"}, {"id": 22, "name": "丙诉丁借款纠纷案"}]},
    ensure_ascii=False,
)


class _FakeBackend:
    """按脚本吐事件；每帧补 ``agent`` / ``run_id``（与真实后端同形）。"""

    capabilities = _CAPS

    def __init__(self, kind: str, script: list[Any]) -> None:
        self.kind = kind
        self._script = script

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        for item in self._script:
            await asyncio.sleep(0)
            yield {**item, "agent": self.kind, "run_id": ctx.run_id}


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> Any:
    """注册表与 aux 计数是进程内全局状态：每条用例前后清空。"""
    registry_module.clear()
    budget._budget.reset()
    monkeypatch.setattr(stream_module, "ensure_registered", lambda: None)
    monkeypatch.setattr(multi, "ensure_registered", lambda: None)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    yield
    registry_module.clear()
    budget._budget.reset()


def _search_script() -> list[Any]:
    """一次真实形态的检索：tool_call → tool_result → 正文 → usage。"""
    return [
        {"type": "tool_call", "tool_call_id": "t1", "name": "mcp__fachuan__search_cases", "arguments": {"q": "买卖"}},
        {"type": "tool_result", "tool_call_id": "t1", "name": "mcp__fachuan__search_cases", "result": _CASES_RESULT},
        {"type": "delta", "content": "甲诉乙案已立案[K1]，丙诉丁案在审[K2]。"},
        {"type": "usage", "input_tokens": 120, "output_tokens": 30, "cache_read_tokens": 900, "cache_write_tokens": 10},
    ]


async def _make_session(agent_kind: str = PRIMARY) -> AgentSession:
    return await AgentSession.objects.acreate(title="引用与用量", agent_kind=agent_kind)


async def _assistant_rows(session: AgentSession) -> list[AgentMessage]:
    return [row async for row in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]


async def _collect(session: AgentSession) -> list[dict[str, Any]]:
    return [event async for event in stream_module.stream_chat(session=session, user_message="查一下买卖合同案")]


class TestCitationsOnTheWire:
    """``citations`` 事件：一次工具调用一帧，只带**新增**的那几条。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_emits_one_frame_per_retrieval(self) -> None:
        register(_FakeBackend(PRIMARY, _search_script()))
        session = await _make_session()

        events = await _collect(session)

        frames = [event for event in events if event.get("type") == "citations"]
        assert len(frames) == 1
        assert [ref["cite_no"] for ref in frames[0]["citations"]] == [1, 2]
        assert [ref["ref_id"] for ref in frames[0]["citations"]] == [21, 22]
        # 必须能归栏：多答时前端靠这两个字段把角标挂到正确的栏
        assert frames[0]["agent"] == PRIMARY
        assert frames[0]["run_id"].startswith(f"{session.session_id}:{PRIMARY}:")

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_citations_arrive_before_the_text_that_cites_them(self) -> None:
        """帧序：``tool_result`` → ``citations`` → 正文。

        顺序反了的话，前端在渲染 ``[K1]`` 时还不知道 1 号是谁，只能先把角标当
        普通方括号——而流式渲染不会再回头重算，那一处角标就永久丢了。
        """
        register(_FakeBackend(PRIMARY, _search_script()))
        session = await _make_session()

        kinds = [event.get("type") for event in await _collect(session)]

        assert kinds.index("citations") < kinds.index("delta")

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_error_results_do_not_produce_citations(self) -> None:
        """失败的工具调用只回错误文案，里面不可能有命中——强行解析只会造出空来源。"""
        register(
            _FakeBackend(
                PRIMARY,
                [
                    {"type": "tool_call", "tool_call_id": "t9", "name": "search_cases", "arguments": {}},
                    {
                        "type": "tool_result",
                        "tool_call_id": "t9",
                        "name": "search_cases",
                        "result": _CASES_RESULT,
                        "is_error": True,
                    },
                    {"type": "delta", "content": "查不到。"},
                ],
            )
        )
        session = await _make_session()

        events = await _collect(session)

        assert [event for event in events if event.get("type") == "citations"] == []


class TestMetadataIsTheReplaySource:
    """落库 metadata：刷新之后「这条回答出自哪几份材料、这栏花了多少、首字多快」。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_single_lane_metadata(self) -> None:
        register(_FakeBackend(PRIMARY, _search_script()))
        session = await _make_session()

        await _collect(session)

        [row] = await _assistant_rows(session)
        # 1) 本轮**全部**引用（不是最后一帧的新增）
        assert [ref["cite_no"] for ref in row.metadata["citations"]] == [1, 2]
        assert row.metadata["citations"][0]["kind"] == "case"
        # 2) 单栏也落用量，键是后端 kind
        assert row.metadata["usage_by_lane"] == {
            PRIMARY: {"output": 30, "input": 120, "cache_read": 900, "cache_write": 10}
        }
        # 3) TTFT 是一个「不可能是 0」的真实测量
        assert isinstance(row.metadata["ttft_ms"], int)
        assert row.metadata["ttft_ms"] >= 0

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_no_fake_zero_ttft_without_a_token(self) -> None:
        """一个 token 事件都没有（秒退 / 只有工具调用）→ 不落库，也就不会写出 0ms。

        0ms 首字是一个不可能的数：它会在分栏对比里伪造出一个「冠军栏目」。
        所以 ``ttft_ms`` 的写法是「有测量才写键」，而不是「没有就填 0」。
        """
        register(
            _FakeBackend(
                PRIMARY,
                [
                    {"type": "tool_call", "tool_call_id": "t1", "name": "search_cases", "arguments": {}},
                    {"type": "tool_result", "tool_call_id": "t1", "name": "search_cases", "result": _CASES_RESULT},
                ],
            )
        )
        session = await _make_session()

        await _collect(session)

        # 没有正文就没有助手消息行；关键断言是「不存在一个 ttft_ms == 0 的行」。
        rows = await _assistant_rows(session)
        assert all("ttft_ms" not in row.metadata for row in rows)
        assert all(row.metadata.get("ttft_ms") != 0 for row in rows)

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_multi_lane_stores_its_own_lane_only(self) -> None:
        """多答时每栏各存自己那条消息、只带自己那一格用量。

        合并成一张总账就答不了「哪一栏更贵」——而那正是多答的产品卖点。
        """
        register(
            _FakeBackend(
                PRIMARY,
                [{"type": "delta", "content": "主答"}, {"type": "usage", "input_tokens": 10, "output_tokens": 1}],
            )
        )
        register(
            _FakeBackend(
                SECONDARY,
                [{"type": "delta", "content": "次答"}, {"type": "usage", "input_tokens": 99, "output_tokens": 9}],
            )
        )
        session = await _make_session()

        [
            event
            async for event in multi.stream_multi(session=session, user_message="同题两答", kinds=[PRIMARY, SECONDARY])
        ]

        rows = await _assistant_rows(session)
        by_agent = {row.agent_kind: row for row in rows}
        assert set(by_agent) == {PRIMARY, SECONDARY}
        assert list(by_agent[PRIMARY].metadata["usage_by_lane"]) == [PRIMARY]
        assert list(by_agent[SECONDARY].metadata["usage_by_lane"]) == [SECONDARY]
        assert by_agent[PRIMARY].metadata["usage_by_lane"][PRIMARY]["input"] == 10
        assert by_agent[SECONDARY].metadata["usage_by_lane"][SECONDARY]["input"] == 99

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_multi_lane_citations_are_numbered_per_lane(self) -> None:
        """每栏从 1 开始各自编号：三栏的正文各说各的，角标互不干扰。"""
        register(
            _FakeBackend(
                PRIMARY,
                [
                    {"type": "tool_result", "tool_call_id": "a", "name": "search_cases", "result": _CASES_RESULT},
                    {"type": "delta", "content": "主答见[K1]"},
                ],
            )
        )
        register(
            _FakeBackend(
                SECONDARY,
                [
                    {"type": "tool_result", "tool_call_id": "b", "name": "search_cases", "result": _CASES_RESULT},
                    {"type": "delta", "content": "次答见[K1]"},
                ],
            )
        )
        session = await _make_session()

        [
            event
            async for event in multi.stream_multi(session=session, user_message="同题两答", kinds=[PRIMARY, SECONDARY])
        ]

        rows = {row.agent_kind: row for row in await _assistant_rows(session)}
        for kind in (PRIMARY, SECONDARY):
            assert [ref["cite_no"] for ref in rows[kind].metadata["citations"]] == [1, 2]
