"""多栏合并的**公平交错**（``services/chat/multi.py`` 的 N 个 task + 共享有界队列）。

本文件钉的是 2026-11-20 修掉的那条缺陷：早先主答在合并协程里**内联**迭代、其余栏
各一个**无界**队列且只在主答结束后**按栏串行抽干**，于是「不管哪个 agent 摆在最
左列，它永远最快」——左列恒为 ``agents[0]``，右列的帧被后端扣住，等左列跑完才
整批刷出。现有 7 个测试文件全都抓不到它：它们只断言「谁的帧都在、done 有几条」，
从不关心**相对顺序**。

五条（任务书的验收清单）+ 一条收尾守卫：

1. **公平交错**：慢主栏 + 快次栏 → 次栏的 delta 早于主栏最后一个 delta。这是唯一
   能钉住本次修复的断言；
2. **帧序**：所有非 done 帧都在第一条 done 之前，``done`` 顺序 == ``agents`` 顺序；
3. **每栏 error**：两栏都败 → 恰好 2 条、各带自己的 ``agent``；一栏败 → 只 1 条且
   挂在失败那一栏，另一栏正文照常完整；
4. **背压不丢帧**：一栏发 400 条 delta（> ``_LANE_QUEUE_MAXSIZE``）→ 400 条一条
   不少、顺序与内容完整（有界队列只阻塞、不丢弃）；
5. **断连落库**：客户端按停止后，次栏已流出的正文仍然落库（否则下次打开会话只剩
   主栏）；
6. **满队列也不死等**：断连时队列刚好是满的，收尾仍能在超时内结束——被取消那一栏
   还要往满队列里放哨兵，收尾方不抽干就会把 SSE 连接挂死（见 ``_join_lanes``）。

全部离线：注册表注入假后端（``stream()`` 吐预置事件 + 可控延迟），不调真模型、
不起子进程。数据库用 ``django_db(transaction=True)``：``stream_multi`` 跨
``asyncio.create_task`` 并发写库，非事务型用例的同步包装会让两个协程看到同一份
快照（与 ``test_dual_stream.py`` 同一口径）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Sequence
from typing import Any, cast

import pytest

from apps.agent.backends import BackendCapabilities, RunContext, register
from apps.agent.backends import registry as registry_module
from apps.agent.models import AgentMessage, AgentSession
from apps.agent.services.chat import budget, multi
from apps.agent.services.chat import stream as stream_module

#: 会话自己的后端（主答 = 左列 = ``agents[0]``）。kind 刻意不用 ``pi`` / ``dsh``：
#: 那两个名字属于真实后端，``builtin.ensure_registered()`` 会把它们补进注册表，
#: 于是本轮真的去起子进程 / 调真模型。
PRIMARY = "fake-primary"
#: 注册表里另一个后端（次答）
SECONDARY = "fake-secondary"
#: 第三栏（验 done 顺序与「三栏各一个」）
THIRD = "fake-third"

_CAPS = BackendCapabilities(
    streaming=True,
    tool_calls=False,
    approval=False,
    compaction=False,
    steer=False,
)


class _FakeBackend:
    """按预置脚本吐事件的假后端（可加延迟 / 可在脚本后挂住不返回）。

    帧里**不带** ``agent`` / ``run_id``：真实后端会补，但本文件要验的是
    ``_pump_lane`` 在**进队列之前**统一补齐，所以脚本里刻意只给 ``type`` 与内容。
    """

    def __init__(
        self,
        kind: str,
        script: list[dict[str, Any]] | BaseException,
        *,
        delay: float = 0.0,
        block_on: asyncio.Event | None = None,
    ) -> None:
        self.kind = kind
        self.capabilities = _CAPS
        self._script = script
        #: 每个帧之间的间隔（秒）。慢栏用它把「谁先产出」拉开到肉眼可见。
        self._delay = delay
        #: 脚本吐完仍不返回（模拟「这一栏还在跑」），断连用例靠它让次栏留在飞。
        self._block_on = block_on

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        if isinstance(self._script, BaseException):
            raise self._script
        for event in self._script:
            # 真实后端每读一行 stdout / 一条 SSE 都会让出一次 tick；假后端显式让出
            # 才让多栏真的交错——否则先起的那一栏会一口气跑完，测不到「合并」。
            await asyncio.sleep(self._delay) if self._delay else await asyncio.sleep(0)
            yield event
        if self._block_on is not None:
            await self._block_on.wait()


def _deltas(*texts: str) -> list[dict[str, Any]]:
    """一串 delta 帧（**不含 ``done``**：后端不发 done，由编排层按栏统一发）。"""
    return [{"type": "delta", "content": text} for text in texts]


def _guard_get_backend(kind: str) -> Any:
    """取后端，并断言「只取本用例注入的假后端」。

    真实后端（``pi`` / ``dsh`` / ``openai-agents``）一旦被 ``ensure_registered``
    补回注册表，本轮就会真的去跑模型——那既不是本文件要验的东西，也会让断言
    变成「一个假的一个真的」。这里把这种情况暴露在取后端的那一刻。
    """
    from apps.agent.backends import get

    backend = get(kind)
    assert isinstance(backend, _FakeBackend), f"取到了真实后端 {kind!r}，注册表未被隔离"
    return backend


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> Any:
    """注册表与 aux 计数都是进程内全局状态：每条用例前后清空。

    同时把内置注册关掉：``stream_chat`` 每轮入口都调 ``ensure_registered()``，
    它会把真实的 ``pi`` / ``dsh`` 补回注册表。两个模块都用了
    ``from ... import ensure_registered`` 的本地名，只改 ``builtin`` 的属性对它们
    无效，必须逐个替换引用点。
    """
    registry_module.clear()
    budget._budget.reset()
    monkeypatch.setattr(stream_module, "ensure_registered", lambda: None)
    monkeypatch.setattr(multi, "ensure_registered", lambda: None)
    monkeypatch.setattr(stream_module, "get_backend", _guard_get_backend)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    yield
    registry_module.clear()
    budget._budget.reset()


async def _make_session() -> AgentSession:
    return await AgentSession.objects.acreate(title="多答交错", agent_kind=PRIMARY)


async def _collect(kinds: Sequence[str], *, pause_every: int = 0) -> list[dict[str, Any]]:
    """跑一轮 ``stream_multi`` 收齐全部帧。

    ``pause_every``：每收这么多帧停顿 10ms，模拟**跟不上的前端**。背压用例靠它
    把有界队列压满——只有「满了就阻塞、不丢弃」的实现才能一条不少地收全。
    """
    session = await _make_session()
    events: list[dict[str, Any]] = []
    async for event in multi.stream_multi(
        session=session, user_message="合同有效吗", user_id=None, kinds=list(kinds)
    ):
        events.append(event)
        if pause_every and len(events) % pause_every == 0:
            await asyncio.sleep(0.01)
    return events


def _indexes(events: Sequence[dict[str, Any]], **match: Any) -> list[int]:
    """满足全部字段等值条件的帧下标（断言「谁在谁之前」用）。"""
    return [i for i, event in enumerate(events) if all(event.get(k) == v for k, v in match.items())]


class TestFairInterleave:
    """本次修复的核心：**谁先产出谁先上线**，没有「主栏优先」的隐式顺序。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_fast_secondary_overtakes_slow_primary(self) -> None:
        """慢主栏 + 快次栏 → 次栏的 delta 出现在主栏**最后一个** delta 之前。

        这条是唯一能钉住本次修复的断言：旧实现把主答内联迭代、次栏攒在队列里等
        主答跑完才抽干，于是次栏的 delta 必然落在主栏全部 delta 之后（用户看到
        的就是「左列永远最快，右列整批后到」）。
        """
        register(_FakeBackend(PRIMARY, _deltas("主1", "主2", "主3", "主4", "主5"), delay=0.02))
        register(_FakeBackend(SECONDARY, _deltas("次1")))

        events = await _collect([PRIMARY, SECONDARY])

        primary_at = _indexes(events, type="delta", agent=PRIMARY)
        secondary_at = _indexes(events, type="delta", agent=SECONDARY)
        assert len(primary_at) == 5, events
        assert len(secondary_at) == 1, events
        # 次栏不是被攒到最后一次性刷出的：它插在主栏还没说完的时候
        assert secondary_at[0] < primary_at[-1], f"次栏 delta 晚于主栏最后一个 delta：{events}"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_secondary_delta_precedes_every_done(self) -> None:
        """次栏 delta 必须早于**第一条** done（done 要等整轮收尾才发）。

        前半句在旧实现下也成立（done 在抽干之后才发），所以它只作为「收尾顺序
        没被交换」的守卫；钉住本次修复的是上一条的「早于主栏最后一个 delta」。
        """
        register(_FakeBackend(PRIMARY, _deltas("主1", "主2"), delay=0.02))
        register(_FakeBackend(SECONDARY, _deltas("次1")))

        events = await _collect([PRIMARY, SECONDARY])

        first_done = _indexes(events, type="done")[0]
        assert _indexes(events, type="delta", agent=SECONDARY)[0] < first_done


