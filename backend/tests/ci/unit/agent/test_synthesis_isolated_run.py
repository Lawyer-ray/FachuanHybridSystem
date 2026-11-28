"""综合结论走「隔离运行」：规则真的下发、会话历史不被污染、取消原样上抛。

守的是评审里的两处真实缺陷：

1. **规则没下发**：``synthesis_system_prompt()`` / ``SYNTHESIS_MAX_TURNS`` 原先全库无人调用，
   ``RunContext`` 也没有承载字段——来源锚点、只用候选依据、分歧写明这三条规则从没到过 agent。
2. **污染 pi 栏历史**：pi 按会话 id 拼 ``--session-dir/--session-id``，综合传的是会话本身，
   于是综合读到 pi 栏全部历史、又把五栏全文与综合稿写回去；用户同时提问时两个 pi 进程
   写同一个 session 文件。

全部用桩，不起 pi 子进程、不连网关。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from apps.agent.backends import BackendError, BackendErrorKind, RunContext
from apps.agent.backends import registry as registry_module
from apps.agent.services.chat.aggregate import AGGREGATE_SYSTEM_PROMPT
from apps.agent.services.synthesis import agent_runner


class _Session:
    session_id = "sess-real"


def _ctx(**overrides: Any) -> RunContext:
    fields: dict[str, Any] = {
        "run_id": "sess-real:synthesis:1",
        "session": _Session(),
        "user_id": 7,
        "prompt": "综合一下",
        "user_token": "tok",
        "model": "kimi-2.6",
        "tool_selection": None,
    }
    fields.update(overrides)
    return RunContext(**fields)


@pytest.fixture(autouse=True)
def _isolated_registry() -> Any:
    registry_module.clear()
    yield
    registry_module.clear()


# ── 1. run_synthesis_agent 下发的 RunContext ───────────────────────────────


class _RecordingBackend:
    """记下收到的 ctx；按 ``frames`` 产出事件。"""

    kind = "fake-synth"

    def __init__(self, frames: list[dict[str, Any]] | None = None) -> None:
        self.contexts: list[RunContext] = []
        self.frames = frames if frames is not None else [{"type": "delta", "content": "结论[来源：pi]"}]
        self.closed = 0

    def stream(self, ctx: RunContext) -> Any:
        self.contexts.append(ctx)
        return self._gen()

    async def _gen(self) -> Any:
        try:
            for frame in self.frames:
                yield frame
        finally:
            self.closed += 1


@pytest.fixture()
def runner_env(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_mint(user_id: int | None) -> str:
        return "tok"

    monkeypatch.setattr("apps.agent.backends.builtin.ensure_registered", lambda: None)
    monkeypatch.setattr("apps.agent.services.chat.env.mint_user_token", fake_mint)


def _run(backend: Any, **overrides: Any) -> Any:
    registry_module.register(backend)
    kwargs: dict[str, Any] = {
        "session": _Session(),
        "user_id": 7,
        "kind": backend.kind,
        "model": "kimi-2.6",
        "prompt": "问题 + 候选",
        "run_id": "sess-real:synthesis:job-1",
    }
    kwargs.update(overrides)
    return agent_runner.run_synthesis_agent(**kwargs)


@pytest.mark.usefixtures("runner_env")
class TestRunnerPassesRules:
    def test_ctx_carries_system_prompt_max_turns_and_isolation(self) -> None:
        backend = _RecordingBackend()
        result = asyncio.run(_run(backend))
        assert result.text == "结论[来源：pi]"
        (ctx,) = backend.contexts
        assert ctx.system_prompt == AGGREGATE_SYSTEM_PROMPT
        assert ctx.max_turns == agent_runner.SYNTHESIS_MAX_TURNS == 8
        assert ctx.isolated is True
        # 审批 / 归因仍用真实会话
        assert str(ctx.session.session_id) == "sess-real"
        assert ctx.run_id == "sess-real:synthesis:job-1"

    def test_retry_attempt_keeps_the_same_rules(self) -> None:
        """第二次尝试（缺锚点重试）同样带规则——不能只有首轮带。"""
        backend = _RecordingBackend(frames=[{"type": "delta", "content": "没有锚点"}])
        with pytest.raises(Exception, match="未通过校验"):
            asyncio.run(_run(backend))
        assert len(backend.contexts) == agent_runner.SYNTHESIS_AGENT_ATTEMPTS
        for ctx in backend.contexts:
            assert (ctx.system_prompt, ctx.max_turns, ctx.isolated) == (AGGREGATE_SYSTEM_PROMPT, 8, True)

    def test_backend_error_becomes_llm_error(self) -> None:
        from apps.core.llm.exceptions import LLMError

        class _Unsupported(_RecordingBackend):
            async def _gen(self) -> Any:
                raise BackendError(BackendErrorKind.UNAVAILABLE, "不支持隔离")
                yield {}  # pragma: no cover - 让它成为异步生成器

        with pytest.raises(LLMError, match="不支持隔离"):
            asyncio.run(_run(_Unsupported()))

    def test_error_frame_closes_backend_generator(self) -> None:
        """报错帧提前退出时后端生成器当场关闭（它的 finally 负责关进程、删隔离目录）。"""
        from apps.core.llm.exceptions import LLMError

        backend = _RecordingBackend(frames=[{"type": "error", "message": "炸了"}, {"type": "delta", "content": "x"}])
        with pytest.raises(LLMError):
            asyncio.run(_run(backend))
        assert backend.closed == 1

    def test_cancellation_propagates_and_closes_generator(self) -> None:
        """取消不是失败：原样上抛 CancelledError，不得被转成 LLMError。"""

        class _Hanging(_RecordingBackend):
            async def _gen(self) -> Any:
                try:
                    yield {"type": "delta", "content": "半截"}
                    await asyncio.sleep(3600)
                    yield {}  # pragma: no cover
                finally:
                    self.closed += 1

        backend = _Hanging()

        async def main() -> None:
            task = asyncio.create_task(_run(backend))
            await asyncio.sleep(0.05)
            task.cancel()
            await task

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(main())
        assert backend.closed == 1


# ── 2. PiProcessPool：隔离运行用一次性目录 ──────────────────────────────────


class _StubPiSession:
    instances: list[_StubPiSession] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        _StubPiSession.instances.append(self)

    async def start(self) -> None:
        return None

    async def close(self, *, abort_running: bool = False) -> None:
        return None


@pytest.fixture()
def stub_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from apps.agent.pi import pool as pool_module

    _StubPiSession.instances = []

    def _write_pi_config(
        target_dir: Any, endpoint: Any = None, model_hint: str = "", *, api_key: str | None = None
    ) -> None:
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        (Path(target_dir) / "AGENTS.md").write_text("法穿默认人格", encoding="utf-8")

    stable = (tmp_path / "work", tmp_path / "config", tmp_path / "sessions")
    for path in stable:
        path.mkdir()
    monkeypatch.setattr(pool_module, "write_pi_config", _write_pi_config)
    monkeypatch.setattr(pool_module, "PiRpcSession", _StubPiSession)
    monkeypatch.setattr(pool_module, "_try_redis_slot", lambda size: None)
    monkeypatch.setattr(pool_module, "_yuandian_env", lambda: {})
    monkeypatch.setattr(pool_module, "layout", lambda: stable)
    return pool_module, tmp_path


def _isolated_roots(tmp_path: Path) -> list[Path]:
    base = tmp_path / "isolated"
    return sorted(base.iterdir()) if base.is_dir() else []


class TestPoolIsolation:
    def test_isolated_run_never_touches_real_session_dir(self, stub_pool: Any) -> None:
        pool_module, tmp_path = stub_pool
        pi_pool = pool_module.PiProcessPool(pool_module.PoolConfig(size=1))
        seen: dict[str, Any] = {}

        async def run() -> None:
            async with pi_pool.acquire(
                session_env={"FACHUAN_SESSION_ID": "sess-real"},
                session_id="sess-real",
                isolated=True,
                system_prompt="综合规则",
            ):
                (root,) = _isolated_roots(tmp_path)
                seen["root"] = root
                seen["agents_md"] = (root / "config" / "AGENTS.md").read_text(encoding="utf-8")

        asyncio.run(run())
        kwargs = _StubPiSession.instances[0].kwargs
        root = seen["root"]
        # 不用真实会话的 id 与目录
        assert kwargs["session_id"] != "sess-real"
        assert not kwargs["session_dir"].startswith(str(tmp_path / "sessions"))
        assert kwargs["session_dir"].startswith(str(root))
        assert kwargs["cwd"] == str(root / "work")
        assert kwargs["extra_env"]["PI_CODING_AGENT_DIR"] == str(root / "config")
        # 审批仍路由到真实会话
        assert kwargs["extra_env"]["FACHUAN_SESSION_ID"] == "sess-real"
        # 隔离运行不注入律师个人记忆
        assert kwargs["memory_injection"] is False
        # system prompt 替换的是隔离目录里的 AGENTS.md，全局那份没动
        assert seen["agents_md"] == "综合规则"
        assert not (tmp_path / "config" / "AGENTS.md").exists()
        # 跑完即删
        assert not root.exists()
        assert not (tmp_path / "sessions" / "sess-real").exists()

    def test_isolated_root_removed_on_error(self, stub_pool: Any) -> None:
        pool_module, tmp_path = stub_pool
        pi_pool = pool_module.PiProcessPool(pool_module.PoolConfig(size=1))

        async def run() -> None:
            async with pi_pool.acquire(session_id="sess-real", isolated=True):
                raise RuntimeError("本轮炸了")

        with pytest.raises(RuntimeError, match="本轮炸了"):
            asyncio.run(run())
        assert _isolated_roots(tmp_path) == []

    def test_isolated_root_removed_on_cancel(self, stub_pool: Any) -> None:
        pool_module, tmp_path = stub_pool
        pi_pool = pool_module.PiProcessPool(pool_module.PoolConfig(size=1))

        async def body(ready: asyncio.Event) -> None:
            async with pi_pool.acquire(session_id="sess-real", isolated=True):
                ready.set()
                await asyncio.sleep(3600)

        async def main() -> None:
            ready = asyncio.Event()
            task = asyncio.create_task(body(ready))
            await ready.wait()
            assert len(_isolated_roots(tmp_path)) == 1
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(main())
        assert _isolated_roots(tmp_path) == []

    def test_stale_isolated_roots_are_swept(self, stub_pool: Any) -> None:
        """崩溃残留（含 key）不能长期留盘：建新隔离目录时清掉超时的旧目录。"""
        import os
        import time

        pool_module, tmp_path = stub_pool
        stale = tmp_path / "isolated" / "run-crashed"
        (stale / "config").mkdir(parents=True)
        (stale / "config" / "models.json").write_text("{}", encoding="utf-8")
        old = time.time() - pool_module.ISOLATED_STALE_SECONDS - 60
        os.utime(stale, (old, old))
        pi_pool = pool_module.PiProcessPool(pool_module.PoolConfig(size=1))

        async def run() -> None:
            async with pi_pool.acquire(session_id="sess-real", isolated=True):
                return None

        asyncio.run(run())
        assert not stale.exists()

    def test_non_isolated_path_unchanged(self, stub_pool: Any) -> None:
        pool_module, tmp_path = stub_pool
        pi_pool = pool_module.PiProcessPool(pool_module.PoolConfig(size=1))

        async def run() -> None:
            async with pi_pool.acquire(session_id="sess-real"):
                return None

        asyncio.run(run())
        kwargs = _StubPiSession.instances[0].kwargs
        assert kwargs["session_id"] == "sess-real"
        assert kwargs["session_dir"] == str(tmp_path / "sessions" / "sess-real")
        assert kwargs["cwd"] == str(tmp_path / "work")
        assert not (tmp_path / "isolated").exists()

    def test_system_prompt_requires_isolation(self, stub_pool: Any) -> None:
        """非隔离时不能为一轮改全局 AGENTS.md：直接报错，不静默忽略。"""
        from apps.agent.pi.rpc_client import PiError

        pool_module, tmp_path = stub_pool
        pi_pool = pool_module.PiProcessPool(pool_module.PoolConfig(size=1))

        async def run() -> None:
            async with pi_pool.acquire(session_id="sess-real", system_prompt="规则"):
                return None

        with pytest.raises(PiError):
            asyncio.run(run())
        assert (tmp_path / "config" / "AGENTS.md").exists() is False


# ── 3. PiBackend：隔离参数、插话登记、轮数上限 ─────────────────────────────


class _BackendStubSession:
    def __init__(self, turns: int = 0) -> None:
        self.turns_started = turns
        self.aborted = 0

    async def prompt(self, message: str) -> None:
        return None

    async def get_session_stats(self) -> dict[str, Any]:
        return {}

    async def abort(self) -> bool:
        self.aborted += 1
        return True


class _BackendStubPool:
    waiting = 0
    saturated = False

    def __init__(self, session: _BackendStubSession) -> None:
        self.session = session
        self.kwargs: dict[str, Any] = {}

    def acquire(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        session = self.session

        class _A:
            async def __aenter__(self) -> _BackendStubSession:
                return session

            async def __aexit__(self, *exc: object) -> bool:
                return False

        return _A()


class _FakeLiveRegistry:
    def __init__(self) -> None:
        self.registered: list[str] = []

    async def register(self, session_id: str, session: Any) -> None:
        self.registered.append(session_id)

    async def unregister(self, session_id: str, session: Any) -> None:
        return None


@pytest.fixture()
def pi_backend_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    from apps.agent.services.event_bus import EventBus

    state: dict[str, Any] = {"session": _BackendStubSession(), "routes": []}
    live = _FakeLiveRegistry()

    async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
        yield {"type": "delta", "content": "答"}
        yield {"type": "settled"}

    async def fake_get_pool() -> Any:
        state["pool"] = _BackendStubPool(state["session"])
        return state["pool"]

    async def fake_model() -> str | None:
        return "kimi-2.6"

    monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool.get_pool", fake_get_pool)
    monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool._resolve_model", fake_model)
    monkeypatch.setattr("apps.agent.backends.pi_backend.stream_events", fake_stream)
    monkeypatch.setattr("apps.agent.backends.pi_backend.get_live_registry", lambda: live)
    monkeypatch.setattr("apps.agent.backends.pi_backend.register_live_route", lambda *a, **k: state["routes"].append(a))
    monkeypatch.setattr("apps.agent.backends.pi_backend.unregister_live_route", lambda *a, **k: None)
    monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)
    state["live"] = live
    return state


def _drain(ctx: RunContext) -> list[dict[str, Any]]:
    from apps.agent.backends.pi_backend import PiBackend

    async def run() -> list[dict[str, Any]]:
        return [e async for e in PiBackend().stream(ctx) if e is not None]

    return asyncio.run(run())


class TestPiBackendIsolation:
    def test_isolated_ctx_reaches_pool_and_skips_live_registry(self, pi_backend_env: Any) -> None:
        _drain(_ctx(isolated=True, system_prompt="综合规则"))
        kwargs = pi_backend_env["pool"].kwargs
        assert kwargs["isolated"] is True
        assert kwargs["system_prompt"] == "综合规则"
        # 会话 id 仍传真实值：池在隔离模式下自行换成临时 id；审批 env 用真实会话
        assert kwargs["session_env"]["FACHUAN_SESSION_ID"] == "sess-real"
        # 用户对本会话的插话不能被路由到综合进程
        assert pi_backend_env["live"].registered == []
        assert pi_backend_env["routes"] == []
        # 律师技能不注入隔离运行：零技能目录 + 无系统提示追加块（方案 A 下技能
        # 走 ``--append-system-prompt`` 索引块，不再是 ``--skill`` 目录）。
        assert kwargs["skill_paths"] == []
        assert kwargs["append_system_prompt"] is None

    def test_regular_ctx_acquire_kwargs_unchanged(self, pi_backend_env: Any) -> None:
        _drain(_ctx())
        kwargs = pi_backend_env["pool"].kwargs
        assert "isolated" not in kwargs and "system_prompt" not in kwargs
        assert pi_backend_env["live"].registered == ["sess-real"]

    def test_system_prompt_without_isolation_is_rejected(self, pi_backend_env: Any) -> None:
        with pytest.raises(BackendError):
            _drain(_ctx(system_prompt="规则"))

    def test_max_turns_exceeded_aborts_and_raises(self, pi_backend_env: Any) -> None:
        pi_backend_env["session"] = _BackendStubSession(turns=3)
        with pytest.raises(BackendError, match="2 轮"):
            _drain(_ctx(isolated=True, max_turns=2))
        assert pi_backend_env["session"].aborted == 1

    def test_max_turns_within_limit_runs_normally(self, pi_backend_env: Any) -> None:
        pi_backend_env["session"] = _BackendStubSession(turns=2)
        events = _drain(_ctx(isolated=True, max_turns=2))
        assert [e["type"] for e in events] == ["delta"]
        assert pi_backend_env["session"].aborted == 0


# ── 4. rpc_client：turn_start 计数 ─────────────────────────────────────────


def test_rpc_session_counts_turn_start_events() -> None:
    from apps.agent.pi.rpc_client import PiRpcSession

    session = PiRpcSession(cwd=".", extension_path="/nonexistent.ts")
    records = (b'{"type":"agent_start"}', b'{"type":"turn_start"}', b'{"type":"turn_end"}', b'{"type":"turn_start"}')
    for record in records:
        session._dispatch_line(record)
    assert session.turns_started == 2


class TestMemoryInjectionSwitch:
    """隔离运行（综合结论）不加载记忆注入 extension；常规会话照旧加载。"""

    def test_regular_acquire_keeps_memory_injection(self, stub_pool: Any) -> None:
        pool_module, _tmp_path = stub_pool
        pi_pool = pool_module.PiProcessPool(pool_module.PoolConfig(size=1))

        async def run() -> None:
            async with pi_pool.acquire(session_id="sess-real"):
                pass

        asyncio.run(run())
        assert _StubPiSession.instances[0].kwargs["memory_injection"] is True

    def test_resolve_extensions_drops_only_memory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.pi import rpc_client

        files = {}
        for name in ("approval", "memory", "guard", "compaction"):
            path = tmp_path / f"{name}.ts"
            path.write_text("//", encoding="utf-8")
            files[name] = str(path)
        monkeypatch.setattr(rpc_client, "default_memory_extension", lambda: files["memory"])
        monkeypatch.setattr(rpc_client, "default_tool_result_guard_extension", lambda: files["guard"])
        monkeypatch.setattr(rpc_client, "default_compaction_extension", lambda: files["compaction"])

        with_memory = rpc_client.resolve_extensions(files["approval"])
        without_memory = rpc_client.resolve_extensions(files["approval"], memory_injection=False)

        assert with_memory == [files["approval"], files["memory"], files["guard"], files["compaction"]]
        # 审批永远在第一位；只少了记忆注入
        assert without_memory == [files["approval"], files["guard"], files["compaction"]]

    def test_build_args_omits_memory_extension(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.pi import rpc_client

        memory = tmp_path / "memory.ts"
        memory.write_text("//", encoding="utf-8")
        approval = tmp_path / "approval.ts"
        approval.write_text("//", encoding="utf-8")
        monkeypatch.setattr(rpc_client, "default_memory_extension", lambda: str(memory))
        monkeypatch.setattr(rpc_client, "default_tool_result_guard_extension", lambda: "")
        monkeypatch.setattr(rpc_client, "default_compaction_extension", lambda: "")

        regular = rpc_client.PiRpcSession(cwd=str(tmp_path), extension_path=str(approval))._build_args("pi")
        isolated = rpc_client.PiRpcSession(
            cwd=str(tmp_path), extension_path=str(approval), memory_injection=False
        )._build_args("pi")

        assert str(memory) in regular
        assert str(memory) not in isolated
        assert str(approval) in isolated
