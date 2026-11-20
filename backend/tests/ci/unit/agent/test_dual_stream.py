"""多 agent 并行回答（services/chat/multi.py）的失败矩阵。

四个必须成立的场景（任务书的「失败矩阵」）：

1. **两个都成**：各自的事件都转发，``done`` 只发一次，助手消息两条各带 ``agent_kind``；
2. **一成一败**：失败方只发一条带 ``agent`` 的 ``error``，成功方照常输出；
3. **两个都败**：只发**第一条** ``error``（不堆两条）；
4. **配额不足**：只跑主后端 + 一条 ``activity{status:"degraded", reason}``。

全部离线：注册表注入假后端（``stream()`` 直接吐预置事件），不调真模型、不起子进程。
数据库用 ``django_db(transaction=True)``：``stream_dual`` 内部跨 ``asyncio.gather``
并发写库，非事务型用例的同步包装会让两个协程看到同一份快照。
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

#: 会话自己的后端（主答）。kind 刻意不用 ``pi`` / ``dsh``：那两个名字属于真实
#: 后端，``builtin.ensure_registered()`` 会把它们补进注册表，``pick_secondary``
#: 就会挑到真后端（而不是本测试的假后端），断言随之变成调真模型。
PRIMARY = "fake-primary"
#: 注册表里另一个后端（次答）
SECONDARY = "fake-secondary"

_CAPS = BackendCapabilities(
    streaming=True,
    tool_calls=False,
    approval=False,
    compaction=False,
    steer=False,
)


class _FakeBackend:
    """按预置脚本吐事件（或抛异常）的假后端。

    事件里**不带** ``agent`` / ``run_id``：真实后端会补，但本测试要验的是
    ``dual`` 在合并边界统一补齐，所以脚本里刻意只给 ``type`` 与内容。
    """

    def __init__(self, kind: str, script: list[dict[str, Any]] | BaseException) -> None:
        self.kind = kind
        self.capabilities = _CAPS
        self._script = script

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        if isinstance(self._script, BaseException):
            raise self._script
        for event in self._script:
            # 真实后端会在每个事件前让出一个 tick（读子进程 stdout 的间隙），
            # 假后端显式 await 一次才让两个协程真的交错——否则先起的那一个会
            # 一口气跑完，测不到「并发合并」这件事。
            await asyncio.sleep(0)
            yield event


def _ok_script(text: str) -> list[dict[str, Any]]:
    """一轮成功后端的脚本（delta → usage）。

    **不含 ``done``**：真实后端（``pi_backend`` / ``dsh_backend``）都不发 done，
    收尾事件由编排层 ``stream_chat`` 统一发（见 ``base.py`` 契约与
    ``stream.py`` 的分工）。假后端若自己发一个，``stream_chat`` 会照转，然后在
    函数末尾再补一个——测出来的是「假后端违约」，不是被测代码的行为。
    """
    return [
        {"type": "delta", "content": text},
        {"type": "usage", "input_tokens": 10, "output_tokens": 5},
    ]


def _guard_get_backend(kind: str) -> Any:
    """取后端，并断言「只取本用例注入的假后端」。

    真实后端注册（``pi`` / ``dsh``）一旦被 ``ensure_registered`` 补回注册表，
    ``pick_secondary`` 就会挑到它并真的去跑模型——那既不是本测试要验的东西，
    也会让「两个后端」变成「一个假的一个真的」。这里用断言把这种情况暴露在
    取后端的那一刻，而不是让它伪装成一条内容奇怪的断言失败。
    """
    from apps.agent.backends import get

    backend = get(kind)
    assert isinstance(backend, _FakeBackend), f"取到了真实后端 {kind!r}，注册表未被隔离"
    return backend


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> Any:
    """注册表与 aux 计数都是进程内全局状态：每条用例前后清空。

    同时把内置注册关掉：``stream_chat`` 每轮入口都调 ``ensure_registered()``，
    它会把真实的 ``pi`` / ``dsh`` 补回注册表——那两个才是 ``pick_secondary`` 会
    挑到的「另一个后端」，本测试的假后端被晾在一边。``get_backend`` 处的守卫
    （``_guard_get_backend``）把这种情况变成一条明确的断言，而不是「两栏内容
    一样」这种看不出根因的失败。
    """
    registry_module.clear()
    budget._budget.reset()
    # 两个模块都用 ``from ... import ensure_registered`` 取了本地名，
    # 只改 ``builtin`` 的属性对它们无效，必须逐个替换引用点
    monkeypatch.setattr(stream_module, "ensure_registered", lambda: None)
    monkeypatch.setattr(multi, "ensure_registered", lambda: None)
    monkeypatch.setattr(stream_module, "get_backend", _guard_get_backend)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    yield
    registry_module.clear()
    budget._budget.reset()


async def _make_session(agent_kind: str = PRIMARY) -> AgentSession:
    return await AgentSession.objects.acreate(title="双答", agent_kind=agent_kind)


async def _collect(session: AgentSession) -> list[dict[str, Any]]:
    return [e async for e in multi.stream_dual(session=session, user_message="合同有效吗", user_id=None)]


def _register_pair(
    primary: list[dict[str, Any]] | BaseException, secondary: list[dict[str, Any]] | BaseException
) -> None:
    register(_FakeBackend(PRIMARY, primary))
    register(_FakeBackend(SECONDARY, secondary))


class TestBothSucceed:
    """失败矩阵第 1 行：两个都成，各自正常输出，done 只有一个。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_events_from_both_sides_are_forwarded_and_tagged(self) -> None:
        _register_pair(_ok_script("主答正文"), _ok_script("次答正文"))
        session = await _make_session()

        events = await _collect(session)

        deltas = [e for e in events if e.get("type") == "delta"]
        # 两栏各有一份正文——任务的核心诉求「两边都看得见」
        assert sorted(e["content"] for e in deltas) == ["主答正文", "次答正文"]
        # 每个事件都能被前端分流：agent 已补，run_id 已补且两边不同
        assert {e["agent"] for e in deltas} == {PRIMARY, SECONDARY}
        assert len({e["run_id"] for e in deltas}) == 2

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_done_emitted_per_column(self) -> None:
        """每栏各一个 done，且都带完整 agents 清单。

        **2026-11-19 修正**：这里原先断言「只发一个 done」，前提是「两个 done 会让
        前端在第一栏结束时收尾、另一栏停在生成中」。那个前提是错的——前端
        ``onDone`` 的契约本来就是「按 agent 收那一栏」，只发一个 done 反而让次栏
        永远收不了尾，界面上两栏都是「(无内容)」。真实事故即由此而来。
        """
        _register_pair(_ok_script("A"), _ok_script("B"))
        session = await _make_session()

        events = await _collect(session)

        dones = [e for e in events if e.get("type") == "done"]
        assert len(dones) == len({PRIMARY, SECONDARY})
        # 每栏的 done 指向自己那一栏，前端据此各自收尾
        assert {d["agent"] for d in dones} == {PRIMARY, SECONDARY}
        for done in dones:
            assert done["agents"] == [PRIMARY, SECONDARY]
        # 整轮的最后一个事件仍是 done（前端据此判定本轮结束）
        assert events[-1]["type"] == "done"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_user_message_recorded_once(self) -> None:
        _register_pair(_ok_script("A"), _ok_script("B"))
        session = await _make_session()

        await _collect(session)

        users = await AgentMessage.objects.filter(session=session, role=AgentMessage.Role.USER).acount()
        # 两个后端跑的是同一条提问：各写一次回放里就有两个一模一样的提问
        assert users == 1

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_both_assistant_messages_persisted_with_agent_kind(self) -> None:
        _register_pair(_ok_script("主答正文"), _ok_script("次答正文"))
        session = await _make_session()

        await _collect(session)

        rows = [m async for m in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]
        # 次答不走 stream_chat 的落库（它拿不到 agent_kind），必须由 dual 补写
        assert {m.agent_kind for m in rows} == {PRIMARY, SECONDARY}
        assert {m.content for m in rows} == {"主答正文", "次答正文"}