class TestFrameOrder:
    """帧序与 done 顺序：前端「全部栏收完才算整轮结束」的前提。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_every_non_done_frame_precedes_the_first_done(self) -> None:
        """所有非 done 帧都在第一条 done 之前。

        防的回归：把 done 挪进各栏的 task 里（谁跑完谁发），于是「先结束那一栏的
        done」会插到「后结束那一栏的正文」前面，前端按 done 收栏后会把后续内容
        当成过期的流丢弃。
        """
        register(_FakeBackend(PRIMARY, _deltas("甲"), delay=0.01))
        register(_FakeBackend(SECONDARY, _deltas("乙")))
        register(_FakeBackend(THIRD, _deltas("丙"), delay=0.02))

        events = await _collect([PRIMARY, SECONDARY, THIRD])

        types = [event.get("type") for event in events]
        first_done = types.index("done")
        assert "done" not in types[:first_done]
        assert types[first_done:] == ["done", "done", "done"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_done_order_follows_agents_order(self) -> None:
        """done 顺序 == ``agents`` 顺序（**不是**完成顺序）。

        左列恒为 ``agents[0]``：前端默认把第一栏画在左边，done 若按完成顺序发，
        每栏的收尾信号就会错位到别的栏上。这里让完成顺序与 agents 顺序**相反**
        （第 3 栏最快），才能把两者分开。
        """
        register(_FakeBackend(PRIMARY, _deltas("甲"), delay=0.03))
        register(_FakeBackend(SECONDARY, _deltas("乙"), delay=0.02))
        register(_FakeBackend(THIRD, _deltas("丙")))

        events = await _collect([PRIMARY, SECONDARY, THIRD])

        dones = [event for event in events if event.get("type") == "done"]
        assert [done["agent"] for done in dones] == [PRIMARY, SECONDARY, THIRD]
        # 每栏的 done 都带本轮全量参与方与自己的 run_id
        for done in dones:
            assert done["agents"] == [PRIMARY, SECONDARY, THIRD]
            assert done["run_id"].endswith(f":{done['agent']}:1")


class TestPerLaneError:
    """每栏**各自**一条 ``error``：前端靠它把那一栏标成「本轮未做」。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_both_failing_lanes_emit_their_own_error(self) -> None:
        register(_FakeBackend(PRIMARY, RuntimeError("主答炸了")))
        register(_FakeBackend(SECONDARY, RuntimeError("次答炸了")))

        events = await _collect([PRIMARY, SECONDARY])

        errors = [event for event in events if event.get("type") == "error"]
        assert len(errors) == 2, errors
        # 各带自己的 agent：只发一条会让主栏的失败被次栏占位而静默消失
        assert {error["agent"] for error in errors} == {PRIMARY, SECONDARY}
        assert [event.get("type") for event in events].count("done") == 2

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_one_failing_lane_does_not_disturb_the_other(self) -> None:
        register(_FakeBackend(PRIMARY, _deltas("甲", "乙", "丙")))
        register(_FakeBackend(SECONDARY, RuntimeError("次答炸了")))

        events = await _collect([PRIMARY, SECONDARY])

        errors = [event for event in events if event.get("type") == "error"]
        assert len(errors) == 1, errors
        assert errors[0]["agent"] == SECONDARY
        # 另一栏的正文照常完整（一个字都不能少）
        assert [event["content"] for event in events if event.get("type") == "delta"] == ["甲", "乙", "丙"]


