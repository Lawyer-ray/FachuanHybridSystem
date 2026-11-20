"""轮次号（``run_id`` 尾段）真递增 + ``finish_reason`` 落库。

两件事放在一起，因为它们都是「这一轮的历史事实」——客户端刷新、第二天再看、
或者按 run 归集用量时，SSE 早就没了，只有 DB 里这两条能回答：

1. **这是第几轮**（``run_id = {session}:{kind}:{turn}``）。尾段以前恒为 ``1``，
   同一会话的第二轮与第一轮共用一个 run_id，前端按 run 归集用量时两轮混成一格。
   现在由 Redis ``INCR`` 取号；Redis 不可用时回落 ``1``（旧行为），不得让对话失败。
2. **这轮怎么结束的**（``AgentMessage.metadata["finish_reason"]``）。前端
   ``turn-actions.canContinue`` 靠它决定「继续生成」能不能点；``degraded`` 是
   **轮级**事实（「另外几栏没跑成」），单栏视角永远只会说 ok/error。
   ``cancelled`` 只可能出现在这里——客户端断开时生成器已被关闭，没有通道发 done。

全部离线：注册表注入假后端，不调模型、不起子进程。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from apps.agent.backends import BackendCapabilities, RunContext, register
from apps.agent.backends import registry as registry_module
from apps.agent.models import AgentMessage, AgentSession
from apps.agent.services.chat import budget, multi
from apps.agent.services.chat import stream as stream_module
from apps.agent.sse_types import WIRE_UNREACHABLE, FinishReason

#: 非真实 kind：真后端注册回注册表后，``pick_secondary`` / ``get_backend`` 会挑到
#: 它们并真的去连网关（见 ``test_dual_stream`` 的同款说明）。
PRIMARY = "fake-turn-primary"
SECONDARY = "fake-turn-secondary"

_CAPS = BackendCapabilities(
    streaming=True,
    tool_calls=False,
    approval=False,
    compaction=False,
    steer=False,
)


class _FakeBackend:
    """按脚本吐事件；脚本里可以夹一个异常来模拟「出了半段字之后失败」。"""

    capabilities = _CAPS

    def __init__(self, kind: str, script: list[Any]) -> None:
        self.kind = kind
        self._script = script
        self.run_ids: list[str] = []

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        self.run_ids.append(ctx.run_id)
        for item in self._script:
            # 真实后端每读一条输出就让出一次控制权；假后端显式让出，多栏才会真的
            # 交错（否则先起的那一栏一口气跑完，「并发合并」没被触发）。
            await asyncio.sleep(0)
            if isinstance(item, BaseException):
                raise item
            # 与真实后端同形：每帧都补 ``agent`` / ``run_id``（见 pi_backend 的
            # 转发处）。少了它，单栏路径的 delta 就没有 run_id——那是假后端的
            # 违约，不是 ``stream_chat`` 的行为。
            yield {**item, "agent": self.kind, "run_id": ctx.run_id}


class _FakeCache:
    """最小的 Redis 计数替身（``add`` + ``incr`` + ``touch``）。"""

    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def add(self, key: str, value: int, timeout: int | None = None) -> bool:
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def incr(self, key: str) -> int:
        self.values[key] += 1
        return self.values[key]

    def touch(self, key: str, timeout: int | None = None) -> bool:
        return key in self.values


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> Any:
    """注册表与 aux 计数是进程内全局状态：每条用例前后清空。

    ``ensure_registered`` 必须逐个替换引用点（两个模块都用 ``from ... import``
    取了本地名），否则 ``stream_chat`` 入口会把真实后端补回注册表。
    """
    registry_module.clear()
    budget._budget.reset()
    monkeypatch.setattr(stream_module, "ensure_registered", lambda: None)
    monkeypatch.setattr(multi, "ensure_registered", lambda: None)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    yield
    registry_module.clear()
    budget._budget.reset()


def _ok_script(text: str) -> list[Any]:
    return [{"type": "delta", "content": text}, {"type": "usage", "input_tokens": 10, "output_tokens": 5}]


async def _make_session(agent_kind: str = PRIMARY) -> AgentSession:
    return await AgentSession.objects.acreate(title="轮次", agent_kind=agent_kind)


async def _assistant_rows(session: AgentSession) -> list[AgentMessage]:
    return [row async for row in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]


class TestRunTurnNumbering:
    """``next_run_turn``：Redis INCR 递增；不可用时回落 1（不得抛）。"""

    def test_increments_per_call_with_redis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stream_module, "redis_cache_enabled", lambda: True)
        monkeypatch.setattr(stream_module, "cache", _FakeCache())

        turns = [stream_module._next_turn_sync("s-1") for _ in range(3)]

        assert turns == [1, 2, 3]

    def test_counter_is_per_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """两个会话各自从 1 开始：键按会话，互不干扰。"""
        monkeypatch.setattr(stream_module, "redis_cache_enabled", lambda: True)
        monkeypatch.setattr(stream_module, "cache", _FakeCache())

        assert stream_module._next_turn_sync("s-1") == 1
        assert stream_module._next_turn_sync("s-2") == 1
        assert stream_module._next_turn_sync("s-1") == 2

    def test_no_redis_falls_back_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """非 Redis 缓存（LocMem / Dummy）不计数。

        进程内计数在两个 worker 上各自从 1 开始，会造出**跨 worker 重复**的
        run_id——那比固定 ``:1`` 更危险（前端把两个 run 的事件归成一个）。
        """
        monkeypatch.setattr(stream_module, "redis_cache_enabled", lambda: False)

        assert stream_module._next_turn_sync("s-1") is None

    def test_cache_failure_does_not_break_the_turn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redis 挂了只降级，不抛：对话绝不能因为取号失败而中断。"""

        class _BrokenCache(_FakeCache):
            def add(self, key: str, value: int, timeout: int | None = None) -> bool:
                raise ConnectionError("redis down")

        monkeypatch.setattr(stream_module, "redis_cache_enabled", lambda: True)
        monkeypatch.setattr(stream_module, "cache", _BrokenCache())

        assert stream_module._next_turn_sync("s-1") is None

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_stream_chat_uses_the_given_turn(self) -> None:
        """显式传 ``turn`` 时必须原样出现在 run_id 尾段（多答各栏共享同一个号）。"""
        register(_FakeBackend(PRIMARY, _ok_script("正文")))
        session = await _make_session()

        events = [e async for e in stream_module.stream_chat(session=session, user_message="q", turn=7)]

        deltas = [e for e in events if e.get("type") == "delta"]
        assert [e["run_id"] for e in deltas] == [f"{session.session_id}:{PRIMARY}:7"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_two_rounds_get_different_turns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """同一会话连跑两轮：尾段 1 → 2（以前两轮都是 1，用量按 run 归集会串账）。"""
        monkeypatch.setattr(stream_module, "redis_cache_enabled", lambda: True)
        monkeypatch.setattr(stream_module, "cache", _FakeCache())
        register(_FakeBackend(PRIMARY, _ok_script("正文")))
        session = await _make_session()

        first = [e async for e in stream_module.stream_chat(session=session, user_message="第一轮")]
        second = [e async for e in stream_module.stream_chat(session=session, user_message="第二轮")]

        first_runs = {e["run_id"] for e in first if e.get("type") == "delta"}
        second_runs = {e["run_id"] for e in second if e.get("type") == "delta"}
        assert first_runs == {f"{session.session_id}:{PRIMARY}:1"}
        assert second_runs == {f"{session.session_id}:{PRIMARY}:2"}

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_fallback_keeps_old_behaviour(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redis 不可用：两轮都退回 ``:1``（旧行为），对话照常跑完。"""
        monkeypatch.setattr(stream_module, "redis_cache_enabled", lambda: False)
        register(_FakeBackend(PRIMARY, _ok_script("正文")))
        session = await _make_session()

        first = [e async for e in stream_module.stream_chat(session=session, user_message="一")]
        second = [e async for e in stream_module.stream_chat(session=session, user_message="二")]

        for events in (first, second):
            assert {e["run_id"] for e in events if e.get("type") == "delta"} == {f"{session.session_id}:{PRIMARY}:1"}
            assert [e for e in events if e.get("type") == "done"], "回落路径也必须正常收尾"


class TestFinishReasonMetadata:
    """``AgentMessage.metadata["finish_reason"]``：历史回放的唯一来源。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_single_turn_ok(self) -> None:
        register(_FakeBackend(PRIMARY, _ok_script("完整回答")))
        session = await _make_session()

        await _collect_stream_chat(session)

        rows = await _assistant_rows(session)
        assert len(rows) == 1
        assert rows[0].metadata["finish_reason"] == "ok"
        assert "truncated" not in rows[0].metadata

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_single_turn_error(self) -> None:
        """半段正文后失败：正文保住，且标记为 error + truncated。"""
        register(_FakeBackend(PRIMARY, [{"type": "delta", "content": "半段"}, RuntimeError("上游炸了")]))
        session = await _make_session()

        await _collect_stream_chat(session)

        rows = await _assistant_rows(session)
        assert [row.content for row in rows] == ["半段"]
        assert rows[0].metadata["finish_reason"] == "error"
        assert rows[0].metadata["truncated"] is True

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_cancelled_is_recorded_even_though_unreachable_on_the_wire(self) -> None:
        """用户按停止：已流出的正文落库，``finish_reason="cancelled"``。

        这个值**不可达于 SSE**（``WIRE_UNREACHABLE``）：生成器已被关闭，没有通道
        发 done。所以它是「只在 metadata 里」的事实——也正是前端判断「这轮是被
        停止的，可以继续生成」的唯一依据。
        """
        release = asyncio.Event()

        class _BlockingBackend(_FakeBackend):
            async def _stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
                yield {"type": "delta", "content": "第一段"}
                await release.wait()
                yield {"type": "delta", "content": "不该出现"}

        register(_BlockingBackend(PRIMARY, []))
        session = await _make_session()

        agen = stream_module.stream_chat(session=session, user_message="问题")
        it = agen.__aiter__()
        for _ in range(3):  # meta / activity / delta
            event = await it.__anext__()
            if event.get("type") == "delta":
                break
        await agen.aclose()  # 模拟前端按停止：生成器收到 GeneratorExit
        release.set()

        row = await _wait_assistant_row(session)
        assert row.content == "第一段"
        assert row.metadata["finish_reason"] == "cancelled"
        assert row.metadata["finish_reason"] in {"cancelled"} | set(WIRE_UNREACHABLE)

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_multi_all_ok(self) -> None:
        register(_FakeBackend(PRIMARY, _ok_script("主答")))
        register(_FakeBackend(SECONDARY, _ok_script("次答")))
        session = await _make_session()

        await _collect_multi(session)

        rows = await _assistant_rows(session)
        assert {row.agent_kind for row in rows} == {PRIMARY, SECONDARY}
        assert {row.metadata["finish_reason"] for row in rows} == {"ok"}

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_multi_partial_failure_is_degraded_for_the_whole_turn(self) -> None:
        """次答出了半段后失败：整轮是 ``degraded``，两栏的行都写它。

        为什么两栏都要写轮级结论：律师看的是「这一轮有没有跑全」。只给失败的
        那栏写 error、成功那栏写 ok，历史回放时就分不清「本轮降级了」还是
        「两轮各跑了一次」——前端也无从决定要不要提示「另外几栏没跑成」。
        单栏失败原因的权威记录是 ``AgentRun.status`` / ``error_kind``。
        """
        register(_FakeBackend(PRIMARY, _ok_script("主答正文")))
        register(_FakeBackend(SECONDARY, [{"type": "delta", "content": "次答半段"}, RuntimeError("次答炸了")]))
        session = await _make_session()

        events = await _collect_multi(session)

        rows = await _assistant_rows(session)
        assert {row.agent_kind for row in rows} == {PRIMARY, SECONDARY}
        assert {row.metadata["finish_reason"] for row in rows} == {"degraded"}
        # 失败那一栏的正文也保住了（半段也算律师看过的东西）
        assert {row.content for row in rows} == {"主答正文", "次答半段"}
        # 线上的 done 也必须是 degraded（前端实时路径与回放路径同一结论）
        dones = [e for e in events if e.get("type") == "done"]
        assert {done["finish_reason"] for done in dones} == {"degraded"}

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_multi_total_failure_has_no_rows_but_error_dones(self) -> None:
        """两栏全败：没有正文就没有可回写的行，但 done 必须说 error。"""
        register(_FakeBackend(PRIMARY, [RuntimeError("主答炸了")]))
        register(_FakeBackend(SECONDARY, [RuntimeError("次答炸了")]))
        session = await _make_session()

        events = await _collect_multi(session)

        assert await _assistant_rows(session) == []
        dones = [e for e in events if e.get("type") == "done"]
        assert dones and {done["finish_reason"] for done in dones} == {"error"}

    def test_metadata_value_is_the_shared_enum(self) -> None:
        """落库值与 ``done.finish_reason`` 是**同一个**枚举（不许各写一套）。

        一份枚举两种载体：SSE 只可能发 ok/degraded/error，``cancelled`` 只在
        metadata 里。两套枚举会让前端「实时看到的」与「刷新后看到的」不一致。
        """
        declared = set(FinishReason.__args__)  # type: ignore[attr-defined]
        assert declared - set(WIRE_UNREACHABLE) == {"ok", "degraded", "error"}
        assert set(WIRE_UNREACHABLE) == {"cancelled"}


# ── 收集与等待的小工具 ──────────────────────────────────────────────────


async def _collect_stream_chat(session: AgentSession) -> list[dict[str, Any]]:
    return [event async for event in stream_module.stream_chat(session=session, user_message="问题")]


async def _collect_multi(session: AgentSession) -> list[dict[str, Any]]:
    return [
        event async for event in multi.stream_multi(session=session, user_message="问题", kinds=[PRIMARY, SECONDARY])
    ]


async def _wait_assistant_row(session: AgentSession, timeout: float = 5.0) -> AgentMessage:
    """等取消路径的落库任务完成（它是 ``ensure_future`` 派发的，不保证立刻可见）。

    轮询条件而不是固定 sleep：取消路径的写入要等事件循环调度一次，快慢取决于
    机器；写死时长会让断言随机失败，而失败信息（row is None）看起来像业务 bug。
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        rows = await _assistant_rows(session)
        if rows:
            return rows[0]
        await asyncio.sleep(0.02)
    raise AssertionError("取消路径未落库助手文本")
