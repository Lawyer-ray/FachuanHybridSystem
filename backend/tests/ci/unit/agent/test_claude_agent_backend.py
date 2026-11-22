"""``ClaudeAgentBackend`` —— claude-agent 后端的接缝、网关归一化与事件翻译。

全部离线（不打真网关、不起共享 MCP、不拉 ``claude`` 子进程）。守 10 件事：

1. **身份与能力声明**：``kind == "claude-agent"``，六项能力如实；``approval`` 与
   开关同源（关掉闸门时能力声明必须同步为 ``False``——声明说 True 而没有闸门，
   前端会显示审批卡、用户点下去什么都不会发生）。
2. **base_url 归一化**：``.../v1`` 必须剥成 ``...``，否则 CLI 会拼成
   ``/v1/v1/messages``（实测 404）。这是本后端最容易「看着配置对、一跑就 404」
   的一处，必须有断言守着。
3. **模型过滤**：只有名字命中 ``anthropic`` 的模型可走这条通道。``glm53`` 在
   Anthropic 协议下会产出空回合（实测 3/3 次空正文），所以它**必须**被拒，
   而不是「照用让网关报错」。
4. **子进程环境**：代理变量必须被置空（内网网关 + 本机 Clash = 502 无 body），
   且 base_url 已剥 ``/v1``。
5. **MCP 配置**：``type=http`` + ``Authorization`` + ``x-fachuan-session`` + tier 头。
   少一个 ``x-fachuan-session`` 会让审批卡投成「无会话单」（只有超管能批）。
6. **事件翻译**：``text_delta`` → ``delta``；**``text`` 块里的 ``thinking_delta``
   必须丢弃**（网关部分路由的协议违例，转了会把思考当正文）；真 ``thinking`` 块才
   → ``thinking``；``tool_use`` 在 ``content_block_stop`` 才发（此时 JSON 才拼完）。
7. **tick**：SDK 静默期必须 ``yield None``——编排层只在后端 yield 时排空审批事件
   总线（不补这一帧，前端的审批卡永远不出现）。
8. **注册**：``ensure_registered()`` 后 ``claude-agent`` 在注册表里。
9. **审批回调拿到真实上下文**：SDK 的 ``ToolPermissionContext`` 不带业务上下文，
   会话 / 轮次 / 用户必须来自 ``_stream`` 绑定的本轮 ``RunContext``；并发两轮互不串。
10. **本轮参数下发**：``ctx.system_prompt`` / ``ctx.max_turns`` 进 ``ClaudeAgentOptions``。
11. **配置目录每轮独立**：``CLAUDE_CONFIG_DIR`` 每轮新建（0700）、结束即删（含异常与取消）；
    CLI 路径走 ``ClaudeAgentOptions.cli_path`` 而不是 env。
12. **收尾**：错误的 ``ResultMessage`` 抛 ``BackendError``（不再是一栏空白）；``usage`` 缺失
    时退回流事件累加值；``result_for`` 的保留条数有上限。

``claude_agent_backend`` 顶层**不** import SDK（只有 ``stream()`` 里延迟 import），
所以纯函数用例在 SDK 未装的 CI 上也跑得起来；需要 SDK 类型的那几条用
``pytest.importorskip`` 兜住。
"""

from __future__ import annotations

import asyncio
import os
import stat
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from apps.agent.backends import builtin
from apps.agent.backends import registry as backend_registry
from apps.agent.backends.base import AgentBackend, BackendError, BackendErrorKind, RunContext
from apps.agent.backends.claude_agent_backend import (
    APPROVAL_ENV,
    APPROVAL_REJECTED_MESSAGE,
    CLI_PATH_ENV,
    CONFIG_DIR_PREFIX,
    DEFAULT_INSTRUCTIONS,
    KIND,
    MAX_KEPT_RESULTS,
    MAX_TURNS,
    ClaudeAgentBackend,
    ClaudeAgentRunResult,
    _bind_can_use_tool,
    _RunState,
    _with_ticks,
    anthropic_base_url,
    approval_enabled,
    backend_capabilities,
    build_env,
    build_mcp_servers,
    make_config_dir,
    remove_config_dir,
    resolve_cli_path,
    select_anthropic_model,
    short_tool_name,
)
from apps.agent.backends.gateway_cache import GatewaySettings


def _ev(payload: dict[str, Any]) -> Any:
    """造一个 SDK 的 ``StreamEvent``（原始 API 事件 dict 原样带在 ``event`` 上）。"""
    from claude_agent_sdk import StreamEvent

    return StreamEvent(uuid="u", session_id="s", event=payload)


