"""「每栏可指定模型」不能弄坏的既有契约 —— 五条独立的回归护栏。

本文件**只防回归**，不重复验证新能力本身（那是 ``scripts/verify_per_agent_model.py``
的活）。每条用例的起点都是「为了让某一栏换模型而改动编排/落库/事件分流时，
最容易顺手弄坏的既有行为」，并且每条断言都写清它防的是哪一次修复：

A. **每栏一个 done**（v27.19.1 契约）：``stream_multi`` 必须给每一栏各发一个
   ``done``，且每栏的 ``done`` 指向自己那一栏、``agents`` 仍是全量。
B. **辅助席位整轮一个**（v27.20 修复）：一轮 N 栏共占**一个** aux 席位，不是每栏
   各抢一个——默认 ``aux_slots() = 4 × 0.25 = 1``，每栏一个的话三栏会静默掉两栏。
C. **工具事件按 agentKind 归位**（v27.20.1 修复）：每栏调的工具事件必须带
   ``agent`` / 各自的 ``run_id``，且工具结果落库时带正确的 ``agent_kind``。
D. **指定模型不让 run_id 撞车**：``run_id = {session_id}:{agent_kind}:1`` 的后缀
   恒为 1（见 ``stream.py``），多栏并行的唯一性完全靠中间的 ``agent_kind``。
   一旦有人为了「同一后端两个模型」把模型塞进 run_id 或把后缀改成共享计数，
   前端会按错误的键分栏、``AgentRun`` 成本会串账。
E. **模型逐栏落到后端**：``specs`` 里每栏的 ``model`` 必须原样进 ``RunContext.model``
   （未指定的栏是 ``None``，不能继承相邻栏），且写进 ``AgentRun.model`` 与助手
   消息 ``metadata["model"]``——两处必须一致。

全部离线：注册表注入假后端（``stream()`` 吐预置事件），不调模型、不起子进程、
不连 MCP、不读写真实网关。数据库用 ``django_db(transaction=True)``：
``stream_multi`` 跨 ``asyncio.create_task`` 并发写库，非事务型用例会让两个协程
看到同一份快照。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from apps.agent.backends import BackendCapabilities, RunContext, register
from apps.agent.backends import registry as registry_module
from apps.agent.models import AgentMessage, AgentRun, AgentSession
from apps.agent.services.chat import budget, multi
from apps.agent.services.chat import stream as stream_module
from apps.agent.services.chat.multi import AgentSpec

#: 三个都**不是**真实 kind 的假后端名：``pi`` / ``dsh`` / ``openai-agents`` 属于
#: 真实后端，``builtin.ensure_registered()`` 会把它们补回注册表，于是
#: ``pick_secondary`` / ``get_backend`` 会挑到真后端并真的去连网关。
COLUMN_A = "fake-model-a"
COLUMN_B = "fake-model-b"
COLUMN_C = "fake-model-c"

#: 三个「不同模型」。本文件不验模型是否被真的送到网关（那需要真后端），只验
#: 指定模型这件事**没有改变**栏位、席位、工具归位与 run_id 的既有口径。
MODEL_A = "model-alpha"
MODEL_B = "model-beta"
MODEL_C = "model-gamma"

_CAPS = BackendCapabilities(
    streaming=True,
    tool_calls=True,
    approval=False,
    compaction=False,
    steer=False,
    concurrent_in_session=True,
)


class _FakeBackend:
    """按预置脚本吐事件的假后端，并把 ``ctx.model`` 记下来供断言。

    记 ``ctx.model`` 而不是 mock ``stream_chat``：``RunContext.model`` 是编排层
    与后端之间**唯一**的模型传递缝（见 ``base.py`` 的 ``RunContext.model`` 注释），
    从它这里看才是「后端真的收到了这个模型」，而不是「编排层以为它传了」。
    """

    capabilities = _CAPS

    def __init__(self, kind: str, script: list[dict[str, Any]]) -> None:
        self.kind = kind
        self._script = script
        #: 每轮 ``stream()`` 收到的 ``RunContext.model``（按调用顺序）。
        self.models: list[str | None] = []
        #: 每轮 ``stream()`` 收到的 ``run_id``（按调用顺序）。
        self.run_ids: list[str] = []

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        self.models.append(ctx.model)
        self.run_ids.append(ctx.run_id)
        for event in self._script:
            # 真实后端每读一条子进程输出就让出一次控制权。假后端显式让出，多栏
            # 才会真的交错——否则先起的那一栏一口气跑完，「并发合并」没被触发。
            await asyncio.sleep(0)
            yield event


def _script(text: str, *, tool: str | None = None) -> list[dict[str, Any]]:
    """一轮成功后端的脚本；``tool`` 不为空时插一次工具调用与结果。

    **不含 ``done``**：三个真实后端都不发 done（``pi`` / ``dsh`` 由编排层发，
    ``openai-agents`` 自己发），假后端若自己发一个，测出来的是「假后端违约」。
    """
    events: list[dict[str, Any]] = [{"type": "delta", "content": text}]
    if tool:
        events.append({"type": "tool_call", "tool_call_id": f"call-{text}", "name": tool, "arguments": "{}"})
        events.append({"type": "tool_result", "tool_call_id": f"call-{text}", "name": tool, "result": "ok"})
    events.append({"type": "usage", "input_tokens": 10, "output_tokens": 5})
    return events


#: 本用例注册的假后端实例（kind → 实例）。``_injected_backend`` 从这里取。
_INJECTED: dict[str, _FakeBackend] = {}


def _injected_backend(kind: str) -> Any:
    """``stream_chat`` 取后端的位置：只认本文件注入的假后端。

    不在注入表里就把 ``get_backend`` 的异常原样抛出去（而不是断言）：本文件
    不验未知 kind 的降级，但保持与生产同构比「测试自己抛错」更有价值。
    """
    backend = _INJECTED.get(kind)
    if backend is None:
        raise LookupError(f"未知 agent backend: {kind!r}；已注册: {sorted(_INJECTED)}")
    return backend


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> Any:
    """注册表与配额计数都是进程内全局状态：每条用例前后清空。

    - 关掉 ``ensure_registered``：``stream_chat`` 每轮入口都会调用它，它会把真实
      的 ``pi`` / ``dsh`` / ``openai-agents`` 补回注册表，于是用例里的三栏会变成
      「一个假后端 + 两个真后端连网关」。
    - aux 席位给足（ratio=1）：默认 ``4 × 0.25 = 1`` 席，三栏会被降级——那是
      B 段**专门**验的行为，不该让 A/C/D 段的用例跟着降级变成两栏。
    - ``budget._budget.reset()``：席位是模块级计数，漏掉它会让上一条用例的占用
      泄漏到下一条，表现为「同一条用例单跑绿、全套跑红」。
    """
    registry_module.clear()
    budget._budget.reset()
    _INJECTED.clear()
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    monkeypatch.setenv("FACHUAN_AGENT_AUX_RATIO", "1")
    # 这两个模块都用 ``from ... import ...`` 取了本地名，只改 ``builtin`` /
    # ``backends`` 的属性对它们无效，必须逐个替换引用点。
    monkeypatch.setattr(stream_module, "ensure_registered", lambda: None)
    monkeypatch.setattr(multi, "ensure_registered", lambda: None)
    monkeypatch.setattr(stream_module, "get_backend", _injected_backend)
    yield
    registry_module.clear()
    budget._budget.reset()
    _INJECTED.clear()


def _install(*specs: tuple[str, str, str | None]) -> dict[str, _FakeBackend]:
    """注册若干假后端：``(kind, 正文标记, 工具名)``。"""
    for kind, marker, tool in specs:
        backend = _FakeBackend(kind, _script(marker, tool=tool))
        register(backend)
        _INJECTED[kind] = backend
    return _INJECTED


async def _make_session(agent_kind: str = COLUMN_A) -> AgentSession:
    return await AgentSession.objects.acreate(title="每栏模型回归", agent_kind=agent_kind)


async def _collect_three() -> list[dict[str, Any]]:
    _install(
        (COLUMN_A, "甲", "read_attachment"),
        (COLUMN_B, "乙", "list_cases"),
        (COLUMN_C, "丙", "search_laws"),
    )
    session = await _make_session()
    return [
        event
        async for event in multi.stream_multi(
            session=session,
            user_message="合同有效吗",
            user_id=None,
            kinds=[COLUMN_A, COLUMN_B, COLUMN_C],
        )
    ]


class TestOneDonePerColumn:
    """A. 三栏同答仍然「每栏一个 done」，且每个 done 指向自己那一栏。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_three_columns_emit_three_dones(self) -> None:
        """3 栏 → 恰好 3 个 done，agent 集合 = 三栏，agents 字段仍是全量。

        防的回归：v27.19.1 之前是「整轮只发一个 done」，前端 ``onDone`` 的契约
        是「这个 done 属于哪个 agent，就收哪一栏」，只发一个会让其余栏永远停在
        「生成中」，界面上全是「(无内容)」（真实事故）。为了让「每栏显示自己的
        模型」而改 done 的形状（例如把 model 塞进 done、顺手合并成一条）就会
        把这个事故放回来。
        """
        events = await _collect_three()

        dones = [event for event in events if event.get("type") == "done"]
        assert len(dones) == 3, f"每栏一个 done 是 v27.19.1 的契约，实际 {dones}"
        assert {done["agent"] for done in dones} == {COLUMN_A, COLUMN_B, COLUMN_C}
        # 每个 done 都带这一轮的全量参与方：前端/日志据它知道本轮有谁参与
        for done in dones:
            assert done["agents"] == [COLUMN_A, COLUMN_B, COLUMN_C]
        # 整轮最后一个事件仍是 done（前端据此判定本轮结束）
        assert events[-1]["type"] == "done"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_each_column_body_lands_in_its_own_column(self) -> None:
        """三份正文各归各栏（delta 带 agent），且三份助手消息都落库。

        防的回归：``_persist_answer`` 给非主答补写正文时漏掉 ``agent_kind``，
        或栏位标签被改成「按模型分组」——两者都会让回放里只剩一条或串栏。
        """
        events = await _collect_three()

        deltas = [event for event in events if event.get("type") == "delta"]
        assert sorted((event["agent"], event["content"]) for event in deltas) == [
            (COLUMN_A, "甲"),
            (COLUMN_B, "乙"),
            (COLUMN_C, "丙"),
        ]
        session = await AgentSession.objects.order_by("-id").afirst()
        rows = [row async for row in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]
        assert {row.agent_kind for row in rows} == {COLUMN_A, COLUMN_B, COLUMN_C}