class TestOneSucceedsOneFails:
    """失败矩阵第 2 行：一个成一个败，失败不阻断另一个。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_secondary_failure_does_not_block_primary(self) -> None:
        _register_pair(_ok_script("主答正文"), RuntimeError("次答炸了"))
        session = await _make_session()

        events = await _collect(session)

        deltas = [e for e in events if e.get("type") == "delta"]
        assert [e["content"] for e in deltas] == ["主答正文"]
        errors = [e for e in events if e.get("type") == "error"]
        # 失败方只发一条 error，且带 agent（前端据此挂到次答那一栏）
        assert len(errors) == 1
        assert errors[0]["agent"] == SECONDARY
        # 仍然有且只有一个 done：主答是成功的，本轮整体正常收尾
        assert [e["type"] for e in events].count("done") == 2  # 每栏各一个

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_primary_failure_does_not_block_secondary(self) -> None:
        _register_pair(RuntimeError("主答炸了"), _ok_script("次答正文"))
        session = await _make_session()

        events = await _collect(session)

        deltas = [e for e in events if e.get("type") == "delta"]
        assert [e["content"] for e in deltas] == ["次答正文"]
        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) == 1
        assert errors[0]["agent"] == PRIMARY
        assert [e["type"] for e in events].count("done") == 2  # 每栏各一个

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_successful_side_still_persisted(self) -> None:
        _register_pair(_ok_script("主答正文"), RuntimeError("次答炸了"))
        session = await _make_session()

        await _collect(session)

        rows = [m async for m in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]
        # 次答失败不该把主答的落库也带走
        assert [m.content for m in rows] == ["主答正文"]
        assert rows[0].agent_kind == PRIMARY


class TestBothFail:
    """失败矩阵第 3 行：两个都败，只发第一条 error。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_only_first_error_emitted(self) -> None:
        _register_pair(RuntimeError("主答炸了"), RuntimeError("次答炸了"))
        session = await _make_session()

        events = await _collect(session)

        errors = [e for e in events if e.get("type") == "error"]
        # 两条 error 在同一个气泡区会渲染成两行，读起来像「失败了两遍」
        assert len(errors) == 1
        # 第一条来自主答（主答先跑），带 agent 供前端归栏
        assert errors[0]["agent"] == PRIMARY

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_done_still_emitted_when_both_fail(self) -> None:
        _register_pair(RuntimeError("主答炸了"), RuntimeError("次答炸了"))
        session = await _make_session()

        events = await _collect(session)

        # 没有 done 的话前端会一直显示「生成中」——失败也必须收尾
        assert [e["type"] for e in events].count("done") == 2  # 每栏各一个（失败也要收尾）