def _settings(**over: Any) -> GatewaySettings:
    base = {
        "name": "律所 kimi",
        "base_url": "http://152.16.10.110:4000/v1",
        "api_keys": ("sk-test",),
        "models": ("kimi-2.6", "glm53", "kimi-2.6(Anthropic)"),
        "default_model": "kimi-2.6",
        "enable_thinking": True,
    }
    base.update(over)
    return GatewaySettings(**base)


# ── 1. 身份与能力 ──────────────────────────────────────────────────────


def test_kind_and_protocol() -> None:
    assert KIND == "claude-agent"
    assert ClaudeAgentBackend().kind == KIND


def test_is_agent_backend_protocol() -> None:
    assert isinstance(ClaudeAgentBackend(), AgentBackend)


def test_capabilities_are_truthful() -> None:
    caps = backend_capabilities()
    assert (caps.streaming, caps.tool_calls) == (True, True)
    # CLI 自带 autocompact。
    assert caps.compaction is True
    # 未接线 LiveBackendHandle 前必须为 False：声明 True 会让前端渲染出一个
    # 「敲进去也没人接」的插话框。
    assert caps.steer is False
    assert caps.concurrent_in_session is True


def test_approval_capability_follows_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPROVAL_ENV, "off")
    assert approval_enabled() is False
    assert backend_capabilities().approval is False

    monkeypatch.setenv(APPROVAL_ENV, "1")
    assert approval_enabled() is True
    assert backend_capabilities().approval is True


# ── 2. base_url 归一化 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://152.16.10.110:4000/v1", "http://152.16.10.110:4000"),
        ("http://152.16.10.110:4000/v1/", "http://152.16.10.110:4000"),
        ("http://152.16.10.110:4000", "http://152.16.10.110:4000"),
        ("http://152.16.10.110:4000/", "http://152.16.10.110:4000"),
        ("", ""),
    ],
)
def test_anthropic_base_url_strips_v1(raw: str, expected: str) -> None:
    assert anthropic_base_url(raw) == expected


def test_anthropic_base_url_keeps_non_v1_path() -> None:
    # 只剥尾部 /v1，别把网关自己的路径前缀也吃掉。
    assert anthropic_base_url("http://gw:4000/litellm/v1") == "http://gw:4000/litellm"


# ── 3. 模型过滤（空回合防线）──────────────────────────────────────────


def test_select_model_picks_anthropic_only() -> None:
    assert select_anthropic_model(_settings(), None) == "kimi-2.6(Anthropic)"


def test_select_model_rejects_glm53() -> None:
    """``glm53`` 在 Anthropic 协议下产出空正文（实测），必须被拒而不是照用。"""
    assert select_anthropic_model(_settings(), "glm53") is None


def test_select_model_honors_anthropic_hint() -> None:
    assert select_anthropic_model(_settings(), "kimi-2.6(Anthropic)") == "kimi-2.6(Anthropic)"


def test_select_model_no_settings() -> None:
    assert select_anthropic_model(None, "kimi-2.6(Anthropic)") is None


def test_select_model_platform_without_anthropic_model() -> None:
    settings = _settings(models=("kimi-2.6", "glm53"), default_model="kimi-2.6")
    assert select_anthropic_model(settings, None) is None


# ── 4. 子进程环境 ────────────────────────────────────────────────────


def test_build_env_strips_v1_and_kills_proxy(tmp_path: Path) -> None:
    # 明显的假 key：只为断言「env 里逐字透传」，不是任何真实凭据。
    fake_key = "not-a-real-key"  # pragma: allowlist secret
    env = build_env(base_url="http://152.16.10.110:4000/v1", api_key=fake_key, model="m", config_dir=tmp_path)
    assert env["ANTHROPIC_BASE_URL"] == "http://152.16.10.110:4000"
    assert env["ANTHROPIC_API_KEY"] == fake_key
    assert env["ANTHROPIC_MODEL"] == "m"
    # 代理必须被显式置空：SDK 的 env 是叠加语义，宿主 Clash 会渗进子进程，
    # 内网网关带代理走 = 502 无 body。
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        assert env[key] == ""
    assert env["NO_PROXY"]
    assert env["DISABLE_TELEMETRY"] == "1"


# ── 5. MCP 配置 ──────────────────────────────────────────────────────


def test_build_mcp_servers_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FACHUAN_CLAUDE_TOOL_TIER", raising=False)
    servers = build_mcp_servers(url="http://127.0.0.1:8011/mcp", user_token="tok", session_id="s-1")
    cfg = servers["fachuan"]
    assert cfg["type"] == "http"
    assert cfg["url"].endswith("/mcp")
    headers = cfg["headers"]
    assert headers["Authorization"] == "Bearer tok"
    assert headers["x-fachuan-session"] == "s-1"
    # 默认 lite：full 档实测 8.3 万 token/轮，本通道只在 lite 档验过。
    assert headers["x-fachuan-tool-tier"] == "lite"


