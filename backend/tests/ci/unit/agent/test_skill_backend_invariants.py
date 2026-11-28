"""技能送达的硬锁不变量：谁能注入索引块、谁被钉死在 ``TOOL_ONLY``、隔离运行绝不偷带技能。

守四件事（对应 ``CONTRACT.md`` §9 / §12 与 ``HANDOFF-P1.md`` §9.3）：

1. **未封洞的后端不许静默升档**：``codex`` / ``cline`` / ``dsh`` 的内置文件读取
   工具尚未封死（或没有人工审批），``skill_delivery`` 只能是 ``TOOL_ONLY``；
2. **声明 ``PROMPT`` 就必须真的注入**：``pi`` / ``claude-agent`` / ``qoder`` /
   ``antigravity`` / ``opencode`` 的 ``skill_delivery`` 是 ``PROMPT``；
3. **隔离运行不带技能**：``isolated=True`` 且无 ``skill_block_override`` 时，系统
   提示里绝不出现 ``ctx.skill_block``；给了 override 时只注 override（发布前试跑）；
4. **只读白名单与内置文件工具无交集**：``readonly_tool_selection`` 的每一项都不能
   是 ``read`` / ``bash`` / ``edit`` / ``write`` / ``powershell`` / ``grep`` /
   ``find`` / ``ls``——子 agent 的只读面是结构性安全，不是提示词劝阻。

## 为什么逐个后端参数化，而不是抽一层共享断言

五个后端的系统提示构造入口本来就不同（这也是各文件就地算、不抽共享层的原因——
共用一层反而更难读）：
``claude_agent._instructions`` / ``qoder._system_prompt`` /
``antigravity._system_prompt_text`` / ``opencode._config_payload`` 的
``agent.prompt`` / pi 的 ``pool.acquire(append_system_prompt=...)``。这里按各后端
**真实入口**取「模型会看到的文本」，而不是复制一份判断逻辑——否则测试与实现一起
漂移，门禁就变成了自我确认。

pi 的完整接线断言在 ``test_skill_delivery_wiring.py``；本文件只取「注了没有」这一个
事实，让五个后端的隔离矩阵在同一处对齐。

全部是纯函数 / 桩对象：**不需要建库**（没有 ``django_db``）。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from apps.agent.backends import BackendError, BackendErrorKind, RunContext, SkillDelivery
from apps.agent.backends.toolface import tool_prefix

#: 内置文件工具集（``CONTRACT.md`` §12 #2）。只读白名单与任何 ``--tools`` 都不许与
#: 它相交——相交等于把「从卷宗/网页里抓到的注入」变成可直接执行的动作。
BUILTIN_FILE_TOOLS: frozenset[str] = frozenset(
    {"read", "bash", "edit", "write", "powershell", "grep", "find", "ls"}
)

#: 声明 ``PROMPT`` 的五个后端（顺序与 ``CONTRACT.md`` §9 的能力表一致）。
PROMPT_BACKENDS: tuple[str, ...] = ("pi", "claude-agent", "qoder", "antigravity", "opencode")

#: 被硬锁在 ``TOOL_ONLY`` 的三个后端（未封内置文件工具 / 无人工审批）。
TOOL_ONLY_BACKENDS: tuple[str, ...] = ("codex", "cline", "dsh")

#: 常规运行该注进去的索引块。带块首（``## 可用技能（法穿）``）而不是只放技能名：
#: 只匹技能名会让「块被截断后仍有一行残留」这种半注入状态假绿。
SENTINEL_BLOCK = "## 可用技能（法穿）\n- [我的] invariant-probe：《不变量哨兵》——只该在常规运行出现"

#: 发布前试跑的 override 块（`isolated=True` 时也必须注进去，且不叠加 SENTINEL_BLOCK）。
OVERRIDE_BLOCK = "## 可用技能（法穿）\n- [我的] draft-probe：《待审技能试跑》"


class _Session:
    """最小会话桩：各后端只读 ``session_id``。"""

    session_id = "sess-skill-invariants"


def _ctx(**overrides: Any) -> RunContext:
    """造一个最小 ``RunContext``（技能块相关字段全部显式传）。"""
    fields: dict[str, Any] = {
        "run_id": "sess-skill-invariants:test:1",
        "session": _Session(),
        "user_id": None,
        "prompt": "你好",
        "user_token": "tok",
        "model": None,
        "tool_selection": None,
    }
    fields.update(overrides)
    return RunContext(**fields)


def _capabilities(kind: str) -> Any:
    """取后端的 ``BackendCapabilities``（SDK 未装的后端跳过，而不是假绿）。"""
    if kind == "pi":
        from apps.agent.backends.pi_backend import PiBackend

        return PiBackend.capabilities
    if kind == "claude-agent":
        from apps.agent.backends import claude_agent_backend

        return claude_agent_backend.backend_capabilities()
    if kind == "qoder":
        from apps.agent.backends import qoder_backend

        return qoder_backend.backend_capabilities()
    if kind == "antigravity":
        pytest.importorskip("google.antigravity", reason="google-antigravity SDK 未安装，跳过 antigravity 能力断言")
        from apps.agent.backends import antigravity_backend

        return antigravity_backend.backend_capabilities()
    if kind == "opencode":
        from apps.agent.backends import opencode_backend

        return opencode_backend.backend_capabilities()
    if kind == "codex":
        from apps.agent.backends import codex_backend

        return codex_backend.CodexBackend().capabilities
    if kind == "cline":
        from apps.agent.backends import cline_backend

        return cline_backend.ClineBackend().capabilities
    if kind == "dsh":
        pytest.importorskip("deepseek_harness", reason="deepseek-harness SDK 未安装，跳过 dsh 能力断言")
        from apps.agent.backends.dsh_backend import DshBackend

        return DshBackend.capabilities
    raise AssertionError(f"未知后端: {kind}")


class TestCapabilityLadder:
    """能力档位是事实陈述：声明 ``PROMPT`` = 承诺真的注入，``TOOL_ONLY`` = 硬锁。"""

    @pytest.mark.parametrize("kind", PROMPT_BACKENDS)
    def test_prompt_backends_declare_prompt(self, kind: str) -> None:
        assert _capabilities(kind).skill_delivery == SkillDelivery.PROMPT

    @pytest.mark.parametrize("kind", TOOL_ONLY_BACKENDS)
    def test_unsealed_backends_stay_tool_only(self, kind: str) -> None:
        """修洞前锁死：这三个后端一旦被悄悄改成 ``PROMPT``，这里当场红。

        升档的真实前提见 ``HANDOFF-P1.md`` §7.1：codex 要封死只读文件/shell 逃逸并
        把未知审批改成 fail-closed；cline 要禁内置工具 + 接审批；dsh 要等
        ``approval=True``（替换 ``_ApprovalPump._handle`` 的 stub）。
        """
        assert _capabilities(kind).skill_delivery == SkillDelivery.TOOL_ONLY


# ── 系统提示注入矩阵：五个 ``PROMPT`` 后端 × (常规 / 隔离 / 试跑 override) ──────


class _StubPiSession:
    """够 ``PiBackend`` 跑完一轮的最小 pi 会话桩（不拉子进程）。"""

    turns_started = 0

    async def prompt(self, message: str) -> None:
        return None

    async def get_session_stats(self) -> dict[str, Any]:
        return {}

    async def abort(self) -> bool:
        return True


class _RecordingPool:
    """记下 ``acquire`` 收到的实参：``append_system_prompt`` 就是 pi 的注入结果。"""

    waiting = 0
    saturated = False

    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def acquire(self, **kwargs: Any) -> Any:
        # 原地更新而不是重新绑定：用例读的是同一个 dict 的快照。
        self.kwargs.clear()
        self.kwargs.update(kwargs)
        session = _StubPiSession()

        class _Acquire:
            async def __aenter__(self) -> _StubPiSession:
                return session

            async def __aexit__(self, *exc: object) -> bool:
                return False

        return _Acquire()


class _FakeLiveRegistry:
    """运行中登记表的空实现（本轮不关心插话，但 ``PiBackend`` 会调它）。"""

    async def register(self, session_id: str, session: Any) -> None:
        return None

    async def unregister(self, session_id: str, session: Any) -> None:
        return None


def _pi_system_prompt(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> str | None:
    """跑一轮 pi（池 / 模型 / 事件流 / 登记表全桩），返回本轮注入的系统提示块。"""
    from apps.agent.backends.pi_backend import PiBackend

    pool = _RecordingPool()

    async def fake_get_pool() -> Any:
        return pool

    async def fake_model() -> str | None:
        return "kimi-2.6"

    async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
        yield {"type": "delta", "content": "答"}
        yield {"type": "done"}

    monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool.get_pool", fake_get_pool)
    monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool._resolve_model", fake_model)
    monkeypatch.setattr("apps.agent.backends.pi_backend.stream_events", fake_stream)
    monkeypatch.setattr("apps.agent.backends.pi_backend.get_live_registry", lambda: _FakeLiveRegistry())
    monkeypatch.setattr("apps.agent.backends.pi_backend.register_live_route", lambda *a, **k: None)
    monkeypatch.setattr("apps.agent.backends.pi_backend.unregister_live_route", lambda *a, **k: None)

    async def drain() -> None:
        async for _event in PiBackend().stream(ctx):
            pass

    asyncio.run(drain())
    block = pool.kwargs.get("append_system_prompt")
    return block if isinstance(block, str) else None


def _system_prompt(kind: str, ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> str:
    """调该后端**真实的**系统提示构造入口，返回模型会看到的提示文本。"""
    if kind == "pi":
        return _pi_system_prompt(ctx, monkeypatch) or ""
    if kind == "claude-agent":
        from apps.agent.backends import claude_agent_backend

        return claude_agent_backend._instructions(ctx)
    if kind == "qoder":
        from apps.agent.backends import qoder_backend

        prompt = qoder_backend._system_prompt(ctx)
        return prompt if isinstance(prompt, str) else str(prompt.get("append") or "")
    if kind == "antigravity":
        pytest.importorskip("google.antigravity", reason="google-antigravity SDK 未安装，跳过 antigravity 注入断言")
        from apps.agent.backends import antigravity_backend

        return antigravity_backend._system_prompt_text(ctx)
    if kind == "opencode":
        from apps.agent.backends import opencode_backend

        payload = opencode_backend.OpenCodeBackend()._config_payload(
            {"base_url": "http://gw/v1", "api_key": "k", "model": "m", "models": []}, ctx
        )
        return str(payload["agent"][opencode_backend.FACHUAN_AGENT].get("prompt") or "")
    raise AssertionError(f"未知后端: {kind}")


@pytest.mark.parametrize("kind", PROMPT_BACKENDS)
def test_regular_run_injects_skill_block(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """常规运行：``ctx.skill_block`` 必须出现在系统提示里（声明 ``PROMPT`` 的代价）。"""
    prompt = _system_prompt(kind, _ctx(skill_block=SENTINEL_BLOCK), monkeypatch)
    assert SENTINEL_BLOCK in prompt, f"{kind} 声明了 PROMPT 却没有把技能索引块注进系统提示"


@pytest.mark.parametrize("kind", PROMPT_BACKENDS)
def test_isolated_run_without_override_injects_nothing(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``isolated=True`` 且无 override：一个字都不许注（``base.py`` 的不变量门禁）。"""
    prompt = _system_prompt(kind, _ctx(isolated=True, skill_block=SENTINEL_BLOCK), monkeypatch)
    assert SENTINEL_BLOCK not in prompt, f"{kind} 在隔离运行里偷带了律师的个人/所内技能"