class TestQuotaDegraded:
    """失败矩阵第 4 行：aux 满额时降级为只跑主后端。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_degraded_activity_and_primary_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # aux 席位为 0 = 对比能力关闭（与「席位已被占满」走同一条降级路径）
        monkeypatch.setenv("FACHUAN_AGENT_AUX_SLOTS", "0")
        _register_pair(_ok_script("主答正文"), _ok_script("次答正文"))
        session = await _make_session()

        events = await _collect(session)

        deltas = [e for e in events if e.get("type") == "delta"]
        assert [e["content"] for e in deltas] == ["主答正文"]
        # 降级用 activity.status=degraded 告知，而不是 error：本轮是成功的
        degraded = [e for e in events if e.get("type") == "activity" and e.get("status") == multi.ACTIVITY_DEGRADED]
        assert len(degraded) == 1
        assert degraded[0]["reason"]
        assert [e["type"] for e in events].count("error") == 0
        assert [e["type"] for e in events].count("done") == 1  # 降级为单后端，仍一个

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_degraded_persists_only_primary_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_AUX_SLOTS", "0")
        _register_pair(_ok_script("主答正文"), _ok_script("次答正文"))
        session = await _make_session()

        await _collect(session)

        rows = [m async for m in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]
        assert [m.content for m in rows] == ["主答正文"]


class TestSingleBackendFallback:
    """部署里只有一个后端时退回单后端路径（不是错误态）。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_no_secondary_delegates_to_stream_chat(self) -> None:
        # 只注册会话自己的那个后端：没有可配对的对象
        register(_FakeBackend(PRIMARY, _ok_script("唯一后端")))
        session = await _make_session()

        events = await _collect(session)

        assert [e["content"] for e in events if e.get("type") == "delta"] == ["唯一后端"]
        assert [e["type"] for e in events].count("done") == 1  # 降级为单后端，仍一个


class TestPickSecondary:
    """次答选择规则：注册表里第一个不等于会话主后端的 kind。"""

    def test_returns_first_other_kind(self) -> None:
        register(_FakeBackend(PRIMARY, []))
        register(_FakeBackend(SECONDARY, []))
        session = AgentSession(title="t", agent_kind=PRIMARY)
        assert multi.pick_secondary(session) == SECONDARY

    def test_single_backend_returns_none(self) -> None:
        register(_FakeBackend(PRIMARY, []))
        session = AgentSession(title="t", agent_kind=PRIMARY)
        # None = 双答无从谈起，调用方退回单后端（不是报错）
        assert multi.pick_secondary(session) is None

    def test_blank_session_kind_treated_as_pi(self) -> None:
        register(_FakeBackend("pi", []))
        register(_FakeBackend(SECONDARY, []))
        session = AgentSession(title="t", agent_kind="")
        # 旧数据空串等价于 pi（与 stream_chat 同口径），次答不该是 pi 自己
        assert multi.pick_secondary(session) == SECONDARY