def test_short_tool_name() -> None:
    assert short_tool_name("mcp__fachuan__delete_case") == "delete_case"
    assert short_tool_name("Bash") == "Bash"


# ── 6. 事件翻译 ──────────────────────────────────────────────────────


def test_translate_text_delta() -> None:
    state = _RunState()
    frames = ClaudeAgentBackend._translate_stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "你好"}}, state
    )
    assert frames == [{"type": "delta", "content": "你好"}]
    assert state.saw_stream_text is True


def test_translate_drops_thinking_delta_inside_text_block() -> None:
    """协议违例：网关把 thinking_delta 塞进 text 块。转了会把思考当正文发给律师。"""
    state = _RunState()
    state.blocks[0] = {"type": "text", "name": "", "id": "", "json": ""}
    frames = ClaudeAgentBackend._translate_stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "想想"}},
        state,
    )
    assert frames == []


def test_translate_keeps_thinking_delta_in_thinking_block() -> None:
    state = _RunState()
    state.blocks[0] = {"type": "thinking", "name": "", "id": "", "json": ""}
    frames = ClaudeAgentBackend._translate_stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "想想"}},
        state,
    )
    assert frames == [{"type": "thinking", "content": "想想"}]


def test_translate_tool_use_emits_on_block_stop() -> None:
    state = _RunState()
    start = ClaudeAgentBackend._translate_stream_event(
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "tool_use", "id": "toolu_1", "name": "mcp__fachuan__list_cases", "input": {}},
        },
        state,
    )
    assert start == []
    for part in ('{"a"', ": 1}"):
        assert (
            ClaudeAgentBackend._translate_stream_event(
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "input_json_delta", "partial_json": part},
                },
                state,
            )
            == []
        )
    stop = ClaudeAgentBackend._translate_stream_event({"type": "content_block_stop", "index": 1}, state)
    assert stop == [
        {
            "type": "tool_call",
            "tool_call_id": "toolu_1",
            "name": "mcp__fachuan__list_cases",
            "arguments": '{"a": 1}',
        }
    ]
    assert state.tool_names["toolu_1"] == "mcp__fachuan__list_cases"


def test_text_after_tool_round_is_not_swallowed() -> None:
    """回归（2026-11-22 会话 335）：工具轮次之后的正文必须照常发出。

    事故序列：第 1 轮 assistant 只有 tool_use（无正文）→ 第 2 轮才有正文。
    旧实现把「发过任何帧」当成「正文已发过」，于是第 2 轮正文被丢弃，界面只剩
    工具卡片、一个字都没有，而 ``AgentRun`` 记了 1745 output token。
    """
    from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock

    backend = ClaudeAgentBackend()
    backend._states["r"] = _RunState()

    # 第 1 轮：只有工具调用
    first = AssistantMessage(
        content=[ToolUseBlock(id="toolu_1", name="mcp__fachuan__get_server_time", input={})],
        model="kimi26",
    )
    frames1 = backend._translate(first, "r")
    assert [f["type"] for f in frames1] == ["tool_call"]

    # 第 2 轮：正文（工具结果回来之后）
    second = AssistantMessage(content=[TextBlock(text="民法典874条属于技术合同章。")], model="kimi26")
    frames2 = backend._translate(second, "r")
    assert frames2 == [{"type": "delta", "content": "民法典874条属于技术合同章。"}], (
        "工具轮次之后的正文被丢掉了——这正是会话 335 里 claude-agent 一片空白的原因"
    )

    # 第 3 轮：再多一轮正文也必须发（工具循环可能有多轮）
    third = AssistantMessage(content=[TextBlock(text="另见刑法285条。")], model="kimi26")
    assert backend._translate(third, "r") == [{"type": "delta", "content": "另见刑法285条。"}]


def test_stream_text_suppresses_assistant_fallback() -> None:
    """流式通道吐过正文时，assistant 整段不能再发一遍（否则前端双份回答）。"""
    from claude_agent_sdk import AssistantMessage, TextBlock

    backend = ClaudeAgentBackend()
    backend._states["r"] = _RunState()
    backend._translate(
        _ev({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "逐字"}}),
        "r",
    )
    msg = AssistantMessage(content=[TextBlock(text="逐字")], model="kimi26")
    assert backend._translate(msg, "r") == []


