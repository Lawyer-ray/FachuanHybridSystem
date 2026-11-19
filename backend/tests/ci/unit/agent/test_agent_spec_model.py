"""每栏模型选择（v27.21）—— 后端侧的归一化与贯通。

规格见 ``docs/04-计划/活跃/每栏模型选择规格.md``。本文件只验「模型选得对不对」，
不验 UI、不调真模型，也不起任何子进程：

1. **``normalize_agents`` 三种输入形态**：纯字符串 / dict / ``AgentSpec``，可混用，
   按 kind 去重且保留第一个模型；
2. **老前端兼容**：``MessageIn`` 收 ``["pi", "dsh"]`` 与 ``[{kind,model}]`` 都不 422；
3. **模型贯通到 ``RunContext``**：``stream_chat(model=...)`` 真的写进 ctx，
   不给时仍是 ``None``（老路径逐字不变）；
4. **``stream_multi`` 每栏各带自己的模型**（主答与次答都要，漏一个就退化成
   「三栏同模型」且没有任何报错）；
5. **pi 读 ``ctx.model``**：显式指定优先于平台默认，为空才回落
   ``_resolve_model()``。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from apps.agent.backends import BackendCapabilities, RunContext, register
from apps.agent.backends import registry as registry_module
from apps.agent.models import AgentSession
from apps.agent.schemas import MessageIn
from apps.agent.services.chat import budget, multi
from apps.agent.services.chat import stream as stream_module

#: 假后端 kind。刻意不用真实后端的名字：``ensure_registered()`` 会把 ``pi`` /
#: ``dsh`` 补回注册表，那两个会真的去跑模型。
PRIMARY = "spec-primary"
SECONDARY = "spec-secondary"

_CAPS = BackendCapabilities(
    streaming=True,
    tool_calls=False,
    approval=False,
    compaction=False,
    steer=False,
)


class _RecordingBackend:
    """记录每次收到的 ``RunContext``，吐一段 delta 收工。"""

    def __init__(self, kind: str, text: str = "答") -> None:
        self.kind = kind
        self.capabilities = _CAPS
        self.contexts: list[RunContext] = []
        self._text = text

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        self.contexts.append(ctx)
        await asyncio.sleep(0)
        yield {"type": "delta", "content": self._text}


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> Any:
    """注册表 / aux 计数是进程内全局状态：每条用例前后清空，并关掉内置注册。"""
    registry_module.clear()
    budget._budget.reset()
    monkeypatch.setattr(stream_module, "ensure_registered", lambda: None)
    monkeypatch.setattr(multi, "ensure_registered", lambda: None)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    yield
    registry_module.clear()
    budget._budget.reset()


# ── 1. 归一化 ────────────────────────────────────────────────


class TestNormalizeAgents:
    """``normalize_agents`` 认三种形态（可混用）并按 kind 去重。"""

    def test_strings_only_is_the_legacy_shape(self) -> None:
        """老前端 ``["pi", "dsh"]`` → 两个只带 kind 的 spec（模型走平台默认）。"""
        specs = multi.normalize_agents(["pi", "dsh"])
        assert specs == [multi.AgentSpec(kind="pi"), multi.AgentSpec(kind="dsh")]
        assert [s.model for s in specs] == [None, None]

    def test_dicts_carry_model_per_column(self) -> None:
        """新前端 ``[{kind, model}]`` → 每栏各自的模型。"""
        specs = multi.normalize_agents(
            [{"kind": "pi", "model": "kimi-2.6"}, {"kind": "dsh", "model": "glm53"}, {"kind": "openai-agents"}]
        )
        assert specs == [
            multi.AgentSpec(kind="pi", model="kimi-2.6"),
            multi.AgentSpec(kind="dsh", model="glm53"),
            multi.AgentSpec(kind="openai-agents", model=None),
        ]

    def test_agent_spec_instances_pass_through(self) -> None:
        """服务层调用方直接给 ``AgentSpec``：不再复制/改写。"""
        given = [multi.AgentSpec(kind="pi", model="kimi-2.6")]
        assert multi.normalize_agents(given) == given

    def test_schema_instances_are_accepted(self) -> None:
        """``AgentSpecIn``（Ninja 解析出来的对象形态）：走 getattr 分支。"""
        payload = MessageIn.model_validate({"message": "q", "agents": [{"kind": "pi", "model": "kimi-2.6"}]})
        assert multi.normalize_agents(payload.agents) == [multi.AgentSpec(kind="pi", model="kimi-2.6")]

    def test_mixed_shapes_in_one_request(self) -> None:
        """三种形态混着发也要能归一（前端中间版本必然出现过这种请求）。"""
        specs = multi.normalize_agents(
            ["pi", {"kind": "dsh", "model": "glm53"}, multi.AgentSpec(kind="openai-agents", model="gpt-5.6")]
        )
        assert specs == [
            multi.AgentSpec(kind="pi"),
            multi.AgentSpec(kind="dsh", model="glm53"),
            multi.AgentSpec(kind="openai-agents", model="gpt-5.6"),
        ]

    def test_dedup_by_kind_keeps_first_model(self) -> None:
        """同一 kind 只跑一次，且保留**第一个**（先出现那栏选的模型）。

        同一 kind 跑两遍既花双倍钱，又会让两栏共用同一个 ``run_id`` 前缀而串栏。
        """
        specs = multi.normalize_agents([{"kind": "pi", "model": "kimi-2.6"}, {"kind": "pi", "model": "glm53"}, "dsh"])
        assert specs == [multi.AgentSpec(kind="pi", model="kimi-2.6"), multi.AgentSpec(kind="dsh")]

    def test_blank_kind_and_blank_model_dropped(self) -> None:
        """空 kind 丢弃；空白模型视同未指定（``--model ""`` 会让 pi 报错）。"""
        specs = multi.normalize_agents(["", "  ", {"kind": "pi", "model": "   "}])
        assert specs == [multi.AgentSpec(kind="pi", model=None)]

    def test_none_and_empty_list(self) -> None:
        """空列表 / None 视同「没指定」：调用方据此回落到「主 + 次」。"""
        assert multi.normalize_agents(None) == []
        assert multi.normalize_agents([]) == []


# ── 2. 老前端兼容（请求体契约） ─────────────────────────────


class TestMessageInCompat:
    """``MessageIn.agents`` 必须同时吃老形态 ``list[str]`` 与新形态 ``list[obj]``。"""

    def test_legacy_string_list_is_accepted(self) -> None:
        """老前端发 ``["pi","dsh"]``：不能 422，解析出来还是字符串。"""
        payload = MessageIn.model_validate({"message": "合同有效吗", "agents": ["pi", "dsh"]})
        assert payload.agents == ["pi", "dsh"]
        assert multi.normalize_agents(payload.agents) == [multi.AgentSpec(kind="pi"), multi.AgentSpec(kind="dsh")]

    def test_structured_list_is_accepted(self) -> None:
        """新前端发对象数组：kind / model 都要落到 spec 上。"""
        payload = MessageIn.model_validate(
            {"message": "合同有效吗", "agents": [{"kind": "pi", "model": "kimi-2.6"}, {"kind": "dsh"}]}
        )
        assert multi.normalize_agents(payload.agents) == [
            multi.AgentSpec(kind="pi", model="kimi-2.6"),
            multi.AgentSpec(kind="dsh"),
        ]

    def test_mixed_list_is_accepted(self) -> None:
        """同一数组里新旧形态混用：迁移期真实会发生。"""
        payload = MessageIn.model_validate({"message": "q", "agents": ["pi", {"kind": "dsh", "model": "glm53"}]})
        assert multi.normalize_agents(payload.agents) == [
            multi.AgentSpec(kind="pi"),
            multi.AgentSpec(kind="dsh", model="glm53"),
        ]

    def test_absent_agents_stays_none(self) -> None:
        """不传 ``agents`` = 老路径（会话自己的后端单跑），不能被写成空列表。"""
        payload = MessageIn.model_validate({"message": "q"})
        assert payload.agents is None


# ── 3. 模型贯通到 RunContext ────────────────────────────────


async def _make_session(agent_kind: str = PRIMARY) -> AgentSession:
    return await AgentSession.objects.acreate(title="模型选择", agent_kind=agent_kind)


class TestStreamChatModel:
    """``stream_chat(model=...)`` → ``RunContext.model``。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_explicit_model_reaches_run_context(self) -> None:
        backend = _RecordingBackend(PRIMARY)
        register(backend)
        session = await _make_session()

        async for _ in stream_module.stream_chat(
            session=session, user_message="q", user_id=None, agent_kind=PRIMARY, model="kimi-2.6"
        ):
            pass

        assert [ctx.model for ctx in backend.contexts] == ["kimi-2.6"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_default_model_is_none_unchanged(self) -> None:
        """不传 model → ctx.model 仍是 ``None``（引入本字段前的行为逐字不变）。"""
        backend = _RecordingBackend(PRIMARY)
        register(backend)
        session = await _make_session()

        async for _ in stream_module.stream_chat(session=session, user_message="q", user_id=None, agent_kind=PRIMARY):
            pass

        assert [ctx.model for ctx in backend.contexts] == [None]


# ── 4. stream_multi 每栏各带自己的模型 ───────────────────────


async def _drain(events: Any) -> list[dict[str, Any]]:
    return [e async for e in events]


class TestStreamMultiPerColumnModel:
    """``stream_multi(specs=...)``：每栏的模型与 kind 必须对齐。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_each_column_gets_its_own_model(self) -> None:
        primary, secondary = _RecordingBackend(PRIMARY, "主"), _RecordingBackend(SECONDARY, "次")
        register(primary)
        register(secondary)
        session = await _make_session()

        await _drain(
            multi.stream_multi(
                session=session,
                user_message="q",
                user_id=None,
                specs=[multi.AgentSpec(PRIMARY, "kimi-2.6"), multi.AgentSpec(SECONDARY, "glm53")],
            )
        )

        assert [ctx.model for ctx in primary.contexts] == ["kimi-2.6"]
        assert [ctx.model for ctx in secondary.contexts] == ["glm53"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_single_column_spec_keeps_its_model(self) -> None:
        """单栏走 ``stream_chat`` 透传路径时模型也不能丢（最容易漏的一条分支）。"""
        backend = _RecordingBackend(PRIMARY)
        register(backend)
        session = await _make_session()

        events = await _drain(
            multi.stream_multi(
                session=session,
                user_message="q",
                user_id=None,
                specs=[multi.AgentSpec(PRIMARY, "kimi-2.6")],
            )
        )

        assert [ctx.model for ctx in backend.contexts] == ["kimi-2.6"]
        # 单栏透传：done 由 stream_chat 发，仍然只有一个
        assert [e["type"] for e in events].count("done") == 1

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_legacy_kinds_argument_still_works(self) -> None:
        """旧入口 ``kinds=[...]``：仍能跑，模型为 ``None``（平台默认）。"""
        primary, secondary = _RecordingBackend(PRIMARY), _RecordingBackend(SECONDARY)
        register(primary)
        register(secondary)
        session = await _make_session()

        await _drain(multi.stream_multi(session=session, user_message="q", user_id=None, kinds=[PRIMARY, SECONDARY]))

        assert [ctx.model for ctx in primary.contexts] == [None]
        assert [ctx.model for ctx in secondary.contexts] == [None]

    def test_resolve_specs_prefers_specs_over_kinds(self) -> None:
        """两处都给时 ``specs`` 优先（显式 > 隐式）。"""
        session = AgentSession(title="t", agent_kind=PRIMARY)
        resolved = multi.resolve_specs(
            session,
            [multi.AgentSpec(PRIMARY, "kimi-2.6")],
            [SECONDARY],
        )
        assert resolved == [multi.AgentSpec(PRIMARY, "kimi-2.6")]

    def test_resolve_specs_falls_back_to_primary_plus_secondary(self) -> None:
        """``specs`` / ``kinds`` 都不给 → 「主 + 次」，模型为 ``None``。"""
        primary, secondary = _RecordingBackend(PRIMARY), _RecordingBackend(SECONDARY)
        register(primary)
        register(secondary)
        session = AgentSession(title="t", agent_kind=PRIMARY)

        resolved = multi.resolve_specs(session, None, None)

        assert resolved[0] == multi.AgentSpec(PRIMARY)
        assert [s.kind for s in resolved] == [PRIMARY, SECONDARY]


# ── 5. pi 后端读 ctx.model ──────────────────────────────────


class TestPiBackendUsesContextModel:
    """``PiBackend`` 的 ``--model`` 来自 ``ctx.model``，为空才回落平台默认。"""

    @staticmethod
    def _install_pi_stubs(monkeypatch: pytest.MonkeyPatch, default_model: str) -> dict[str, Any]:
        """替掉池 / 模型解析 / 事件流；返回可断言的 ``acquire_kwargs`` 容器。"""
        from apps.agent.services.event_bus import EventBus

        class _StubSession:
            async def prompt(self, message: str) -> None:
                return None

        class _StubAcquire:
            async def __aenter__(self) -> _StubSession:
                return _StubSession()

            async def __aexit__(self, *exc: object) -> bool:
                return False

        captured: dict[str, Any] = {}

        class _StubPool:
            waiting = 0
            saturated = False

            def acquire(self, **kwargs: Any) -> _StubAcquire:
                captured.update(kwargs)
                return _StubAcquire()

        async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
            yield {"type": "delta", "content": "答"}
            yield {"type": "done"}

        async def fake_get_pool() -> Any:
            return _StubPool()

        async def fake_model() -> str | None:
            return default_model

        monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool.get_pool", fake_get_pool)
        monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool._resolve_model", fake_model)
        monkeypatch.setattr("apps.agent.backends.pi_backend.stream_events", fake_stream)
        monkeypatch.setattr("apps.agent.backends.pi_backend.register_live_route", lambda *a, **k: None)
        monkeypatch.setattr("apps.agent.backends.pi_backend.unregister_live_route", lambda *a, **k: None)
        monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)
        return captured

    @staticmethod
    def _ctx(model: str | None) -> RunContext:
        class _Session:
            session_id = "sess-model"

        return RunContext(
            run_id="sess-model:pi:1",
            session=_Session(),
            user_id=None,
            prompt="你好",
            user_token="tok",
            model=model,
            tool_selection=None,
        )

    @pytest.mark.django_db
    def test_explicit_ctx_model_wins_over_platform_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """用户选了模型就用它——不回落平台默认（否则「指定了也没生效」）。"""
        from apps.agent.backends.pi_backend import PiBackend

        captured = self._install_pi_stubs(monkeypatch, "platform-default")

        async def run() -> None:
            async for _ in PiBackend().stream(self._ctx("kimi-2.6")):
                pass

        asyncio.run(run())
        assert captured["model"] == "kimi-2.6"

    @pytest.mark.django_db
    def test_empty_ctx_model_falls_back_to_platform_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """不指定 → 回落 ``_resolve_model()``（老路径逐字不变）。"""
        from apps.agent.backends.pi_backend import PiBackend

        captured = self._install_pi_stubs(monkeypatch, "platform-default")

        async def run() -> None:
            async for _ in PiBackend().stream(self._ctx(None)):
                pass

        asyncio.run(run())
        assert captured["model"] == "platform-default"

    @pytest.mark.django_db
    def test_selected_model_is_reported_as_actual(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """收尾事实里的模型必须是实际传下去的那个（AgentRun / done 都读它）。"""
        from apps.agent.backends.pi_backend import PiBackend

        self._install_pi_stubs(monkeypatch, "platform-default")
        backend = PiBackend()

        async def run() -> None:
            async for _ in backend.stream(self._ctx("kimi-2.6")):
                pass

        asyncio.run(run())
        result = backend.result_for("sess-model:pi:1")
        assert result is not None
        assert result.model == "kimi-2.6"
