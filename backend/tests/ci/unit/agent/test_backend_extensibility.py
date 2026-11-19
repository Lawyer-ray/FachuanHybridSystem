"""第 4 个 agent 接入时「编排层不需要改动」——独立验证抽象是否真的成立。

本文件**不信任实现者**：它造一个**从未存在过**的第 4 号后端（``fake-4th``），
按规格 §五「接入新 agent 的全部工作 = 写 xxx_backend.py + @register + 一行依赖」
只做后两步，然后断言编排层（``services/chat/multi.py``）能把它当第 N 栏跑完。

## 为什么这些断言值得写（而不是再抄一遍注册表测试）

``tests/ci/unit/agent/test_agent_backends_registry.py`` 验的是「注册表自身的语义」；
本文件验的是**跨层契约**——注册进来自动可编排。两者失败时的排查方向完全不同：

- 注册表测试红 = 注册表坏了；
- 本文件红 = 注册表没问题，但**编排层认识具体 kind 了**（例如写死了
  ``[primary, aux]``、按 kind 分支、或只给「第二个」栏留了位置）。

## 断言清单

A. 注册与发现：``get("fake-4th")`` 取得到、``available_kinds()`` 含它、
   协议可结构化满足（不用继承）、``capabilities`` 保守默认（``concurrent_in_session``
   为 ``False``）、重复 kind 抛错且不静默覆盖。
B. 编排可扩展：``stream_multi(kinds=[pi, dsh, fake-4th])`` 产出 **3 个 done**、
   3 栏正文各一份、事件全部带 ``agent`` / ``run_id``；加第 4 栏同样成立
   （``MAX_ANSWERS`` 之前不看 kind 数量）。
C. 未知 kind 的降级口径：把未注册的 kind 塞进 ``kinds`` 只让**那一栏**失败，
   其余栏照常（编排层不预校验 kind，因此接入期拼错名字不会把整轮打死）。
D. 顺序与配额口径：第 1 栏拿 ``primary`` 配额（不拒绝），其余栏走 ``aux``；
   aux=0 时降级为只跑第 1 栏且**不丢**其它栏之外的事件。

全部离线：假后端的 ``stream()`` 直接吐预置事件，不调模型、不起子进程、不连 MCP。
数据库用 ``django_db(transaction=True)``：``stream_multi`` 内部跨
``asyncio.create_task`` 并发写库，非事务型用例会让两个协程看到同一份快照。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import pytest

from apps.agent.backends import (
    AgentBackend,
    BackendCapabilities,
    RunContext,
    StreamFrame,
    available_kinds,
    get,
    register,
)
from apps.agent.backends import registry as registry_module
from apps.agent.models import AgentMessage, AgentSession
from apps.agent.services.chat import budget, multi
from apps.agent.services.chat import stream as stream_module

#: 规格里已有的两个 kind 与本次要「凭空加进来」的第 3 个。名字都用规格式短标识：
#: ``fake-4th`` 刻意取「第 4 个」而不是 ``fake-third``——它表达的是**未来**那个
#: 后端：写的人除了实现协议什么都不该做。
PI = "fake-pi"
DSH = "fake-dsh"
FOURTH = "fake-4th"
FIFTH = "fake-5th"

#: 新后端在「只声明必须字段」时应得的能力：全部保守（除流式）。
#:
#: ``concurrent_in_session`` 刻意**不写**，走 dataclass 默认值——这条断言就是
#: ``base.py`` 里那段「默认 False 的保守性很重要」的唯一守卫：默认 ``True`` 会让
#: 未验证的新后端被编排层直接并行拉起，污染会话上下文且没有测试能提前发现。
_CONSERVATIVE_CAPS = BackendCapabilities(
    streaming=True,
    tool_calls=True,
    approval=False,
    compaction=False,
    steer=False,
)


class FakeBackend:
    """按预置脚本吐事件的假后端（实现 ``AgentBackend`` 协议，不继承任何基类）。

    事件里**不带** ``agent`` / ``run_id``：真实后端会补，但本文件要验的是编排层
    在合并边界统一补齐（``multi._tag``），所以脚本里刻意只给 ``type`` 与内容。

    ``capabilities`` 用类属性而不是实例属性：注册表里存的是实例，能力是静态声明，
    与 ``PiBackend`` / ``DshBackend`` 的写法一致。
    """

    capabilities = _CONSERVATIVE_CAPS

    def __init__(self, kind: str, script: list[dict[str, Any]] | BaseException | None = None) -> None:
        self.kind = kind
        #: 本后端的 ``stream()`` 被 **next 过几次**（= 起了几条流）。用来验「每一栏都
        #: 真的被拉起过」，而不是只看事件——零事件的失败栏不会留下事件痕迹。
        self.started = 0
        self._script: list[dict[str, Any]] | BaseException = script if script is not None else _ok_script(kind)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        self.started += 1
        if isinstance(self._script, BaseException):
            raise self._script
        for event in self._script:
            # 真实后端在每个事件前让出一个 tick（读子进程 stdout / SSE 的间隙）。
            # 假后端显式 await 一次，才让多栏真的交错——否则先起的那一栏会一口气
            # 跑完，「并发合并」这件事根本没被触发。
            await asyncio.sleep(0)
            yield event


def _ok_script(marker: str) -> list[dict[str, Any]]:
    """一轮成功后端的脚本（delta → usage）。

    **不含 ``done``**：真实后端（``pi_backend`` / ``dsh_backend`` /
    ``openai_agents_backend``）都不发 done，收尾事件由编排层统一发（见 ``base.py``
    契约与 ``stream.py`` 的分工）。假后端若自己发一个，测出来的是「假后端违约」。
    """
    return [
        {"type": "delta", "content": marker},
        {"type": "usage", "input_tokens": 10, "output_tokens": 5},
    ]


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> Any:
    """注册表与 aux 计数都是进程内全局状态：每条用例前后清空。

    同时把 ``ensure_registered`` 关掉并把``get_backend`` 换成只认本用例注入的实例：
    ``stream_chat`` 每轮入口都调 ``ensure_registered()``，它会把真实的 ``pi`` /
    ``dsh`` / ``openai-agents`` 补回注册表——那样测出来的是真后端去连网关，既不是
    本文件要验的东西，也会让「第 N 栏」变成「一个假的后端 + 几个真的」。

    两个模块都用 ``from ... import ensure_registered / get_backend`` 取了本地名，
    只改 ``builtin`` / ``backends`` 的属性对它们无效，必须逐个替换引用点。
    """
    registry_module.clear()
    budget._budget.reset()
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    # aux 席位按满额算（总量 4 时 aux 默认 1 席，三栏场景会被降级——那是另一条
    # 用例专门验的）。这里给足，让「能跑 N 栏」与「配额不足」两件事互不干扰。
    monkeypatch.setenv("FACHUAN_AGENT_AUX_RATIO", "1")
    monkeypatch.setattr(stream_module, "ensure_registered", lambda: None)
    monkeypatch.setattr(multi, "ensure_registered", lambda: None)
    monkeypatch.setattr(stream_module, "get_backend", _injected_backend)
    yield
    registry_module.clear()
    budget._budget.reset()


#: 本用例里注册的假后端实例（kind → 实例）。``_injected_backend`` 从这里取。
_INJECTED: dict[str, FakeBackend] = {}


def _injected_backend(kind: str) -> Any:
    """``stream_chat`` 取后端的位置：只认本文件注入的假后端。

    ``kind`` 不在注入表里时**抛真实后端的那个 ``LookupError``**（而不是断言）：
    多条用例刻意喂未注册的 kind（验「拼错只失败那一栏」），那里必须走生产同款的
    失败路径，断言会把它变成「测试自己抛错了」，验不到编排层的降级。

    抛的异常形状与 ``registry.get`` 一致（带已注册清单），所以编排层侧的行为与
    真环境完全同构。
    """
    backend = _INJECTED.get(kind)
    if backend is None:
        raise LookupError(f"未知 agent backend: {kind!r}；已注册: {sorted(_INJECTED)}")
    return backend


def _install(*kinds: str) -> dict[str, FakeBackend]:
    """按 kind 逐个注册假后端，返回 ``kind → 实例``。

    走生产入口 ``register()``（不是直接塞 ``_BACKENDS``）：注册表语义本身也是被测
    对象之一——绕开它就等于假设「注册这一步不会出错」。
    """
    _INJECTED.clear()
    for kind in kinds:
        backend = FakeBackend(kind)
        register(backend)
        _INJECTED[kind] = backend
    return _INJECTED


async def _make_session(agent_kind: str = PI) -> AgentSession:
    return await AgentSession.objects.acreate(title="多答扩展性", agent_kind=agent_kind)


async def _collect(kinds: list[str], *, session_kind: str = PI) -> list[dict[str, Any]]:
    session = await _make_session(session_kind)
    return [e async for e in multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=kinds)]


async def _collect_keeping_session(kinds: list[str], *, session_kind: str = PI) -> tuple[AgentSession, list[dict[str, Any]]]:
    session = await _make_session(session_kind)
    events = [e async for e in multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=kinds)]
    return session, events


# ── A. 注册与发现 ─────────────────────────────────────────────────────


class TestFourthBackendRegisters:
    """「写 xxx_backend.py + @register」这两步做完，抽象就该认得它。"""

    def test_get_returns_the_registered_instance(self) -> None:
        installed = _install(PI, DSH, FOURTH)
        # 身份相等（不只是「取到一个」，防止注册表把实例又包了一层）
        assert get(FOURTH) is installed[FOURTH]

    def test_available_kinds_includes_it_in_sorted_order(self) -> None:
        _install(PI, DSH, FOURTH)
        # 排序是稳定契约（前端能力探测 / 错误信息都依赖它）；新 kind 自动进榜。
        # 期望值写 sorted(...) 而不是手排：本断言要验的是「在榜且有序」，不是
        # 「这三个字符串按字典序长什么样」——手排一旦写错，失败信息指向的是测试
        # 自己的笔误，而不是注册表。
        assert available_kinds() == sorted([PI, DSH, FOURTH])
        assert FOURTH in available_kinds()

    def test_fake_backend_satisfies_protocol_without_inheritance(self) -> None:
        """第 4 个后端只需**结构上**满足协议，不继承任何基类。

        ``runtime_checkable`` 是「不用继承也能实现」的前提；破了它，整层解耦就
        退回显式基类，接入新 agent 要先改抽象层——正是本规格要消除的。
        """
        assert isinstance(FakeBackend(FOURTH), AgentBackend)

    def test_capabilities_are_conservative_by_default(self) -> None:
        """未显式声明的能力必须落在保守值上（尤其 ``concurrent_in_session``）。"""
        caps = FakeBackend(FOURTH).capabilities
        assert caps.concurrent_in_session is False
        # 其余四项是「如实声明」而非愿望：审批 / 压缩 / 插话新后端都没有，
        # 声明 True 会让前端渲染出不存在的控件（见 base.py 的字段注释）
        assert (caps.approval, caps.compaction, caps.steer) == (False, False, False)
        assert caps.streaming is True


class TestDuplicateKindIsRejected:
    """防静默覆盖：两个模块注册同一个 kind 说明命名冲突或重复实现。"""

    def test_second_registration_of_same_kind_raises(self) -> None:
        _install(FOURTH)
        with pytest.raises(ValueError, match="重复注册"):
            register(FakeBackend(FOURTH))

    def test_original_instance_survives_failed_reregistration(self) -> None:
        """报错之外的另一半：已有的实现必须原封不动。

        静默覆盖的后果是「同一个名字跑出不同行为」，且只在某些 import 顺序下
        复现——排查成本远高于启动时直接炸。
        """
        installed = _install(FOURTH)
        with pytest.raises(ValueError):
            register(FakeBackend(FOURTH))
        assert get(FOURTH) is installed[FOURTH]
        assert FakeBackend(FOURTH).started == 0, "被拒绝注册的实例不该被使用"

    def test_unknown_kind_lists_what_is_available(self) -> None:
        """史拼错 vs 忘了注册：错误信息必须带已注册清单，否则两种情况长得一样。"""
        _install(PI, FOURTH)
        with pytest.raises(LookupError) as excinfo:
            get("fake-4ht")
        message = str(excinfo.value)
        assert "fake-4ht" in message
        assert FOURTH in message and PI in message


# ── B. 编排可扩展：三个 / 四个 kind 不改编排层 ────────────────────────


class TestOrchestrationRunsThreeKinds:
    """核心断言：``[pi, dsh, fake-4th]`` 产出 3 栏，每栏一个 ``done``。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_three_kinds_produce_three_done(self) -> None:
        _install(PI, DSH, FOURTH)

        events = await _collect([PI, DSH, FOURTH])

        dones = [e for e in events if e.get("type") == "done"]
        assert len(dones) == 3
        # 每栏的 done 指向自己那一栏：前端 onDone 的契约就是「这个 done 属于哪个
        # agent，就收哪一栏」，缺一栏那一栏永远停在「生成中」
        assert [d["agent"] for d in dones] == [PI, DSH, FOURTH]
        # 每个 done 都带完整参与方清单
        assert all(d["agents"] == [PI, DSH, FOURTH] for d in dones)
        # 整轮最后一个事件仍是 done（前端据此判定本轮结束）
        assert events[-1]["type"] == "done"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_each_column_has_its_own_body_and_run_id(self) -> None:
        _install(PI, DSH, FOURTH)

        events = await _collect([PI, DSH, FOURTH])

        deltas = [e for e in events if e.get("type") == "delta"]
        # 三份正文，各来自一个后端（假后端的 marker 就是它自己的 kind）
        assert sorted(e["content"] for e in deltas) == sorted([PI, DSH, FOURTH])
        # 分流靠 agent + run_id：两个字段缺任何一个，前端都只能猜
        assert {e["agent"] for e in deltas} == {PI, DSH, FOURTH}
        run_ids = {e["agent"]: e["run_id"] for e in deltas}
        assert set(run_ids) == {PI, DSH, FOURTH}
        assert len(set(run_ids.values())) == 3, f"run_id 必须每栏唯一，实际: {run_ids}"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_meta_declares_all_participants(self) -> None:
        """流开头就把参与方声明出去：前端据此先画出空白栏，而不是等第一份内容。"""
        _install(PI, DSH, FOURTH)

        events = await _collect([PI, DSH, FOURTH])

        meta = next(e for e in events if e.get("type") == "meta")
        assert meta["agents"] == [PI, DSH, FOURTH]
        activity = next(e for e in events if e.get("type") == "activity")
        assert activity["agents"] == [PI, DSH, FOURTH]
        assert activity["status"] == "thinking"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_every_column_really_started(self) -> None:
        """3 个 done 不能靠「编排层凭空补发」凑出来：每个后端的 ``stream()`` 必须真被拉起。

        只看事件的话，一个「起了但立刻失败」的栏也会留下 error + done，与
        「根本没跑」在事件层面难以区分。``started`` 计数把两者分开。
        """
        installed = _install(PI, DSH, FOURTH)

        await _collect([PI, DSH, FOURTH])

        assert {kind: backend.started for kind, backend in installed.items()} == {PI: 1, DSH: 1, FOURTH: 1}

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_four_kinds_reach_max_answers_without_any_kind_branch(self) -> None:
        """``MAX_ANSWERS = 4`` 之内，编排层对 N 没有假设——4 栏同样成立。

        这条断言是「不需要写 quad.py」的直接证据：同一份代码，2→3→4 只改 ``kinds``。
        """
        _install(PI, DSH, FOURTH, FIFTH)

        events = await _collect([PI, DSH, FOURTH, FIFTH])

        dones = [e for e in events if e.get("type") == "done"]
        assert len(dones) == multi.MAX_ANSWERS == 4
        assert {d["agent"] for d in dones} == {PI, DSH, FOURTH, FIFTH}

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_one_assistant_message_per_column_with_agent_kind(self) -> None:
        """非主答正文必须带 ``agent_kind`` 落库，否则历史回放里第 3、4 栏凭空消失。"""
        _install(PI, DSH, FOURTH)

        session, _events = await _collect_keeping_session([PI, DSH, FOURTH])

        rows = [m async for m in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT)]
        assert sorted(m.agent_kind for m in rows) == sorted([PI, DSH, FOURTH])
        assert sorted(m.content for m in rows) == sorted([PI, DSH, FOURTH])
        # 用户消息只有一条：三个后端跑的是同一条提问
        users = await AgentMessage.objects.filter(session=session, role=AgentMessage.Role.USER).acount()
        assert users == 1

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_single_kind_does_not_go_through_merge_path(self) -> None:
        """只有一栏时透传 ``stream_chat``：本轮恰好一个 done、一条助手消息。

        这是「多答」与「单答」的边界——一栏也走合并路径的话，会多绕一层并引入
        「done 长什么样」的第二处定义。
        """
        installed = _install(PI)

        events = await _collect([PI])

        assert [e["type"] for e in events].count("done") == 1
        assert installed[PI].started == 1
        deltas = [e for e in events if e.get("type") == "delta"]
        assert [e["content"] for e in deltas] == [PI]