def test_translate_usage_from_stream_events() -> None:
    state = _RunState()
    ClaudeAgentBackend._translate_stream_event(
        {
            "type": "message_start",
            "message": {
                "usage": {
                    "input_tokens": 10,
                    "cache_read_input_tokens": 2,
                    "cache_creation_input_tokens": 3,
                }
            },
        },
        state,
    )
    ClaudeAgentBackend._translate_stream_event(
        {"type": "message_delta", "usage": {"input_tokens": 10, "output_tokens": 7}}, state
    )
    assert (state.input_tokens, state.output_tokens, state.cache_read_tokens, state.cache_write_tokens) == (
        10,
        7,
        2,
        3,
    )
    assert state.reported_usage is True


def test_usage_frame_one_per_turn() -> None:
    result = SimpleNamespace(
        usage={"input_tokens": 8, "output_tokens": 20, "cache_creation_input_tokens": 128, "cache_read_input_tokens": 0}
    )
    frame = ClaudeAgentBackend._usage_frame(result)
    assert frame == {
        "type": "usage",
        "input_tokens": 8,
        "output_tokens": 20,
        "cache_read_tokens": 0,
        "cache_write_tokens": 128,
    }


def test_usage_frame_absent_when_no_numbers() -> None:
    # 拿不到就返回 None——编造的 0 无法与真实 0 区分。
    assert ClaudeAgentBackend._usage_frame(SimpleNamespace(usage={})) is None


# ── 7. tick ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_with_ticks_yields_none_while_silent() -> None:
    """SDK 静默期必须让出 tick，否则审批卡永远不出现。"""

    async def _slow() -> AsyncIterator[Any]:
        await asyncio.sleep(0.45)
        yield "msg"

    seen: list[Any] = []
    async for item in _with_ticks(_slow()):
        seen.append(item)
        if item == "msg":
            break
    assert None in seen, f"静默期没有 yield None：{seen}"
    assert seen[-1] == "msg"


# ── 8. 错误分类 ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("exc_factory", "kind"),
    [
        (lambda: type("CLINotFoundError", (Exception,), {})("claude not found"), BackendErrorKind.UNAVAILABLE),
        (lambda: type("CLIConnectionError", (Exception,), {})("connection reset"), BackendErrorKind.UNAVAILABLE),
        (lambda: RuntimeError("401 unauthorized"), BackendErrorKind.AUTH),
        (lambda: RuntimeError("429 rate limit"), BackendErrorKind.RATE_LIMITED),
        (lambda: RuntimeError("context window exceeded"), BackendErrorKind.CONTEXT_OVERFLOW),
        (lambda: RuntimeError("weird"), BackendErrorKind.UNKNOWN),
    ],
)
def test_wrap_error(exc_factory: Any, kind: BackendErrorKind) -> None:
    wrapped = ClaudeAgentBackend._wrap_error(exc_factory())
    assert isinstance(wrapped, BackendError)
    assert wrapped.kind == kind


# ── 9. 注册 ─────────────────────────────────────────────────────────


def test_registered_when_sdk_present() -> None:
    pytest.importorskip("claude_agent_sdk")
    builtin.ensure_registered()
    assert "claude-agent" in backend_registry.available_kinds()


def test_ensure_registered_is_idempotent() -> None:
    builtin.ensure_registered()
    builtin.ensure_registered()
    assert len([k for k in backend_registry.available_kinds() if k == "claude-agent"]) <= 1


# ── 10. 审批回调：会话 / 轮次 / 用户来自绑定的 ctx ────────────────────────────


def _ctx(
    *,
    run_id: str = "run-A",
    session_id: str = "sess-A",
    user_id: int | None = 7,
    system_prompt: str | None = None,
    max_turns: int | None = None,
) -> RunContext:
    return RunContext(
        run_id=run_id,
        session=SimpleNamespace(session_id=session_id),
        user_id=user_id,
        prompt="p",
        user_token="tok",
        model=None,
        tool_selection=None,
        system_prompt=system_prompt,
        max_turns=max_turns,
    )


class _ApprovalSpy:
    """替换审批链的三个依赖，记录它们收到的参数。"""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, refusal: str | None = None, approve: bool = True) -> None:
        from apps.agent.services import approval as approval_pkg
        from apps.agent.services.approval import RiskLevel
        from apps.agent.services.approval import policy as approval_policy

        self.refusal_calls: list[dict[str, Any]] = []
        self.approval_calls: list[dict[str, Any]] = []
        self._refusal = refusal
        self._approve = approve

        def fake_refusal(*, session_id: str | None, tool_name: str) -> str | None:
            self.refusal_calls.append({"session_id": session_id, "tool_name": tool_name})
            return self._refusal

        async def fake_request_approval(**kwargs: Any) -> tuple[bool, str, str]:
            self.approval_calls.append(kwargs)
            return self._approve, "approval-1", ""

        monkeypatch.setattr(approval_policy, "multi_lane_write_refusal", fake_refusal)
        monkeypatch.setattr(approval_pkg, "classify_risk", lambda _name, _args: RiskLevel.HIGH)
        monkeypatch.setattr(approval_pkg, "request_approval", fake_request_approval)