class TestThreeAnswers:
    """三栏以上：验证「多答」不是「双答」的别名。

    这是 v27.20 抽象收敛的核心回归——``multi.stream_multi(kinds=[a, b, c])``
    必须真的跑三个，而不是只有前两个生效。

    为什么单独成类而不是改 ``_register_pair``：双栏路径是 ``dual=true`` 旧前端的
    契约，它的行为必须逐字不变；三栏是新能力，两者不该共用断言。

    **全部用例写成 async 并共用一个事件循环**：Django 异步 ORM 的连接绑定在
    创建它的事件循环上，用 ``asyncio.run`` 分段跑（先建会话、再收集事件）会让
    第二段拿到一个属于已关闭循环的连接，表现为「第三个 agent 静默不产出」——
    排查了很久才发现是测试装置的问题，不是 ``multi`` 的。
    """

    THIRD = "third-agent"

    @classmethod
    async def _collect_three(cls, kinds: list[str]) -> list[dict[str, Any]]:
        session = await _make_session()
        return [
            e async for e in multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=kinds)
        ]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_three_bodies_three_dones_three_run_ids(self) -> None:
        """三栏各一份正文 + 各一个 done + 各一个 run_id。

        run_id 必须互不相同：前端靠它把事件分流到各自的栏，两个后端共用同一个
        run_id 会让它们的 delta 落进同一栏——界面上变成一段混着两个模型的乱码。
        """
        _register_pair(_ok_script("甲"), _ok_script("乙"))
        register(_FakeBackend(self.THIRD, _ok_script("丙")))

        events = await self._collect_three([PRIMARY, SECONDARY, self.THIRD])

        deltas = [e for e in events if e.get("type") == "delta"]
        assert sorted(e["content"] for e in deltas) == ["丙", "乙", "甲"]
        assert {e["agent"] for e in deltas} == {PRIMARY, SECONDARY, self.THIRD}

        dones = [e for e in events if e.get("type") == "done"]
        assert len(dones) == 3
        assert len({e["run_id"] for e in deltas}) == 3

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_aux_seat_held_once_for_whole_round(self) -> None:
        """整轮只占**一个** aux 席位，不是每栏一个。

        实测默认 ``aux_slots() = 4 × 0.25 = 1``。若每栏各抢一个，三栏时后两栏
        必然被挡，界面上「选了三个只出两个」且被挡的栏连原因都看不到。
        """
        _register_pair(_ok_script("甲"), _ok_script("乙"))
        register(_FakeBackend(self.THIRD, _ok_script("丙")))

        await self._collect_three([PRIMARY, SECONDARY, self.THIRD])

        # 跑完必须把席位还回去，否则下一轮永远降级
        assert budget.snapshot()["aux_in_use"] == 0

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_duplicate_kinds_are_deduped(self) -> None:
        """同一个 kind 传两遍只跑一次。

        重复跑同一个后端：两栏共用一份 ``session_id:agent_kind:`` 前缀，run_id
        会撞车，且成本翻倍却得到两个一模一样（且互相串栏）的回答。
        """
        _register_pair(_ok_script("甲"), _ok_script("乙"))
        session = await _make_session()

        assert multi.resolve_kinds(session, [PRIMARY, PRIMARY, SECONDARY]) == [PRIMARY, SECONDARY]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_explicit_single_kind_delegates(self) -> None:
        """只给一个 kind 时走单后端路径，不经过合并逻辑。"""
        _register_pair(_ok_script("甲"), _ok_script("乙"))
        session = await _make_session()

        events = [
            e
            async for e in multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=[PRIMARY])
        ]
        dones = [e for e in events if e.get("type") == "done"]
        assert len(dones) == 1
        # 单栏透传走 ``stream_chat`` 原样（不经过本模块的合并逻辑）——钉住这一点：
        # done 只一条。
        #
        # 但 done **必须带 agent / run_id / finish_reason**：契约已把这几个键
        # 升为每个事件类的公共信封（前端不再靠属性探测判断「这帧是谁发的」），
        # 单栏也不例外——单栏时前端同样要拿 run_id 归集用量与水位。
        assert dones[0]["agent"] == PRIMARY
        assert dones[0]["run_id"].endswith(f":{PRIMARY}:1")
        assert dones[0]["finish_reason"] == "ok"