class TestBackpressure:
    """有界队列只**阻塞**，绝不丢弃：丢一条 delta 就是用户看到的正文缺字。"""

    #: 远大于 ``_LANE_QUEUE_MAXSIZE``：生产者必然被队列顶住一段时间
    DELTA_COUNT = 400

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_no_frame_is_dropped_when_the_queue_is_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        texts = [f"第{i}段" for i in range(self.DELTA_COUNT)]
        # 上限压到 2：慢消费者 + 两个生产者，队列**必然**被顶满（用默认的 256 时
        # 这条用例跑完可能一次都没满过，「有界队列不丢帧」就成了没有对象的断言）
        monkeypatch.setattr(multi, "_LANE_QUEUE_MAXSIZE", 2)
        assert self.DELTA_COUNT > multi._LANE_QUEUE_MAXSIZE, "本用例要靠超容量才有意义"
        register(_FakeBackend(PRIMARY, _deltas(*texts)))
        register(_FakeBackend(SECONDARY, _deltas(*[f"次{i}" for i in range(20)])))

        # 消费者定期停顿 = 慢前端：把有界队列压满
        events = await _collect([PRIMARY, SECONDARY], pause_every=50)

        received = [event["content"] for event in events if event.get("type") == "delta" and event["agent"] == PRIMARY]
        assert len(received) == self.DELTA_COUNT, f"丢了 {self.DELTA_COUNT - len(received)} 条 delta"
        assert received == texts, "顺序被打乱"
        assert [event.get("type") for event in events].count("done") == 2