def _perm_ctx(tool_use_id: str = "toolu_9") -> Any:
    """SDK 真实的回调参数：只有 signal / suggestions / tool_use_id 等，没有业务上下文。"""
    from claude_agent_sdk import ToolPermissionContext

    return ToolPermissionContext(tool_use_id=tool_use_id)


@pytest.mark.asyncio
async def test_can_use_tool_uses_bound_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    """回归：旧实现从 ``context.context`` 取 ctx，而 SDK 参数上没有这个字段 → 全是空值。"""
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk import PermissionResultAllow

    spy = _ApprovalSpy(monkeypatch)
    callback = _bind_can_use_tool(_ctx())
    result = await callback("mcp__fachuan__update_case", {"id": 1}, _perm_ctx())

    assert isinstance(result, PermissionResultAllow)
    assert spy.refusal_calls == [{"session_id": "sess-A", "tool_name": "mcp__fachuan__update_case"}]
    assert len(spy.approval_calls) == 1
    call = spy.approval_calls[0]
    assert (call["session_id"], call["run_id"], call["user_id"]) == ("sess-A", "run-A", 7)
    assert call["tool_call_id"] == "toolu_9"
    assert call["tool_args"] == {"id": 1}


@pytest.mark.asyncio
async def test_multi_lane_refusal_sees_real_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """多栏禁写检查必须拿到真实会话 id：拿到 None 时它恒放行（旧实现正是被这样绕过的）。"""
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk import PermissionResultDeny

    spy = _ApprovalSpy(monkeypatch, refusal="多栏并答时不能直接改文件")
    result = await _bind_can_use_tool(_ctx())("mcp__fachuan__update_case", {}, _perm_ctx())

    assert isinstance(result, PermissionResultDeny)
    assert result.message == "多栏并答时不能直接改文件"
    assert spy.refusal_calls[0]["session_id"] == "sess-A"
    assert spy.approval_calls == []


@pytest.mark.asyncio
async def test_blocked_tool_denied_without_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk import PermissionResultDeny

    spy = _ApprovalSpy(monkeypatch)
    result = await _bind_can_use_tool(_ctx())("mcp__fachuan__delete_case", {"id": 1}, _perm_ctx())

    assert isinstance(result, PermissionResultDeny)
    assert "delete_case" in result.message
    assert spy.refusal_calls == []
    assert spy.approval_calls == []


@pytest.mark.asyncio
async def test_rejected_approval_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk import PermissionResultDeny

    _ApprovalSpy(monkeypatch, approve=False)
    result = await _bind_can_use_tool(_ctx())("mcp__fachuan__update_case", {}, _perm_ctx())

    assert isinstance(result, PermissionResultDeny)
    assert result.message == APPROVAL_REJECTED_MESSAGE


@pytest.mark.asyncio
async def test_concurrent_bindings_do_not_cross(monkeypatch: pytest.MonkeyPatch) -> None:
    """两轮同时挂在审批上：各自的回调只认各自的 ctx（后端是单例，不能有共享状态）。"""
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

    from apps.agent.services import approval as approval_pkg

    _ApprovalSpy(monkeypatch)
    calls: list[dict[str, Any]] = []
    both_pending = asyncio.Event()

    async def slow_request_approval(**kwargs: Any) -> tuple[bool, str, str]:
        calls.append(kwargs)
        if len(calls) == 2:
            both_pending.set()
        await asyncio.wait_for(both_pending.wait(), timeout=1.0)
        return kwargs["session_id"] == "sess-A", "approval", ""

    monkeypatch.setattr(approval_pkg, "request_approval", slow_request_approval)

    cb_a = _bind_can_use_tool(_ctx(run_id="run-A", session_id="sess-A", user_id=1))
    cb_b = _bind_can_use_tool(_ctx(run_id="run-B", session_id="sess-B", user_id=2))
    res_a, res_b = await asyncio.gather(
        cb_a("mcp__fachuan__update_case", {}, _perm_ctx("toolu_a")),
        cb_b("mcp__fachuan__update_case", {}, _perm_ctx("toolu_b")),
    )

    assert isinstance(res_a, PermissionResultAllow)
    assert isinstance(res_b, PermissionResultDeny)
    seen = sorted((c["session_id"], c["run_id"], c["user_id"], c["tool_call_id"]) for c in calls)
    assert seen == [("sess-A", "run-A", 1, "toolu_a"), ("sess-B", "run-B", 2, "toolu_b")]


# ── 11. 本轮参数下发：system_prompt / max_turns / 回调绑定 ─────────────────────