class TestAuxSeatHeldOncePerRound:
    """B. 辅助席位仍是「整轮一个」，没有退回「每栏一个」。

    ## 为什么「抢了几次」必须自己数（不能只看 ``aux_in_use`` 收尾或峰值）

    两种错误实现会在 ``aux_in_use`` 上完全看不出区别：

    - 正确：整轮 ``async with budget.reserve("aux")`` 一次；
    - 错误：每栏各 ``reserve("aux")`` 一次——各栏**串行**跑时，前一个在后一个
      进来前就还了，占用峰值同样是 1，收尾同样是 0。

    但后者在默认配置（``aux_slots() = 4 × 0.25 = 1``）下会被闸门挡掉，症状正是
    v27.20 修的那个「选了三个只出两个，且被挡的栏连原因都没有」。所以断言的是
    **调用次数**：整轮只能进一次 ``reserve``。

    注意 ``@asynccontextmanager`` 生成器的函数体在 ``__aenter__`` 时才执行，
    因此「累计违反配额」必须在包装器里记成**即时**失败：只在收尾断言计数的话，
    ``_hold_aux`` 会把 ``BudgetExceeded`` 吞成「降级为单栏」，三栏测试变成两栏
    还照样绿。
    """

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_round_enters_aux_gate_exactly_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """跑三栏只进一次 aux 闸门，且三栏真的都跑了。

        防的回归（v27.20 修的就是这个）：实测默认 ``aux_slots() = 4 × 0.25 = 1``。
        若有人为了让「每栏还能各自换模型」而去掉 ``_hold_aux``、改成每栏各
        ``reserve("aux")``，三栏里后两栏必然被挡——界面上「选了三个只出两个」。
        为了让这条在默认配额下就必然暴露，这里**不再放大配额**（把默认的
        ``FACHUAN_AGENT_AUX_RATIO=1`` 撤销，回到生产默认的 0.25）。
        """
        monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
        violations: list[str] = []
        enters: list[str] = []
        original_reserve = budget.reserve

        def _tracking_reserve(purpose: str = "primary") -> Any:
            return _TrackingContext(original_reserve(purpose), purpose, enters, violations)

        monkeypatch.setattr(budget, "reserve", _tracking_reserve)

        events = await _collect_three()

        assert violations == [], f"一轮里退回了「每栏各抢一个 aux 席位」：{violations}"
        assert enters == ["aux"], f"整轮只该进一次 aux 闸门（v27.20），实际 {enters}"
        # 三栏都真的跑完了：闸门再多进一次就会在这里变成 2 个 done
        assert len([event for event in events if event.get("type") == "done"]) == 3
        # 席位必须归还，否则下一轮永远降级
        assert budget.snapshot()["aux_in_use"] == 0


