"""``PiBackend`` —— 把「跑一轮 pi」收成 ``AgentBackend`` 实现。

本文件只验三件事（都不起真进程）：

1. **身份与能力声明**：``kind == "pi"``，五项能力全开。能力是前端决定 UI 形态的
   依据（声明了 ``streaming`` 却不发 ``delta``，前端只会长时间空白后突然出整段），
   所以这里断言的是事实而不是空值。
2. **结构化满足协议**：``isinstance(PiBackend(), AgentBackend)``。``runtime_checkable``
   是「不用继承也能实现」的前提，破了它整层解耦就退化成显式基类。
3. **注册可用 + 事件带 agent/run_id**：注册后 ``registry.get("pi")`` 拿得到；
   事件体必须带 ``agent`` 与 ``run_id``（两个 agent 同题并行时，前端靠这两个字段
   把交错的事件分流到不同栏）。用桩池 + 桩事件流，不碰 pi 子进程。

另加一条「收尾事实」断言：``PiRunResult`` 必须在 ``done`` 事件**之前**就位，
否则编排层收到 done 就停，``backend.result`` 永远是 None（模型与水位全丢）。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from apps.agent.backends import AgentBackend, BackendCapabilities, RunContext, get, register
from apps.agent.backends import registry as registry_module
from apps.agent.backends.pi_backend import PiBackend, PiRunResult


class _StubSession:
    """最小 pi 会话桩：prompt 记账，stats 返回空（水位降级为 None）。"""

    def __init__(self) -> None:
        self.prompted: list[str] = []

    async def prompt(self, message: str) -> None:
        self.prompted.append(message)

    async def get_session_stats(self) -> dict[str, Any]:
        return {}


class _StubAcquire:
    def __init__(self, session: _StubSession) -> None:
        self._session = session

    async def __aenter__(self) -> _StubSession:
        return self._session

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _StubPool:
    """记录 acquire 参数，便于断言 env / model / tool_selection 的接线。"""

    waiting = 0
    saturated = False

    def __init__(self, session: _StubSession) -> None:
        self._session = session
        self.acquire_kwargs: dict[str, Any] = {}

    def acquire(self, **kwargs: Any) -> _StubAcquire:
        self.acquire_kwargs = kwargs
        return _StubAcquire(self._session)


def _ctx(run_id: str = "sess-1:pi:1") -> RunContext:
    class _Session:
        session_id = "sess-1"

    return RunContext(
        run_id=run_id,
        session=_Session(),
        user_id=None,
        prompt="你好",
        user_token="tok",
        model=None,
        tool_selection="readonly",
    )


@pytest.fixture(autouse=True)
def _isolated_registry() -> Any:
    """注册表是模块级全局状态；串用例会出假绿。"""
    registry_module.clear()
    yield
    registry_module.clear()


@pytest.fixture()
def stub_runtime(monkeypatch: pytest.MonkeyPatch) -> _StubPool:
    """替掉池 / 模型解析 / pi 事件流，``PiBackend.stream`` 只剩编排可测。"""
    from apps.agent.services.event_bus import EventBus

    session = _StubSession()
    pool = _StubPool(session)

    async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
        yield {"type": "delta", "content": "答"}
        yield {"type": "done"}

    async def fake_get_pool() -> Any:
        return pool

    async def fake_model() -> str | None:
        return "kimi-2.6"

    monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool.get_pool", fake_get_pool)
    monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool._resolve_model", fake_model)
    monkeypatch.setattr("apps.agent.backends.pi_backend.stream_events", fake_stream)
    # live session 路由表走 Redis，测试环境无 Redis 也要能跑（失败只降级，但别刷日志）。
    monkeypatch.setattr("apps.agent.backends.pi_backend.register_live_route", lambda *a, **k: None)
    monkeypatch.setattr("apps.agent.backends.pi_backend.unregister_live_route", lambda *a, **k: None)
    monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)
    return pool


class TestIdentity:
    def test_kind_is_pi(self) -> None:
        assert PiBackend.kind == "pi"

    def test_capabilities_are_all_true(self) -> None:
        """pi 确实支持流式 / 工具 / 审批 / compaction / 插话：五项如实为 True。"""
        caps = PiBackend.capabilities
        assert isinstance(caps, BackendCapabilities)
        assert (caps.streaming, caps.tool_calls, caps.approval, caps.compaction, caps.steer) == (
            True,
            True,
            True,
            True,
            True,
        )

    def test_satisfies_agent_backend_protocol(self) -> None:
        """``runtime_checkable`` 协议：不继承也要能过 isinstance。"""
        assert isinstance(PiBackend(), AgentBackend)


class TestRegistration:
    def test_registered_instance_is_returned_by_kind(self) -> None:
        register(PiBackend())
        assert isinstance(get("pi"), PiBackend)

    def test_app_ready_registers_pi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Django app 启动时必须把 pi 挂进注册表。

        漏注册的后果是「冷启动后的第一轮对话」报未知 backend——只在进程启动后的
        第一轮暴露，最难复现。这里跑真正的 ``AgentConfig.ready()``（其周期任务注册
        在测试环境会降级/跳过），断言注册表里确实有了 ``pi``。"""
        from apps.agent.apps import AgentConfig

        # ready() 里的调度表注册需要数据库与调度器；本用例只关心后端注册，
        # 把那一半换掉，避免无关的环境依赖。
        monkeypatch.setattr(AgentConfig, "_register_memory_schedules", staticmethod(lambda: None))
        AgentConfig.ready(AgentConfig.__new__(AgentConfig))
        assert isinstance(get("pi"), PiBackend)