class _FakeClient:
    """替换 ``ClaudeSDKClient``：记录 options，不拉子进程。"""

    captured: list[Any] = []

    def __init__(self, options: Any) -> None:
        self.options = options
        _FakeClient.captured.append(options)

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def query(self, prompt: str) -> None:
        return None

    async def receive_response(self) -> AsyncIterator[Any]:
        # 空流：本组用例只关心 options。``return`` 在 ``yield`` 之前，让它成为异步生成器。
        return
        yield


async def _run_stream(monkeypatch: pytest.MonkeyPatch, ctx: RunContext) -> Any:
    import claude_agent_sdk

    _FakeClient.captured = []
    monkeypatch.setattr(claude_agent_sdk, "ClaudeSDKClient", _FakeClient)
    backend = ClaudeAgentBackend()

    async def fake_resolve(_ctx: RunContext) -> dict[str, Any]:
        return {
            "base_url": "http://gw:4000/v1",
            "api_key": "not-a-real-key",  # pragma: allowlist secret
            "model": "kimi-2.6(Anthropic)",
            "mcp_servers": {},
        }

    monkeypatch.setattr(backend, "_resolve_gateway", fake_resolve)
    frames = [frame async for frame in backend.stream(ctx) if frame is not None]
    assert frames == []
    assert len(_FakeClient.captured) == 1
    return _FakeClient.captured[0]


@pytest.mark.asyncio
async def test_stream_passes_system_prompt_and_max_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("claude_agent_sdk")
    options = await _run_stream(monkeypatch, _ctx(system_prompt="综合规则：每条结论标来源。", max_turns=8))
    assert options.system_prompt == "综合规则：每条结论标来源。"
    assert options.max_turns == 8


@pytest.mark.asyncio
async def test_stream_defaults_without_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("claude_agent_sdk")
    options = await _run_stream(monkeypatch, _ctx())
    assert options.system_prompt == DEFAULT_INSTRUCTIONS
    assert options.max_turns == MAX_TURNS


@pytest.mark.asyncio
async def test_stream_binds_ctx_into_can_use_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """端到端：``_stream`` 交给 SDK 的回调本身就带着本轮 ctx。"""
    pytest.importorskip("claude_agent_sdk")
    spy = _ApprovalSpy(monkeypatch)
    options = await _run_stream(monkeypatch, _ctx(run_id="run-S", session_id="sess-S", user_id=42))

    await options.can_use_tool("mcp__fachuan__update_case", {}, _perm_ctx())
    call = spy.approval_calls[0]
    assert (call["session_id"], call["run_id"], call["user_id"]) == ("sess-S", "run-S", 42)


# ── 11. 配置目录每轮独立 / CLI 路径 ───────────────────────────────────


def test_build_env_uses_given_config_dir_and_no_cli_env(tmp_path: Path) -> None:
    env = build_env(base_url="http://gw/v1", api_key="k", model="m", config_dir=tmp_path)  # pragma: allowlist secret
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    # SDK 不读这个 env：CLI 路径只经 ClaudeAgentOptions.cli_path 下发。
    assert CLI_PATH_ENV not in env


def test_make_config_dir_is_private_and_unique(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    first, second = make_config_dir(), make_config_dir()
    assert first != second
    for path in (first, second):
        assert path.parent == tmp_path
        assert path.name.startswith(CONFIG_DIR_PREFIX)
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    (first / "projects").mkdir()
    (first / "projects" / "session.jsonl").write_text("律师对话", encoding="utf-8")
    remove_config_dir(first)
    assert not first.exists()
    remove_config_dir(None)  # 没建成目录时调用也不炸


def test_make_config_dir_sweeps_stale_leftovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    legacy = tmp_path / f"{CONFIG_DIR_PREFIX}config"  # 旧版本的共用目录
    legacy.mkdir()
    fresh = tmp_path / f"{CONFIG_DIR_PREFIX}fresh"  # 另一轮正在用的目录
    fresh.mkdir()
    old = time.time() - 7 * 3600
    os.utime(legacy, (old, old))
    make_config_dir()
    assert not legacy.exists()
    assert fresh.exists()


def test_resolve_cli_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CLI_PATH_ENV, raising=False)
    assert resolve_cli_path() is None
    monkeypatch.setenv(CLI_PATH_ENV, "  /opt/claude/bin/claude  ")
    assert resolve_cli_path() == "/opt/claude/bin/claude"