class _TrackingContext:
    """包一层 ``budget.reserve(...)`` 的上下文管理器，记录进入次数与超额进入。

    超额进入**立刻**记进 ``violations``（而不是抛异常）：抛出去会被 ``_hold_aux``
    当成「配额已满」降级成单栏，测试就发现不了闸门被重复进入——这正是要防的
    那个静默降级。
    """

    def __init__(self, inner: Any, purpose: str, enters: list[str], violations: list[str]) -> None:
        self._inner = inner
        self._purpose = purpose
        self._enters = enters
        self._violations = violations

    async def __aenter__(self) -> Any:
        self._enters.append(self._purpose)
        if self._enters.count("aux") > 1:
            self._violations.append(f"第 {self._enters.count('aux')} 次进入 aux 闸门（整轮只该一次）")
        return await self._inner.__aenter__()

    async def __aexit__(self, *exc_info: Any) -> Any:
        return await self._inner.__aexit__(*exc_info)


class TestToolEventsStayAttributed:
    """C. 工具调用 / 结果仍按 agentKind 归位到各自那一栏（v27.20.1）。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_tool_events_carry_agent_and_distinct_run_ids(self) -> None:
        """每栏的 ``tool_call`` / ``tool_result`` 都带自己的 ``agent`` 与 ``run_id``。

        防的回归：为了让「栏头显示模型」而在合并边界改写事件（例如统一覆盖
        ``agent``、或按第一次出现的 kind 写死），工具事件会全部挂到第一栏——
        律师看到的证据链错位，且不会报任何错。
        """
        events = await _collect_three()

        tool_events = [event for event in events if event.get("type") in {"tool_call", "tool_result"}]
        assert len(tool_events) == 6, f"三栏各一次调用+结果，实际 {tool_events}"
        by_agent: dict[str, set[str]] = {}
        for event in tool_events:
            assert event.get("agent") in {COLUMN_A, COLUMN_B, COLUMN_C}, event
            assert event.get("run_id"), f"工具事件缺 run_id 就无法归栏：{event}"
            by_agent.setdefault(event["agent"], set()).add(event["run_id"])
        assert set(by_agent) == {COLUMN_A, COLUMN_B, COLUMN_C}
        # 每一栏的调用与结果用同一个 run_id（同一次运行产出的两条事件）
        # —— 两个事件共用 run_id，但不同栏之间必须不同，否则前端会把它们归到一起
        for agent, run_ids in by_agent.items():
            assert len(run_ids) == 1, f"{agent} 这一栏的 run_id 不一致：{run_ids}"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_tool_results_persisted_with_own_agent_kind(self) -> None:
        """工具结果落库时带**自己那一栏**的 ``agent_kind``。

        防的回归：``stream.py`` 里 ``_persist_tool_message(..., backend.kind)``
        若被改成写会话的 ``agent_kind``（或空串），回放时三栏的证据会全部标成
        主答那一家，历史记录里分不出「哪条证据是谁查的」。
        """
        await _collect_three()

        session = await AgentSession.objects.order_by("-id").afirst()
        rows = [row async for row in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.TOOL)]
        assert sorted(row.agent_kind for row in rows) == [COLUMN_A, COLUMN_B, COLUMN_C]
        assert sorted(row.tool_name for row in rows) == ["list_cases", "read_attachment", "search_laws"]


class TestRunIdUniqueness:
    """D. 指定模型后 run_id 仍然互不相同、且仍按 kind 区分。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_run_ids_are_unique_per_column(self) -> None:
        """三栏的 ``run_id`` 互不相同，且后缀仍是固定的 ``:1``。

        防的回归（本次改动的直接风险）：``run_id = f"{session_id}:{agent_kind}:1"``
        的后缀是**固定 1**，多栏并行的唯一性完全来自中间的 ``agent_kind``。
        若有人为了让「同一个后端换不同模型」也各占一栏，把模型拼进 run_id、
        或把后缀改成跨栏共享的轮次计数，就会出两种事故：

        - 两栏 run_id 相同 → 前端按 run_id 分栏时两份回答串成一栏；
        - 后缀不再是 ``:1`` → 审批回调（``FACHUAN_RUN_ID`` 二级寻址）与
          ``backend.result_for(run_id)`` 对不上，成本与水位归到错的栏。

        断言「后缀是 ``:1``」而不是只断言「互不相同」：后者在把后缀改成
        ``:2`` / ``:3`` 时仍然绿，而那种改动已经破坏了外部契约。
        """
        events = await _collect_three()

        deltas = [event for event in events if event.get("type") == "delta"]
        run_ids = {event["run_id"] for event in deltas}
        assert len(run_ids) == 3, f"三栏必须三个 run_id，实际 {run_ids}"
        session = await AgentSession.objects.order_by("-id").afirst()
        session_id = str(session.session_id)
        assert run_ids == {f"{session_id}:{kind}:1" for kind in (COLUMN_A, COLUMN_B, COLUMN_C)}

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_run_id_shape_is_kind_only(self) -> None:
        """``run_id`` 的中间段只能是 kind，不能出现模型名或别的维度。

        防的回归：「给同一后端换不同模型各占一栏」最诱人的实现是把模型拼进
        ``run_id``（``{session}:{kind}:{model}:1``）来区分。那会同时破坏三处：
        审批回调的 ``FACHUAN_RUN_ID`` 二级寻址、前端按 run_id 分栏的契约、
        ``backend.result_for(run_id)`` 的成本归因。模型的唯一去处是
        ``RunContext.model``（见下一条用例），不进 run_id。
        """
        await _collect_three()

        session = await AgentSession.objects.order_by("-id").afirst()
        session_id = str(session.session_id)
        for kind, backend in _INJECTED.items():
            assert len(backend.run_ids) == 1, f"{kind} 这一栏起了 {len(backend.run_ids)} 条流"
            assert backend.run_ids[0] == f"{session_id}:{kind}:1"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_agent_run_rows_stay_per_column(self) -> None:
        """三栏各落一条 ``AgentRun``，成本不会因为多栏而合并或丢失。

        防的回归：为了让「每栏模型不同」而把 ``AgentRun`` 改成按会话汇总（一条
        记录混三个模型），成本归因立刻失去模型维度——而这次改动的**全部意义**
        就是让不同模型各答一次，账却对不上谁的模型贵。
        """
        await _collect_three()

        session = await AgentSession.objects.order_by("-id").afirst()
        runs = [run async for run in AgentRun.objects.filter(session=session)]
        assert len(runs) == 3, f"三栏各一条 AgentRun，实际 {len(runs)}"
        assert {run.status for run in runs} == {AgentRun.Status.OK}