# ── C. 未知 kind 只失败自己那一栏 ─────────────────────────────────────


class TestUnknownKindDegradesOneColumn:
    """接入期拼错 kind 名字是常态：编排层不预校验，让失败限定在那一栏。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_missing_kind_does_not_kill_the_other_columns(self) -> None:
        _install(PI, DSH, FOURTH)

        events = await _collect([PI, "fake-typo", FOURTH])

        # 两栏是好后端，正文照常
        deltas = [e for e in events if e.get("type") == "delta"]
        assert sorted(e["content"] for e in deltas) == sorted([PI, FOURTH])
        # 拼错的那一栏只留一条 error（前端据此挂到对应栏）
        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) == 1
        # 每栏仍然各收一个 done：三栏都画出来了，就得三栏都收尾
        assert [e["type"] for e in events].count("done") == 3

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_all_columns_failing_emits_one_error(self) -> None:
        """全部失败只发第一条 error：N 条 error 在同一气泡区读起来像失败 N 遍。"""
        _install(PI, DSH)

        events = await _collect([PI, DSH, "fake-missing"])

        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) == 1
        # 仍按栏收尾，否则前端一直显示「生成中」
        assert [e["type"] for e in events].count("done") == 3

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_column_error_event_carries_no_losing_agent(self) -> None:
        """已知缺口（已写进验收报告）：非主答栏的 error **不带** ``agent``。

        ``_pump_one`` 抛错时把 ``agent=""`` 写进事件，而消费侧用
        ``_tag(event, kind, memo)`` 补—— ``setdefault`` 不会覆盖已存在的空串，
        于是这条 error 落到 ``agent=""`` 上，前端无法把它挂回失败的那一栏。

        本断言把**当前行为**钉住（而不是假装它正确）：缺口修好后这里会红，
        届时改成 ``assert errors[0]["agent"] == FOURTH`` 即可。这是本文件唯一一条
        「钉住缺陷」的用例，故意写成断言而不是注释——注释会静静烂掉。
        """
        _install(PI, FakeBackend(FOURTH, RuntimeError("第 3 栏炸了")))
        # 第 3 栏要真的被启动才可能失败，aux 给足
        events = await _collect([PI, DSH, FOURTH])

        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) == 1, f"失败栏只发一条 error，实际: {errors}"
        assert errors[0]["agent"] == "", "缺口已修复？请把断言改成 agent == 失败的那个 kind"


# ── D. 配额按序分档 ──────────────────────────────────────────────────


class TestQuotaAppliesByPositionNotByKind:
    """第一个 kind 拿 ``primary``（不拒绝），其余走 ``aux``（满了降级）。

    断言的是**位置**语义：同一个 kind 放在第 1 位与第 3 位，行为不同；编排层不认识
    具体 kind，只认识列表顺序。
    """

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_aux_disabled_runs_only_the_first_column(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_AUX_SLOTS", "0")
        installed = _install(PI, DSH, FOURTH)

        events = await _collect([PI, DSH, FOURTH])

        # 只有第一栏真的跑了；其余栏一个流都没起（不是「起了又失败」）
        assert {kind: backend.started for kind, backend in installed.items()} == {PI: 1, DSH: 0, FOURTH: 0}
        assert [e["content"] for e in events if e.get("type") == "delta"] == [PI]
        # 降级用 activity.status=degraded 告知（本轮是成功的，只是少了几栏）
        degraded = [e for e in events if e.get("type") == "activity" and e.get("status") == multi.ACTIVITY_DEGRADED]
        assert len(degraded) == 1
        assert degraded[0]["reason"]
        # agents 收窄为单栏，且只发一个 done——否则前端会画出从未有内容的空栏
        assert [e["type"] for e in events].count("done") == 1
        done = next(e for e in events if e.get("type") == "done")
        assert done["agents"] == [PI]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_first_kind_is_never_rejected_by_quota(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """aux 席位为 0 时，第 1 栏照常跑——primary 有保证配额。

        放进第 1 位的是「新后端」而不是 pi：主答身份由**位置**决定，与 kind 无关。
        """
        monkeypatch.setenv("FACHUAN_AGENT_AUX_SLOTS", "0")
        installed = _install(PI, FOURTH)

        events = await _collect([FOURTH, PI])

        assert installed[FOURTH].started == 1
        assert [e["content"] for e in events if e.get("type") == "delta"] == [FOURTH]
        assert [e["type"] for e in events].count("error") == 0

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_secondary_columns_release_aux_slots(self) -> None:
        """aux 是**准入计数**不是长占位：一轮结束后必须归零，否则下一轮全部降级。

        三栏并发时同时持有 2 个 aux 席位，任何一处提前释放 / 忘记释放都会让
        ``snapshot()`` 停在非零值上——那是「第一轮好好的，之后全降级」的根因。
        """
        _install(PI, DSH, FOURTH)

        await _collect([PI, DSH, FOURTH])

        assert budget.snapshot()["aux_in_use"] == 0


# ── E. 反向守卫：新增 kind 不必改动编排层的哪一处 ────────────────────


class TestOrchestrationLayerDoesNotKnowKinds:
    """结构性断言：编排层的源码里不该出现任何具体 kind 字面量。

    这条用 AST 扫也太重；直接读源码字符串做**排除式**断言足够——它要挡的是
    「有人为了方便又写一句 ``if kind == "dsh":``」，那种改动一定是可见字面量。
    """

    #: 真后端 kind 的字面量。``fake-`` 前缀的不列：本文件自己的假后端名字出现在
    #: 编排层才是问题，但那属于同一条守卫。
    KNOWN_KINDS = ("dsh", "deepseek-harness", "openai-agents")

    #: 允许存在的唯一 kind 字面量：``"pi"`` 是**历史数据的回落默认值**（旧会话的
    #: ``agent_kind`` 是空串，等价于引入多后端之前的 pi 行为）。它出现在
    #: ``primary_kind`` 里是「向后兼容」而不是「按 kind 分支」——两者形状一样、
    #: 后果相反，所以这里只允许它出现在那一个函数的原文里，别处出现仍然算退化。
    ALLOWED_LITERAL = '"pi"'
    ALLOWED_IN_FUNCTION = "primary_kind"

    def test_multi_module_contains_no_backend_kind_branch(self) -> None:
        import inspect
        import re

        source = inspect.getsource(multi)
        # 逐行匹配带引号的 kind 字面量；短名容易误伤（"api" / "pipeline" 里的
        # 子串），所以要求引号包住整个词
        for kind in self.KNOWN_KINDS:
            pattern = re.compile(rf"""["']{re.escape(kind)}["']""")
            assert not pattern.search(source), f"编排层出现了具体 kind 字面量 {kind!r}——抽象退化了"

        # ``"pi"`` 只允许出现在回落默认值那一处
        offending = [
            line
            for line in source.splitlines()
            if self.ALLOWED_LITERAL in line and "agent_kind" not in line
        ]
        assert not offending, f"``\"pi\"`` 只允许用于 agent_kind 回落，实际出现在: {offending}"
        fallback = inspect.getsource(multi.primary_kind)
        assert self.ALLOWED_LITERAL in fallback, "回落默认值应当只留在 primary_kind 里，便于一处审计"

    def test_resolve_kinds_accepts_arbitrary_strings(self) -> None:
        """``resolve_kinds`` 只做去重 / 空值处理，不做「认识的 kind 才放行」。"""
        session = AgentSession(title="t", agent_kind=PI)
        resolved = multi.resolve_kinds(session, [FOURTH, FIFTH, FOURTH, ""])
        assert resolved == [FOURTH, FIFTH]

    def test_resolve_kinds_falls_back_to_primary_plus_secondary(self) -> None:
        """``kinds=None``（旧前端 ``dual=True`` 路径）仍按「主 + 次」补齐。"""
        _install(PI, DSH, FOURTH)
        session = AgentSession(title="t", agent_kind=PI)
        # 次选取注册表里**第一个不等于主**的 kind（``available_kinds()`` 有序），
        # 所以期望值必须与注册表同源而不是手写一个写死 order 的名字
        expected = [PI, next(k for k in available_kinds() if k != PI)]
        assert multi.resolve_kinds(session, None) == expected
        assert multi.resolve_kinds(session, []) == expected


async def _drain(gen: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:
    """把任意异步迭代器抽成列表（保持与 ``_collect`` 同口径，便于逐条阅读）。"""
    return [event async for event in gen]


class TestCollectHelperContract:
    """``_collect`` 自身的行为守卫：本文件其余断言都建立在它之上。

    零断言的测试会被 ``test_test_quality_ratchet.py`` 判为反模式；这条同时确保
    「事件列表非空」不是靠隐式约定——空列表会让 ``next(...)`` 抛 StopIteration，
    失败信息会指向错误的方向（看起来像编排层没发事件，实际是测试写错）。
    """

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_collect_returns_events_with_types(self) -> None:
        _install(PI)
        events = await _drain(multi.stream_multi(session=await _make_session(), user_message="q", user_id=None, kinds=[PI]))
        assert events, "至少要有 meta / activity / delta / done"
        assert all(isinstance(e.get("type"), str) for e in events)