class _ScriptedClient:
    """按脚本吐消息的 ``ClaudeSDKClient`` 替身：记录 options 与进入时配置目录的状态。"""

    captured: list[Any] = []
    #: 进入 ``async with`` 时看到的 (目录, 是否存在, 权限位)
    seen_dirs: list[tuple[Path, bool, int]] = []
    script: list[Any] = []
    hang = False
    fail: BaseException | None = None

    def __init__(self, options: Any) -> None:
        self.options = options
        _ScriptedClient.captured.append(options)

    async def __aenter__(self) -> _ScriptedClient:
        cfg = Path(self.options.env["CLAUDE_CONFIG_DIR"])
        _ScriptedClient.seen_dirs.append((cfg, cfg.is_dir(), stat.S_IMODE(cfg.stat().st_mode)))
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def query(self, prompt: str) -> None:
        return None

    async def receive_response(self) -> AsyncIterator[Any]:
        for msg in _ScriptedClient.script:
            yield msg
        if _ScriptedClient.fail is not None:
            raise _ScriptedClient.fail
        if _ScriptedClient.hang:
            await asyncio.Event().wait()


def _scripted_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    script: list[Any] | None = None,
    *,
    hang: bool = False,
    fail: BaseException | None = None,
) -> ClaudeAgentBackend:
    import claude_agent_sdk

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    _ScriptedClient.captured = []
    _ScriptedClient.seen_dirs = []
    _ScriptedClient.script = list(script or [])
    _ScriptedClient.hang = hang
    _ScriptedClient.fail = fail
    monkeypatch.setattr(claude_agent_sdk, "ClaudeSDKClient", _ScriptedClient)
    backend = ClaudeAgentBackend()

    async def fake_resolve(_ctx: RunContext) -> dict[str, Any]:
        return {
            "base_url": "http://gw:4000/v1",
            "api_key": "not-a-real-key",  # pragma: allowlist secret
            "model": "kimi-2.6(Anthropic)",
            "mcp_servers": {},
        }

    monkeypatch.setattr(backend, "_resolve_gateway", fake_resolve)
    return backend


def _result(**over: Any) -> Any:
    from claude_agent_sdk import ResultMessage

    fields: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "cli-session",
    }
    fields.update(over)
    return ResultMessage(**fields)


async def _collect(backend: ClaudeAgentBackend, ctx: RunContext) -> list[dict[str, Any]]:
    return [frame async for frame in backend.stream(ctx) if frame is not None]


def _leftover_dirs(tmp_path: Path) -> list[Path]:
    return sorted(tmp_path.glob(f"{CONFIG_DIR_PREFIX}*"))


@pytest.mark.asyncio
async def test_config_dir_is_new_per_run_and_removed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    backend = _scripted_backend(monkeypatch, tmp_path, [_result()])
    await _collect(backend, _ctx(run_id="run-1"))
    _ScriptedClient.script = [_result()]
    await _collect(backend, _ctx(run_id="run-2"))

    (dir_1, existed_1, mode_1), (dir_2, existed_2, mode_2) = _ScriptedClient.seen_dirs
    assert dir_1 != dir_2
    assert existed_1 and existed_2
    assert mode_1 == mode_2 == 0o700
    # 跑完即删：系统临时目录下不留任何一轮的会话记录
    assert _leftover_dirs(tmp_path) == []


@pytest.mark.asyncio
async def test_config_dir_removed_when_run_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    backend = _scripted_backend(monkeypatch, tmp_path, fail=RuntimeError("CLI 崩了"))
    with pytest.raises(BackendError):
        await _collect(backend, _ctx())
    assert len(_ScriptedClient.seen_dirs) == 1
    assert _leftover_dirs(tmp_path) == []


@pytest.mark.asyncio
async def test_config_dir_removed_when_cancelled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    backend = _scripted_backend(monkeypatch, tmp_path, hang=True)

    async def consume() -> None:
        async for _frame in backend.stream(_ctx()):
            pass

    task = asyncio.create_task(consume())
    for _ in range(200):
        if _ScriptedClient.seen_dirs:
            break
        await asyncio.sleep(0.01)
    assert _leftover_dirs(tmp_path), "运行中目录应当存在"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _leftover_dirs(tmp_path) == []


@pytest.mark.asyncio
async def test_cli_path_goes_to_options_not_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    monkeypatch.setenv(CLI_PATH_ENV, "/opt/claude/bin/claude")
    backend = _scripted_backend(monkeypatch, tmp_path, [_result()])
    await _collect(backend, _ctx())
    options = _ScriptedClient.captured[0]
    assert str(options.cli_path) == "/opt/claude/bin/claude"
    assert CLI_PATH_ENV not in options.env


@pytest.mark.asyncio
async def test_cli_path_defaults_to_sdk_lookup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    monkeypatch.delenv(CLI_PATH_ENV, raising=False)
    backend = _scripted_backend(monkeypatch, tmp_path, [_result()])
    await _collect(backend, _ctx())
    assert _ScriptedClient.captured[0].cli_path is None