@pytest.mark.parametrize("kind", PROMPT_BACKENDS)
def test_override_survives_isolation_and_replaces_block(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """发布前试跑：override 必须绕过隔离的强制空块，且**不叠加**常规索引。"""
    prompt = _system_prompt(
        kind,
        _ctx(isolated=True, skill_block=SENTINEL_BLOCK, skill_block_override=OVERRIDE_BLOCK),
        monkeypatch,
    )
    assert OVERRIDE_BLOCK in prompt, f"{kind} 没能把发布前试跑的待审技能注进去"
    assert SENTINEL_BLOCK not in prompt, f"{kind} 在试跑时叠加了常规索引块（应只装待审这一条）"


def _run_option_rejector(kind: str) -> Any:
    """取该后端的「不支持的运行选项」拒收函数（失败必须是显式错，不是静默忽略）。"""
    if kind == "opencode":
        from apps.agent.backends.opencode_backend import _reject_unsupported_run_options

        return _reject_unsupported_run_options
    if kind == "codex":
        from apps.agent.backends.codex_backend import _reject_unsupported_run_options

        return _reject_unsupported_run_options
    if kind == "cline":
        from apps.agent.backends.cline_backend import _reject_unsupported_run_options

        return _reject_unsupported_run_options
    raise AssertionError(f"未知后端: {kind}")


@pytest.mark.parametrize("kind", ("opencode", "codex", "cline"))
@pytest.mark.parametrize("option", ("system_prompt", "max_turns"))
def test_unsupported_run_options_fail_closed(kind: str, option: str) -> None:
    """做不到的运行选项必须报 ``BackendError``，不许静默忽略（``base.py:420-431``）。

    静默忽略的后果不是报错，而是「综合结论的规则没生效」——模型照旧回答，谁也不知道
    那套规则从未到过它面前。
    """
    value: Any = "只输出结论" if option == "system_prompt" else 3
    with pytest.raises(BackendError) as excinfo:
        _run_option_rejector(kind)(_ctx(**{option: value}))
    assert excinfo.value.kind == BackendErrorKind.UNAVAILABLE
    assert option in excinfo.value.message


class TestReadonlyToolSelection:
    """子 agent 的工具面必须结构性只读（``CONTRACT.md`` §12 #2）。"""

    def test_selection_never_contains_builtin_file_tools(self) -> None:
        from apps.agent.services.subtask import readonly_tool_selection

        selection = readonly_tool_selection()
        entries = [entry for entry in selection.split(",") if entry]
        assert entries, "只读白名单不能为空——空串等于「子 agent 一个工具都没有」"

        prefix = tool_prefix()
        for entry in entries:
            # 裸文件工具名（read / bash / ...）一旦出现，收窄就是假的：pi 的
            # ``--tools`` 会把它当成一个真实可调的内置工具暴露给子 agent。
            assert entry not in BUILTIN_FILE_TOOLS
            assert entry.startswith(prefix), f"只读白名单项必须走共享 MCP 命名空间: {entry}"
            short = entry.removeprefix(prefix).removesuffix("*")
            assert short not in BUILTIN_FILE_TOOLS, f"只读白名单里出现内置文件工具: {entry}"
            for banned in BUILTIN_FILE_TOOLS:
                assert f"+{banned}" not in entry and f"-{banned}" not in entry