class TestStreamEvents:
    @pytest.mark.django_db
    def test_events_carry_agent_and_run_id(self, stub_runtime: _StubPool) -> None:
        backend = PiBackend()
        ctx = _ctx("sess-1:pi:1")

        async def run() -> list[dict[str, Any]]:
            return [e async for e in backend.stream(ctx) if e is not None]

        events = asyncio.run(run())
        assert events, "没有产出任何事件"
        for event in events:
            assert event["agent"] == "pi", event
            assert event["run_id"] == "sess-1:pi:1", event

    @pytest.mark.django_db
    def test_result_is_ready_when_done_arrives(self, stub_runtime: _StubPool) -> None:
        """done 事件产出时 ``result_for(run_id)`` 必须已就位。

        编排层收到 done 就停止消费，若收尾事实在 done 之后才写，模型与水位会全丢
        （AgentRun 记空模型、done 事件没有水位）。
        """
        backend = PiBackend()
        ctx = _ctx()
        seen_done_result: list[PiRunResult | None] = []

        async def run() -> None:
            async for event in backend.stream(ctx):
                if event is not None and event.get("type") == "done":
                    seen_done_result.append(backend.result_for(ctx.run_id))

        asyncio.run(run())
        assert seen_done_result, "没有收到 done"
        result = seen_done_result[0]
        assert isinstance(result, PiRunResult)
        assert result.model == "kimi-2.6"
        # 桩 stats 返回空 dict → 水位应为 None（不编造 0）
        assert result.context_used is None
        assert result.context_total is None

    @pytest.mark.django_db
    def test_acquire_receives_env_model_and_tool_selection(self, stub_runtime: _StubPool) -> None:
        """env 必须带 FACHUAN_RUN_ID（审批回调的二级寻址键），模型与工具面按 ctx 透传。"""
        backend = PiBackend()
        ctx = _ctx("sess-1:pi:3")

        async def run() -> None:
            async for _ in backend.stream(ctx):
                pass

        asyncio.run(run())
        kwargs = stub_runtime.acquire_kwargs
        assert kwargs["session_env"]["FACHUAN_RUN_ID"] == "sess-1:pi:3"
        assert kwargs["session_env"]["FACHUAN_SESSION_ID"] == "sess-1"
        assert kwargs["model"] == "kimi-2.6"
        assert kwargs["tool_selection"] == "readonly"
        assert kwargs["session_id"] == "sess-1"