# ── 12. 收尾：错误结果 / 用量回退 / 结果保留上限 ───────────────────────


@pytest.mark.asyncio
async def test_max_turns_result_raises_readable_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    backend = _scripted_backend(
        monkeypatch,
        tmp_path,
        [_result(is_error=True, subtype="error_max_turns", num_turns=8, usage={"input_tokens": 30, "output_tokens": 4})],
    )
    frames: list[dict[str, Any]] = []
    with pytest.raises(BackendError) as info:
        async for frame in backend.stream(_ctx(run_id="run-M", max_turns=8)):
            if frame is not None:
                frames.append(frame)
    assert "8 轮" in str(info.value)
    # 失败的一轮也花了钱：用量帧在报错前照发
    assert [frame["type"] for frame in frames] == ["usage"]
    # 失败轮不留收尾事实
    assert backend.result_for("run-M") is None


@pytest.mark.asyncio
async def test_api_error_result_raises_instead_of_blank_lane(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    backend = _scripted_backend(
        monkeypatch,
        tmp_path,
        [_result(is_error=True, subtype="success", api_error_status=429, result="API Error: rate limited")],
    )
    with pytest.raises(BackendError) as info:
        await _collect(backend, _ctx())
    assert info.value.kind == BackendErrorKind.RATE_LIMITED
    assert info.value.retryable is True


def test_result_failure_classification() -> None:
    def failure(**over: Any) -> BackendError | None:
        fields = {"subtype": "success", "is_error": True, "terminal_reason": None, "errors": None, "result": None}
        fields.update(over)
        return ClaudeAgentBackend._result_failure(SimpleNamespace(**fields), max_turns=24)

    assert failure(is_error=False) is None
    assert failure(api_error_status=401).kind == BackendErrorKind.AUTH  # type: ignore[union-attr]
    assert failure(api_error_status=503).kind == BackendErrorKind.UNAVAILABLE  # type: ignore[union-attr]
    turns = failure(subtype="success", terminal_reason="max_turns")
    assert turns is not None and "24 轮" in str(turns)
    during = failure(subtype="error_during_execution", is_error=False, errors=["工具进程退出"])
    assert during is not None and "工具进程退出" in str(during)


def test_usage_frame_falls_back_to_stream_totals() -> None:
    state = _RunState(input_tokens=120, output_tokens=30, cache_read_tokens=64, reported_usage=True)
    assert ClaudeAgentBackend._usage_frame(SimpleNamespace(usage=None), state) == {
        "type": "usage",
        "input_tokens": 120,
        "output_tokens": 30,
        "cache_read_tokens": 64,
        "cache_write_tokens": 0,
    }
    # 汇总值优先于累加值
    frame = ClaudeAgentBackend._usage_frame(SimpleNamespace(usage={"input_tokens": 9, "output_tokens": 1}), state)
    assert frame is not None and (frame["input_tokens"], frame["output_tokens"]) == (9, 1)
    # 流事件里也从没报过用量 → 不编造
    assert ClaudeAgentBackend._usage_frame(SimpleNamespace(usage=None), _RunState()) is None


@pytest.mark.asyncio
async def test_stream_usage_falls_back_when_result_has_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    script = [
        _ev({"type": "message_start", "message": {"usage": {"input_tokens": 10}}}),
        _ev({"type": "message_delta", "usage": {"output_tokens": 5}}),
        _result(usage=None),
    ]
    backend = _scripted_backend(monkeypatch, tmp_path, script)
    frames = await _collect(backend, _ctx())
    usage = [frame for frame in frames if frame["type"] == "usage"]
    assert len(usage) == 1
    assert (usage[0]["input_tokens"], usage[0]["output_tokens"]) == (10, 5)


@pytest.mark.asyncio
async def test_successful_run_records_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    backend = _scripted_backend(monkeypatch, tmp_path, [_result()])
    await _collect(backend, _ctx(run_id="run-OK"))
    result = backend.result_for("run-OK")
    assert result is not None and result.model == "kimi-2.6(Anthropic)"


def test_results_are_bounded() -> None:
    backend = ClaudeAgentBackend()
    for index in range(MAX_KEPT_RESULTS + 5):
        backend._remember_result(f"run-{index}", ClaudeAgentRunResult(model="m"))
    assert len(backend._results) == MAX_KEPT_RESULTS
    assert backend.result_for("run-0") is None  # 最旧的被挤掉
    assert backend.result_for(f"run-{MAX_KEPT_RESULTS + 4}") is not None
    # 同一轮重复写入不占新位置，且移到最新
    backend._remember_result("run-5", ClaudeAgentRunResult(model="m2"))
    assert len(backend._results) == MAX_KEPT_RESULTS
    assert next(reversed(backend._results)) == "run-5"
