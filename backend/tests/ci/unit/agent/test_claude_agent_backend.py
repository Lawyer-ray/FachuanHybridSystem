"""``ClaudeAgentBackend`` —— claude-agent 后端的接缝、网关归一化与事件翻译。

全部离线（不打真网关、不起共享 MCP、不拉 ``claude`` 子进程）。守 8 件事：

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

``claude_agent_backend`` 顶层**不** import SDK（只有 ``stream()`` 里延迟 import），
所以纯函数用例在 SDK 未装的 CI 上也跑得起来；需要 SDK 类型的那几条用
``pytest.importorskip`` 兜住。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from apps.agent.backends import builtin
from apps.agent.backends import registry as backend_registry
from apps.agent.backends.base import AgentBackend, BackendError, BackendErrorKind
from apps.agent.backends.claude_agent_backend import (
    APPROVAL_ENV,
    KIND,
    ClaudeAgentBackend,
    _RunState,
    _with_ticks,
    anthropic_base_url,
    approval_enabled,
    backend_capabilities,
    build_env,
    build_mcp_servers,
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


def test_build_env_strips_v1_and_kills_proxy() -> None:
    # 明显的假 key：只为断言「env 里逐字透传」，不是任何真实凭据。
    fake_key = "not-a-real-key"  # pragma: allowlist secret
    env = build_env(base_url="http://152.16.10.110:4000/v1", api_key=fake_key, model="m", cli_path=None)
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