class _ContextRecordingBackend(_FakeBackend):
    """按预置脚本吐事件，并记下本轮 ``RunContext``（验「三栏拿到同一份 prep」）。"""

    def __init__(self, kind: str, script: list[dict[str, Any]], seen: dict[str, Any]) -> None:
        super().__init__(kind, script)
        self._seen = seen

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        self._seen[self.kind] = ctx
        return self._stream(ctx)


class TestSharedPreStreamPrep:
    """开流前的固定开销对 N 栏是同一个答案，只该算一次。

    回归的是三 agent 同答时每栏各做一遍「铸凭证 + 探 pi session + （无 pi session
    时）查历史」：这三件事只取决于律师、会话、提问，与哪一栏无关。三条都走
    ``sync_to_async(thread_sensitive=True)``（同一线程排队），重复 N 次就是串行
    N 次，全部摊在首字延迟上。

    只断言「调用次数」与「三栏拿到同一份 prep」，不断言耗时——耗时随机器与
    数据库状态漂移，钉不住。
    """

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_prep_computed_once_and_shared_by_all_columns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from collections import Counter

        calls: Counter[str] = Counter()
        seen: dict[str, Any] = {}

        async def _mint(user_id: Any) -> str:
            calls["mint"] += 1
            return "tok-shared"

        async def _probe(session_id: str) -> bool:
            calls["probe"] += 1
            # 无 pi session：逼出历史回退那一段（多答时它也曾被各栏各查一遍）
            return False

        async def _history(session: Any, limit: int = 40) -> list[Any]:
            calls["history"] += 1
            return []

        monkeypatch.setattr(stream_module.env, "mint_user_token", _mint)
        monkeypatch.setattr(stream_module, "probe_pi_session", _probe)
        monkeypatch.setattr(stream_module.persist, "_recent_history", _history)

        for kind in (PRIMARY, SECONDARY, "third-agent"):
            register(_ContextRecordingBackend(kind, _ok_script(kind), seen))
        session = await _make_session()

        events = [
            e
            async for e in multi.stream_multi(
                session=session, user_message="合同有效吗", user_id=7, kinds=[PRIMARY, SECONDARY, "third-agent"]
            )
        ]

        # 三栏同一个律师、同一个会话、同一条提问 → 各算一次就够
        assert calls == {"mint": 1, "probe": 1, "history": 1}, calls
        # 但每一栏都必须真的拿到那份凭证与 prompt：共用的是「算出来的值」，
        # 不是「只有主答有」。少了这个断言，prep 传丢一栏也测不出来。
        assert set(seen) == {PRIMARY, SECONDARY, "third-agent"}
        assert {ctx.user_token for ctx in seen.values()} == {"tok-shared"}
        assert len({ctx.prompt for ctx in seen.values()}) == 1
        # 三栅契约不变：每栏一个 done，整轮仍只落一条用户消息
        assert [e["type"] for e in events].count("done") == 3
        assert await AgentMessage.objects.filter(session=session, role=AgentMessage.Role.USER).acount() == 1

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_mint_failure_keeps_per_column_error_semantics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """预铸凭证失败时的行为必须与「各栏自己铸」逐字一致。

        预铸只是省掉重复劳动，不能改失败语义：那时是每栏各发一条 error，
        全部失败按失败矩阵只转发第一条。若预铸失败就整轮拉倒、或只跑主答，
        律师看到的东西就变了。
        """

        async def _mint(user_id: Any) -> str:
            raise ValueError("用户已停用")

        monkeypatch.setattr(stream_module.env, "mint_user_token", _mint)

        for kind in (PRIMARY, SECONDARY):
            register(_FakeBackend(kind, _ok_script(kind)))
        session = await _make_session()

        events = [
            e
            async for e in multi.stream_multi(
                session=session, user_message="合同有效吗", user_id=7, kinds=[PRIMARY, SECONDARY]
            )
        ]

        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) == 1  # 全部失败：只转发第一条（失败矩阵第 3 行）
        assert errors[0]["agent"] == PRIMARY
        assert [e["type"] for e in events].count("done") == 2  # 失败也要每栏收尾
        # 用户消息在凭证之前就已落库（既有顺序），失败不许把它带走
        assert await AgentMessage.objects.filter(session=session, role=AgentMessage.Role.USER).acount() == 1
        assert await AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT).acount() == 0