class TestPerColumnModelHandoff:
    """E. 每栏的模型逐栏落到 ``RunContext.model``（本次改动的核心缝）。

    ``ctx.model`` 是编排层与后端之间**唯一**的模型传递方式（见 ``base.py`` 的
    ``RunContext.model`` 注释：``None`` = 由后端按自身默认策略选）。dsh /
    openai-agents 把它转成网关的 ``model``，pi 用 ``ctx.model or _resolve_model()``；
    编排层则由 ``stream_chat(model=...)`` 填进 ``RunContext``。
    """

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_unspecified_model_reaches_backend_as_none(self) -> None:
        """没指定模型的栏，后端收到的必须是 ``None``（回落平台默认）。

        防的回归：``kinds=`` 老入口（以及 ``dual=true`` 老前端）不知道模型，它转
        成的 ``AgentSpec(kind, None)`` 一旦被写成「空串」或「沿用上一栏」，后端就
        会拿 ``""`` / 别人的模型去起进程——``kimi-2.6`` 与 ``glm53`` 混跑时表现
        为「答案不对」而不是报错，是最难查的一类串号。
        """
        await _collect_three()

        assert {kind: backend.models for kind, backend in _INJECTED.items()} == {
            COLUMN_A: [None],
            COLUMN_B: [None],
            COLUMN_C: [None],
        }

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_per_column_model_reaches_each_backend(self) -> None:
        """三栏各指定不同模型：逐栏落到后端，且未指定的那栏仍是 ``None``。

        断言三件事，缺一条就掩盖另一条：

        - 指定的两栏各收到自己的模型（不是都跑默认，也不是互相串）；
        - 未指定的那一栏仍是 ``None``（不能被相邻栏的模型污染）；
        - ``run_id`` 仍只由 kind 决定（模型不进 run_id，见 D 段）。
        """
        _install((COLUMN_A, "甲", None), (COLUMN_B, "乙", None), (COLUMN_C, "丙", None))
        session = await _make_session()
        session_id = str(session.session_id)
        events = [
            event
            async for event in multi.stream_multi(
                session=session,
                user_message="合同有效吗",
                user_id=None,
                specs=[
                    AgentSpec(kind=COLUMN_A, model=MODEL_A),
                    AgentSpec(kind=COLUMN_B, model=MODEL_B),
                    AgentSpec(kind=COLUMN_C),
                ],
            )
        ]

        assert [event for event in events if event.get("type") == "error"] == []
        assert _INJECTED[COLUMN_A].models == [MODEL_A]
        assert _INJECTED[COLUMN_B].models == [MODEL_B]
        assert _INJECTED[COLUMN_C].models == [None]
        for kind, backend in _INJECTED.items():
            assert backend.run_ids == [f"{session_id}:{kind}:1"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_model_written_to_run_and_message_metadata(self) -> None:
        """指定的模型要落进 ``AgentRun.model`` 与助手消息的 ``metadata["model"]``。

        防的回归：``stream_chat`` 里 `"model": model or ""` 那两处一旦退回
        「只在后端回报时才写」，用户选的模型在成本记录里就变成空串——而这次
        改动的全部价值就是「不同模型各答一次」，账上却看不出用了哪个。两个来源
        必须**一致**：不一致说明有两处各自推导模型（漂移的开始）。
        """
        _install((COLUMN_A, "甲", None), (COLUMN_B, "乙", None), (COLUMN_C, "丙", None))
        session = await _make_session()
        async for _ in multi.stream_multi(
            session=session,
            user_message="合同有效吗",
            user_id=None,
            specs=[AgentSpec(kind=COLUMN_A, model=MODEL_A)],
        ):
            pass

        runs = [run async for run in AgentRun.objects.filter(session=session)]
        rows = [row async for row in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]
        assert [run.model for run in runs] == [MODEL_A]
        assert [(row.metadata or {}).get("model") for row in rows] == [MODEL_A]