class TestDisconnectPersistsEveryLane:
    """客户端按停止（断连）时也要按栏落库。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_secondary_partial_body_persisted_on_disconnect(self) -> None:
        """次栏已流出的正文不能因为用户按了停止就永久消失。

        旧实现只在「正常抽干」那条路径上补落库，断连时次栏的正文就此丢失——下次
        打开会话只剩主栏（律师看到的是「右边那栏的回答凭空没了」）。
        """
        # 次栏吐完正文后挂住不返回：断连那一刻它还在飞（最容易被丢掉的状态）
        register(_FakeBackend(PRIMARY, _deltas("主答正文"), delay=0.01))
        register(_FakeBackend(SECONDARY, _deltas("次答正文半截"), block_on=asyncio.Event()))
        session = await _make_session()

        # ``aclose()`` 只在异步生成器上有（返回值声明的是 ``AsyncIterator``）
        stream = cast(
            AsyncGenerator[dict[str, Any], None],
            multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=[PRIMARY, SECONDARY]),
        )
        async for event in stream:
            if event.get("type") == "delta" and event.get("agent") == SECONDARY:
                break  # 次栏已经出字，用户此刻按了停止
        await stream.aclose()

        rows = [m async for m in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]
        secondary_rows = [m for m in rows if m.agent_kind == SECONDARY]
        assert secondary_rows, f"断连时次栏正文没有落库，实际落库：{[(m.agent_kind, m.content) for m in rows]}"
        assert secondary_rows[0].content.strip() == "次答正文半截"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_cancel_while_blocked_on_put_still_closes_the_lane(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """取消落在 ``queue.put`` 上时，那一栏的生成器仍必须在收尾期间被关掉。

        队列有界之后，「被取消」可以落在**生成器外面**（顶在 ``put`` 上）。而
        ``async for`` 提前退出**不会**替调用方 ``aclose()``（PEP 525），
        ``stream_chat`` 的 finally 又是唯一把已流出正文写进 ``memo.parts``、把
        已花 token 记进 ``AgentRun`` 的地方 —— 不显式关，断连时次栏半截正文会
        静默丢失，主栏那条助手行还会改由 asyncgen finalizer 异步补写（晚于收尾
        时同步写的次栏行 ⇒ 回放栏序反转）。

        队列限成 1 格、两栏各吐 20 条：收到第 2 条帧时两条生产者必然都顶在
        ``put`` 上，此刻断开就是上面那个状态。
        """
        monkeypatch.setattr(multi, "_LANE_QUEUE_MAXSIZE", 1)
        closed: list[str] = []
        #: 抓住每一栏生成器的强引用。**必须抓**：被 GC 掉的异步生成器会被事件
        #: 循环的 asyncgen finalizer 异步补一次 ``aclose()``，那样「收尾时有没有
        #: 人显式关它」就验不出来了（变异实验证实：不抓引用时，把修复去掉本用例
        #: 照样绿）。
        keep_alive: list[AsyncGenerator[dict[str, Any], None]] = []
        real_stream_chat = multi.stream_chat

        async def _record_close(**kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            inner = real_stream_chat(**kwargs)
            try:
                async for event in inner:
                    yield event
            finally:
                closed.append(kwargs["agent_kind"])
                # 包装层只负责「记录自己被关」，并把关闭继续传给真正的
                # ``stream_chat``（否则它把被测行为揞住：内层永不跑 finally，
                # 正文永远落不了库）
                try:
                    await inner.aclose()
                except Exception:
                    pass

        def _record_close_factory(**kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            agen = _record_close(**kwargs)
            keep_alive.append(agen)
            return agen

        # 包装层自己能观察到「被关」：只在有人显式关它（或它自己跑完）时跑
        # finally —— 这里要区分的是「从没被关过」
        monkeypatch.setattr(multi, "stream_chat", _record_close_factory)

        register(_FakeBackend(PRIMARY, _deltas(*[f"主{i}" for i in range(50)])))
        register(_FakeBackend(SECONDARY, _deltas(*[f"次{i}" for i in range(50)])))
        session = await _make_session()
        stream = cast(
            AsyncGenerator[dict[str, Any], None],
            multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=[PRIMARY, SECONDARY]),
        )
        seen_agents: set[str] = set()
        async for event in stream:
            if event.get("type") == "delta":
                seen_agents.add(str(event.get("agent")))
            # 两栏都出过字（两边生成器都真的跑起来了，否则 ``aclose()`` 对一个
            # 从没启动过的生成器是空操作，验不出东西），再故意停一会儿：队列只有
            # 1 格，两栏各还有几十帧要吐 → 断开那一刻**两条生产者都顶在 put 上**
            if seen_agents == {PRIMARY, SECONDARY}:
                await asyncio.sleep(0.05)
                break
        await asyncio.wait_for(stream.aclose(), timeout=10)

        # 关键断言：生成器在**收尾期间**就被关了，不是等 GC 的 asyncgen finalizer
        # （task 还挂在 tasks 字典里，GC 根本轮不到它，所以这条断言是硬的）
        assert sorted(closed) == sorted([PRIMARY, SECONDARY]), f"收尾时没有关掉这些栏的生成器：{closed}"
        rows = [m async for m in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]
        assert [m for m in rows if m.agent_kind == SECONDARY], "次栏半截正文没有落库"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_close_completes_when_the_queue_is_full(self) -> None:
        """队列满 + 取消 → 收尾仍能结束（不能死等）。

        ``task.cancel()`` 只打断**一次** await（当时挂着的那个）：被取消那一栏随后
        在 ``finally`` 里把哨兵放进**满**队列时会一直挂着，收尾方如果只是
        ``gather`` 就是死等（SSE 连接再也关不掉）。``multi._join_lanes`` 边等边
        抽干才解得开。这里让慢消费者把队列压满再断开，用超时把「挂住」变成断言。
        """
        texts = [f"第{i}段" for i in range(400)]
        # 常量一旦被调到 ≥400，本用例的场景（队列真的满过）就消失了 —— 必须炸
        # 而不是静默变绿。
        assert len(texts) > multi._LANE_QUEUE_MAXSIZE, "本用例要靠超容量才有意义"
        register(_FakeBackend(PRIMARY, _deltas(*texts)))
        register(_FakeBackend(SECONDARY, _deltas("次答正文半截"), delay=0.005))
        session = await _make_session()

        stream = cast(
            AsyncGenerator[dict[str, Any], None],
            multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=[PRIMARY, SECONDARY]),
        )
        seen = 0
        async for event in stream:
            if event.get("type") != "delta":
                continue
            seen += 1
            if seen == 30:
                break  # 慢前端：30 帧 × 10ms，期间生产者早把 256 的队列顶满
            await asyncio.sleep(0.01)
        await asyncio.wait_for(stream.aclose(), timeout=10)

        rows = [m async for m in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]
        assert [m.agent_kind for m in rows if m.agent_kind == SECONDARY]
