"""``QoderBackend`` —— qoder 后端的接缝、工具面硬约束与事件翻译。

全部离线（不打真网关、不起共享 MCP、不拉 ``qodercli`` 子进程、不联网）。守 12 件事：

1. **身份与能力声明**：``kind == "qoder"``；``approval`` 与开关同源（关掉闸门时能力
   声明必须同步为 ``False``——声明 True 而没有闸门，前端会显示审批卡、点下去什么
   都不会发生）。
2. **模型来源**：默认 ``qoder``（云侧模型）、未知取值也回落 ``qoder``。**不能**
   回落成 ``gateway``：那会把「配置写错」变成「整栏跑不起来」，还会静默改掉
   「提示词出不出境」这条合规判断。
3. **鉴权优先级**：个人令牌 → 服务账号密钥 → 复用本机登录态；且只有配了显式凭据
   才敢把配置目录临时化（登录态存在默认配置目录里，临时化就等于「未登录」）。
4. **子进程环境**：有显式凭据时 ``QODER_CONFIG_DIR`` 指向本轮临时目录；没有时
   **不设**该变量。
5. **MCP 配置**：``type=http`` + ``Authorization`` + ``x-fachuan-session`` + tier 头。
   没有律师 token 时**不挂工具**（不许退回服务账号，那会让全所数据同一身份外流）。
6. **工具面四件套**：``tools=[]`` / ``allowed_tools=[]`` / ``setting_sources=[]`` /
   ``skills=[]``，且 ``disallowed_tools`` 用 MCP **全名**（写原始名会静默不生效）。
7. **``PreToolUse`` hook**：高危工具强制置 ``ask``（qoder 自己的分类器不能替律师
   放行）、不可逆删除类直接 ``deny``、审批关掉时不干预。
8. **``can_use_tool``**：不可逆删除类连审批卡都不弹；高危才走 ``request_approval``；
   会话/轮次/用户来自本轮 ``RunContext``（SDK 上下文不带业务字段）。
9. **事件翻译**：``text_delta`` → ``delta``；**``text`` 块里的 ``thinking_delta``
   必须丢弃**（协议违例，转了会把思考当正文）；真 ``thinking`` 块才 → ``thinking``；
   ``tool_use`` 在 ``content_block_stop`` 才发（此时 JSON 才拼完）；流式通时
   ``AssistantMessage`` 的兜底必须关掉（否则同一段正文出现两遍）。
10. **tick**：SDK 静默期必须 ``yield None``——编排层只在后端 yield 时排空审批事件总线。
11. **错误分类**：qoder 数字码 → 分类 + 人话（105 登录过期 / 80411 超长 / 500 可重试）。
12. **SDK 导入面**（patch 级护栏）：``qoder-agent-sdk`` 声明 ``mcp<2``，本仓库强制
    ``mcp[cli]>=2.2.0``（见 ``pyproject.toml`` 的 ``override-dependencies``）。这条
    测试按名字钉住它真正用到的那些 mcp 符号——mcp 升到删名的版本时当场红。

``qoder_backend`` 顶层**不** import SDK（只有 ``stream()`` / ``qoder_auth()`` /
``_translate()`` 里延迟 import），所以纯函数用例在 SDK 未装的 CI 上照样跑；
需要 SDK 类型的那几条用 ``pytest.importorskip`` 兜住。
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
from apps.agent.backends.base import AgentBackend, BackendError, BackendErrorKind, RunContext
from apps.agent.backends.qoder_backend import (
    ACCESS_TOKEN_ENV,
    APPROVAL_ENV,
    APPROVAL_REJECTED_MESSAGE,
    BLOCKED_TOOL_NAMES,
    CONFIG_DIR_PREFIX,
    DEFAULT_INSTRUCTIONS,
    ERROR_CODES,
    KIND,
    MAX_KEPT_RESULTS,
    MODEL_SOURCE_ENV,
    MODEL_SOURCE_GATEWAY,
    MODEL_SOURCE_QODER,
    PROXY_ENV,
    SA_KEY_ENV,
    QoderBackend,
    QoderRunResult,
    _can_use_tool,
    _error_code,
    _pre_tool_use,
    _RunState,
    _system_prompt,
    approval_enabled,
    backend_capabilities,
    build_env,
    build_mcp_servers,
    disallowed_tools,
    has_explicit_auth,
    is_available,
    make_config_dir,
    model_source,
    qoder_auth,
    remove_config_dir,
    resolve_cli_path,
    resolve_proxy,
    short_tool_name,
    tool_tier,
)
from apps.agent.backends.ticks import with_ticks

pytestmark = pytest.mark.unit

_SDK = pytest.mark.skipif(not is_available(), reason="未安装 qoder-agent-sdk")


def _ctx(**over: Any) -> RunContext:
    """造一个本轮 ``RunContext``（只带后端真正读的字段）。"""
    base: dict[str, Any] = {
        "run_id": "s1:qoder:1",
        "session": SimpleNamespace(session_id="s1"),
        "user_id": 7,
        "prompt": "查一下 112 个案件",
        "user_token": "tok-lawyer",
        "model": None,
        "tool_selection": None,
    }
    base.update(over)
    return RunContext(**base)


# ── 1. 身份与能力 ──────────────────────────────────────────────────────


def test_kind_and_protocol() -> None:
    assert KIND == "qoder"
    assert QoderBackend().kind == KIND
    assert isinstance(QoderBackend(), AgentBackend)


def test_capabilities_are_truthful() -> None:
    caps = backend_capabilities()
    assert (caps.streaming, caps.tool_calls) == (True, True)
    # 单轮内 CLI 自带 autocompact。
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


def test_registered_by_ensure_registered() -> None:
    """``ensure_registered()`` 之后 qoder 必须出现在注册表里（SDK 装了的话）。"""
    if not is_available():
        pytest.skip("未安装 qoder-agent-sdk")
    backend_registry.clear()
    builtin._attempted.discard(KIND)
    try:
        builtin.ensure_registered()
        assert KIND in backend_registry.available_kinds()
        assert isinstance(backend_registry.get(KIND), QoderBackend)
    finally:
        backend_registry.clear()
        builtin._registered = False
        builtin._attempted.discard(KIND)


# ── 2/3. 模型来源与鉴权 ────────────────────────────────────────────────


def test_model_source_defaults_to_qoder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MODEL_SOURCE_ENV, raising=False)
    assert model_source() == MODEL_SOURCE_QODER


def test_model_source_unknown_value_falls_back_to_qoder(monkeypatch: pytest.MonkeyPatch) -> None:
    """写错的取值必须回落 ``qoder``，不许回落 ``gateway``。

    回落 ``gateway`` 的两种坏结果：①没配平台就整栏起不来；②配了平台就**静默**把
    提示词从「发往 Qoder 云」改成「发往律所网关」——这是合规判断，不能由拼写决定。
    """
    monkeypatch.setenv(MODEL_SOURCE_ENV, "gatewayy")
    assert model_source() == MODEL_SOURCE_QODER

    monkeypatch.setenv(MODEL_SOURCE_ENV, " GATEWAY ")
    assert model_source() == MODEL_SOURCE_GATEWAY


def test_has_explicit_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ACCESS_TOKEN_ENV, raising=False)
    monkeypatch.delenv(SA_KEY_ENV, raising=False)
    assert has_explicit_auth() is False

    monkeypatch.setenv(ACCESS_TOKEN_ENV, "pat-xxx")
    assert has_explicit_auth() is True


@_SDK
def test_auth_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """令牌 > 服务账号 > 本机登录态。"""
    monkeypatch.setenv(ACCESS_TOKEN_ENV, "pat-xxx")
    monkeypatch.setenv(SA_KEY_ENV, "sa-yyy")
    assert getattr(qoder_auth(), "type", "") == "accessToken"

    monkeypatch.delenv(ACCESS_TOKEN_ENV)
    assert getattr(qoder_auth(), "type", "") == "serviceAccount"

    monkeypatch.delenv(SA_KEY_ENV)
    assert getattr(qoder_auth(), "type", "") == "qodercli"


# ── 4/5. 子进程环境与 MCP ──────────────────────────────────────────────


def test_env_sets_config_dir_only_when_given() -> None:
    """没有显式凭据时**不设** ``QODER_CONFIG_DIR``：设了就等于「未登录」。

    登录态存在默认配置目录（``~/.qoder``）里，把它指到临时目录会让 CLI 认为
    没有登录——这是本后端最容易「看着配好、一跑就报未登录」的一处。
    """
    without = build_env(config_dir=None)
    assert "QODER_CONFIG_DIR" not in without

    with_dir = build_env(config_dir=make_config_dir())
    assert with_dir["QODER_CONFIG_DIR"]
    assert with_dir["DISABLE_TELEMETRY"] == "1"


def test_config_dir_is_private_and_removable() -> None:
    path = make_config_dir()
    try:
        assert path.name.startswith(CONFIG_DIR_PREFIX)
        assert oct(os.stat(path).st_mode)[-3:] == "700"
    finally:
        remove_config_dir(path)
    assert not path.exists()


def test_mcp_servers_carry_lawyer_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FACHUAN_QODER_TOOL_TIER", raising=False)
    servers = build_mcp_servers(url="http://127.0.0.1:8011/mcp", user_token="tok-lawyer", session_id="s1")
    fachuan = servers["fachuan"]
    assert fachuan["type"] == "http"
    assert fachuan["url"] == "http://127.0.0.1:8011/mcp"
    # 少 Authorization = 没有律师身份；少 x-fachuan-session = 审批卡投成「无会话单」。
    assert fachuan["headers"]["Authorization"] == "Bearer tok-lawyer"
    assert fachuan["headers"]["x-fachuan-session"] == "s1"
    assert fachuan["headers"]["x-fachuan-tool-tier"] == "lite"


def test_no_token_means_no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有律师 token 时宁可不挂工具，也不退回服务账号。"""
    monkeypatch.setenv("FACHUAN_MCP_SHARED", "1")
    backend = QoderBackend()
    assert backend._mcp_servers(_ctx(user_token="")) == {}
    assert backend._mcp_servers(_ctx(user_token="   ")) == {}


def test_tool_tier_and_cli_path_and_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FACHUAN_QODER_TOOL_TIER", raising=False)
    assert tool_tier() == "lite"
    monkeypatch.setenv("FACHUAN_QODER_TOOL_TIER", "FULL")
    assert tool_tier() == "full"
    monkeypatch.setenv("FACHUAN_QODER_TOOL_TIER", "huge")
    assert tool_tier() == "lite"

    monkeypatch.delenv("FACHUAN_QODER_CLI_PATH", raising=False)
    assert resolve_cli_path() is None
    monkeypatch.setenv("FACHUAN_QODER_CLI_PATH", "/opt/qodercli")
    assert resolve_cli_path() == "/opt/qodercli"

    monkeypatch.delenv(PROXY_ENV, raising=False)
    assert resolve_proxy() is None
    monkeypatch.setenv(PROXY_ENV, "http://127.0.0.1:7890")
    assert resolve_proxy() == "http://127.0.0.1:7890"


# ── 6. 工具面四件套 ────────────────────────────────────────────────────


def test_disallowed_tools_use_full_mcp_names() -> None:
    """``disallowed_tools`` 按工具**全名**匹配，写原始名会静默不生效。"""
    names = disallowed_tools()
    assert "mcp__fachuan__delete_case" in names
    assert not any(not name.startswith("mcp__fachuan__") for name in names)
    assert set(BLOCKED_TOOL_NAMES) == {"delete_case"}


def test_short_tool_name() -> None:
    assert short_tool_name("mcp__fachuan__delete_case") == "delete_case"
    assert short_tool_name("Bash") == "Bash"


@_SDK
def test_hardening_flags_are_emitted() -> None:
    """四件套必须真的变成 CLI 参数（声明安全、实际没传 = 静默失效）。

    这条用 SDK 自己的 ``build_session_args()`` 把参数拼出来看，而不是读我们的
    选项 dict——选项写对了但 SDK 不翻译成 flag 的情况，只有这里能抓到。

    ``tools=[]`` 必须翻成 ``--tools ""``（CLI 的帮助文本："" to disable all）。
    写成「不传 --tools」的后果是 **全量内置工具**：读文件 / 跑 shell 直通 RCE，
    而提示注入只需要一次工具结果就能触发。
    """
    from qoder_agent_sdk import HookMatcher, QoderAgentOptions
    from qoder_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    ctx = _ctx()
    options = QoderAgentOptions(
        cwd="/tmp",
        env=build_env(config_dir=None),
        tools=[],
        skills=[],
        setting_sources=[],
        allowed_tools=[],
        disallowed_tools=disallowed_tools(),
        mcp_servers=build_mcp_servers(url="http://127.0.0.1:8011/mcp", user_token="tok", session_id="s1"),
        allowed_mcp_server_names=["fachuan"],
        strict_mcp_config=True,
        permission_mode="default",
        system_prompt=_system_prompt(ctx),
        include_partial_messages=True,
        can_use_tool=lambda *a: None,
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[])]},
    )
    args = SubprocessCLITransport(prompt="x", options=options).build_session_args()

    assert "--tools" in args
    assert args[args.index("--tools") + 1] == ""  # 空串 = 全关
    assert args[args.index("--permission-mode") + 1] == "default"
    assert args[args.index("--permission-prompt-tool") + 1] == "stdio"
    assert args[args.index("--setting-sources") + 1] == ""  # 不读用户/项目设置
    assert args[args.index("--disallowed-tools") + 1] == "mcp__fachuan__delete_case"
    assert args[args.index("--allowed-mcp-server-names") + 1] == "fachuan"
    assert "--strict-mcp-config" in args
    assert "--include-partial-messages" in args
    # 默认走 append（保留 qodercli preset 的工具纪律），不是 --system-prompt 全替换。
    assert "--append-system-prompt" in args
    assert "--system-prompt" not in args
    # 未开 allow_byok 时绝不能带 --model（把网关模型名送给 qoder 云必然 404）。
    assert "--model" not in args


# ── 7/8. 三道审批闸 ────────────────────────────────────────────────────


@_SDK
def test_pre_tool_use_forces_ask_for_high_risk() -> None:
    """高危工具必须由我们置 ``ask``——qoder 的分类器不能替律师放行。"""
    ctx = _ctx()
    hook_input = SimpleNamespace(tool_name="mcp__fachuan__delete_case", tool_input={"case_id": 1})
    out = asyncio.run(_pre_tool_use(ctx, hook_input))
    # 不可逆删除类走 deny（连审批卡都不弹）。
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    hook_input = SimpleNamespace(tool_name="mcp__fachuan__submit_court_filing", tool_input={})
    out = asyncio.run(_pre_tool_use(ctx, hook_input))
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"

    # 只读工具不干预（空 dict = 按 CLI 自己的规则走）。
    hook_input = SimpleNamespace(tool_name="mcp__fachuan__list_cases", tool_input={})
    assert asyncio.run(_pre_tool_use(ctx, hook_input)) == {}


@_SDK
def test_pre_tool_use_does_not_ask_when_approval_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """审批闸门关掉时不能再置 ``ask``：CLI 会等一个永远不来的回调，工具卡到超时。"""
    monkeypatch.setenv(APPROVAL_ENV, "off")
    hook_input = SimpleNamespace(tool_name="mcp__fachuan__submit_court_filing", tool_input={})
    assert asyncio.run(_pre_tool_use(_ctx(), hook_input)) == {}


@_SDK
def test_can_use_tool_denies_blocked_without_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """不可逆删除类连审批卡都不弹。"""
    from apps.agent.services import approval as approval_service

    called: list[Any] = []

    async def _never(**kwargs: Any) -> tuple[bool, int, str]:  # pragma: no cover - 不该被调用
        called.append(kwargs)
        return True, 1, ""

    monkeypatch.setattr(approval_service, "request_approval", _never)
    result = asyncio.run(_can_use_tool(_ctx(), "mcp__fachuan__delete_case", {}, SimpleNamespace(tool_use_id="t1")))
    assert getattr(result, "behavior", "") == "deny"
    assert called == []


@_SDK
def test_can_use_tool_asks_for_high_risk_and_reports_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    """高危工具走现有审批链，且会话 / 轮次 / 用户 / 工具卡 id 全部来自本轮 ctx。"""
    from apps.agent.services import approval as approval_service

    seen: dict[str, Any] = {}

    async def _deny(**kwargs: Any) -> tuple[bool, int, str]:
        seen.update(kwargs)
        return False, 42, "律师拒绝"

    monkeypatch.setattr(approval_service, "request_approval", _deny)
    ctx = _ctx(run_id="s1:qoder:3", user_id=11)
    result = asyncio.run(
        _can_use_tool(ctx, "mcp__fachuan__submit_court_filing", {"case_id": 9}, SimpleNamespace(tool_use_id="t9"))
    )
    assert getattr(result, "behavior", "") == "deny"
    assert getattr(result, "message", "") == APPROVAL_REJECTED_MESSAGE
    assert seen["session_id"] == "s1"
    assert seen["run_id"] == "s1:qoder:3"
    assert seen["user_id"] == 11
    assert seen["tool_call_id"] == "t9"
    assert seen["tool_name"] == "mcp__fachuan__submit_court_filing"


@_SDK
def test_can_use_tool_allows_low_risk(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.agent.services import approval as approval_service

    async def _never(**kwargs: Any) -> tuple[bool, int, str]:  # pragma: no cover - 不该被调用
        raise AssertionError("低危工具不该走审批")

    monkeypatch.setattr(approval_service, "request_approval", _never)
    result = asyncio.run(_can_use_tool(_ctx(), "mcp__fachuan__list_cases", {}, SimpleNamespace(tool_use_id="t1")))
    assert getattr(result, "behavior", "") == "allow"


# ── 9. 事件翻译 ────────────────────────────────────────────────────────


def test_text_delta_becomes_delta() -> None:
    state = _RunState()
    frames = QoderBackend._translate_stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "你好"}}, state
    )
    assert frames == [{"type": "delta", "content": "你好"}]
    assert state.saw_stream_text is True


def test_thinking_delta_in_text_block_is_dropped() -> None:
    """网关部分路由把 ``thinking_delta`` 塞进 text 块（协议违例）——转了会把思考当正文。"""
    state = _RunState()
    state.blocks[0] = {"type": "text", "name": "", "id": "", "json": ""}
    frames = QoderBackend._translate_stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "想"}}, state
    )
    assert frames == []


def test_thinking_delta_in_thinking_block_becomes_thinking() -> None:
    state = _RunState()
    state.blocks[0] = {"type": "thinking", "name": "", "id": "", "json": ""}
    frames = QoderBackend._translate_stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "想"}}, state
    )
    assert frames == [{"type": "thinking", "content": "想"}]


def test_tool_use_emitted_only_after_json_is_complete() -> None:
    """``tool_use`` 只在 ``content_block_stop`` 发出——之前 JSON 还没拼完。"""
    state = _RunState()
    QoderBackend._translate_stream_event(
        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "t1", "name": "x"}},
        state,
    )
    assert (
        QoderBackend._translate_stream_event(
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"a"'}},
            state,
        )
        == []
    )
    QoderBackend._translate_stream_event(
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": ":1}"}},
        state,
    )
    frames = QoderBackend._translate_stream_event({"type": "content_block_stop", "index": 1}, state)
    assert frames == [{"type": "tool_call", "tool_call_id": "t1", "name": "x", "arguments": '{"a":1}'}]
    assert state.tool_names["t1"] == "x"


def test_usage_accumulates_across_events() -> None:
    state = _RunState()
    QoderBackend._translate_stream_event(
        {"type": "message_start", "message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": 4}}}, state
    )
    QoderBackend._translate_stream_event({"type": "message_delta", "usage": {"output_tokens": 7}}, state)
    assert (state.input_tokens, state.output_tokens, state.cache_read_tokens) == (10, 7, 4)
    assert state.reported_usage is True


@_SDK
def test_assistant_fallback_is_off_once_streaming_worked() -> None:
    """流式通时 ``AssistantMessage`` 的兜底必须关掉，否则同一段正文出现两遍。"""
    from qoder_agent_sdk import AssistantMessage, TextBlock

    backend = QoderBackend()
    ctx = _ctx()
    backend._states[ctx.run_id] = _RunState(saw_stream_text=True)
    msg = AssistantMessage(content=[TextBlock(text="整段")], model="qoder-pro")
    assert backend._translate(msg, ctx.run_id) == []


@_SDK
def test_assistant_fallback_emits_text_when_streaming_is_silent() -> None:
    """流式不通时每轮都要发——工具循环里第 2、3 轮才有正文。"""
    from qoder_agent_sdk import AssistantMessage, TextBlock

    backend = QoderBackend()
    ctx = _ctx()
    state = _RunState()
    backend._states[ctx.run_id] = state
    msg = AssistantMessage(content=[TextBlock(text="整段")], model="qoder-pro")
    assert backend._translate(msg, ctx.run_id) == [{"type": "delta", "content": "整段"}]
    assert state.model == "qoder-pro"


@_SDK
def test_tool_result_translated() -> None:
    from qoder_agent_sdk import ToolResultBlock, UserMessage

    backend = QoderBackend()
    ctx = _ctx()
    state = _RunState(tool_names={"t1": "mcp__fachuan__list_cases"})
    backend._states[ctx.run_id] = state
    msg = UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="[1,2,3]", is_error=False)])
    assert backend._translate(msg, ctx.run_id) == [
        {
            "type": "tool_result",
            "tool_call_id": "t1",
            "name": "mcp__fachuan__list_cases",
            "result": "[1,2,3]",
            "is_error": False,
        }
    ]


# ── 10. tick ───────────────────────────────────────────────────────────


def test_with_ticks_yields_none_while_silent() -> None:
    """SDK 静默期必须 ``yield None``：编排层只在后端 yield 时排空审批事件总线。"""

    async def _scenario() -> list[Any]:
        async def _slow() -> AsyncIterator[str]:
            await asyncio.sleep(0.25)
            yield "msg"

        out = []
        async for item in with_ticks(_slow()):
            out.append(item)
        return out

    out = asyncio.run(_scenario())
    assert out[-1] == "msg"
    assert None in out[:-1]


# ── 11. 错误分类 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expect"),
    [
        ("request failed with code 105", "105"),
        ("quota exhausted (113)", "113"),
        ("input too long: 80411", "80411"),
        ("no known code here", None),
        ("", None),
    ],
)
def test_error_code_extraction(text: str, expect: str | None) -> None:
    assert _error_code(text) == expect


def test_every_error_code_maps_to_a_message() -> None:
    for code, (kind, message, retryable) in ERROR_CODES.items():
        assert isinstance(kind, BackendErrorKind)
        assert message
        # AUTH / CONTEXT_OVERFLOW 标成可重试会让编排层白白重放，用户等更久、账单更高。
        if kind in (BackendErrorKind.AUTH, BackendErrorKind.CONTEXT_OVERFLOW):
            assert retryable is False, code


@_SDK
def test_result_failure_maps_known_codes() -> None:
    from qoder_agent_sdk import ResultMessage

    def _result(**over: Any) -> Any:
        base: dict[str, Any] = {
            "subtype": "error_during_execution",
            "duration_ms": 1,
            "duration_api_ms": 1,
            "is_error": True,
            "num_turns": 1,
            "session_id": "s1",
        }
        base.update(over)
        return ResultMessage(**base)

    error = QoderBackend._result_failure(_result(errors=["login expired: code 105"]), max_turns=24)
    assert isinstance(error, BackendError)
    assert error.kind is BackendErrorKind.AUTH
    assert error.retryable is False

    error = QoderBackend._result_failure(_result(errors=["input too long: 80411"]), max_turns=24)
    assert error is not None
    assert error.kind is BackendErrorKind.CONTEXT_OVERFLOW

    error = QoderBackend._result_failure(_result(errors=["internal error 500"]), max_turns=24)
    assert error is not None
    assert (error.kind, error.retryable) == (BackendErrorKind.UNAVAILABLE, True)

    # 成功结果不是错误。
    assert QoderBackend._result_failure(_result(subtype="success", is_error=False), max_turns=24) is None


@_SDK
def test_result_failure_max_turns_is_readable() -> None:
    from qoder_agent_sdk import ResultMessage

    msg = ResultMessage(
        subtype="error_max_turns",
        duration_ms=1,
        duration_api_ms=1,
        is_error=True,
        num_turns=24,
        session_id="s1",
    )
    error = QoderBackend._result_failure(msg, max_turns=24)
    assert error is not None
    assert "24" in str(error)


@_SDK
def test_usage_frame_prefers_result_then_state() -> None:
    from qoder_agent_sdk import ResultMessage

    msg = ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s1",
        usage={"input_tokens": 12, "output_tokens": 34, "cache_read_input_tokens": 5, "cache_creation_input_tokens": 6},
    )
    assert QoderBackend._usage_frame(msg, _RunState()) == {
        "type": "usage",
        "input_tokens": 12,
        "output_tokens": 34,
        "cache_read_tokens": 5,
        "cache_write_tokens": 6,
    }

    # 结果里没有用量时退回流事件累加值。
    state = _RunState(input_tokens=3, output_tokens=4, reported_usage=True)
    bare = ResultMessage(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s1"
    )
    assert QoderBackend._usage_frame(bare, state) == {
        "type": "usage",
        "input_tokens": 3,
        "output_tokens": 4,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }

    # 两边都拿不到 → 不发 0/0 假帧（编造的 0 无法与真实 0 区分）。
    assert QoderBackend._usage_frame(bare, _RunState()) is None


# ── 12. system prompt 与收尾事实 ───────────────────────────────────────


def test_system_prompt_appends_by_default() -> None:
    """默认**追加**到 qodercli preset，而不是全替换（全替换可能连工具纪律一起删掉）。"""
    prompt = _system_prompt(_ctx())
    assert prompt == {"type": "preset", "preset": "qodercli", "append": DEFAULT_INSTRUCTIONS}


def test_system_prompt_full_replace_when_given() -> None:
    """``ctx.system_prompt`` 的语义是**全量替换**（综合结论的规则只靠它下发）。"""
    assert _system_prompt(_ctx(system_prompt="只输出结论")) == "只输出结论"


def test_result_store_is_bounded() -> None:
    backend = QoderBackend()
    for index in range(MAX_KEPT_RESULTS + 5):
        backend._remember_result(f"run-{index}", QoderRunResult(model="qoder-pro"))
    assert backend.result_for("run-0") is None
    assert backend.result_for(f"run-{MAX_KEPT_RESULTS + 4}") is not None
    assert len(backend._results) == MAX_KEPT_RESULTS


# ── patch 级护栏：SDK 在 mcp 2.x 上的导入面 ────────────────────────────


@_SDK
def test_sdk_import_surface() -> None:
    """``qoder-agent-sdk`` 要 ``mcp<2``，本仓库强制 ``mcp[cli]>=2.2.0``。

    ``pyproject.toml`` 的 ``override-dependencies`` 是这个覆盖的唯一凭据，而它的
    安全性完全取决于「qoder 用到的 mcp 符号在新版里还在」。这条测试就是那句话的
    可执行版本：mcp 升到删掉这些名字的版本时，这里当场红。
    """
    # qoder 的模块级导入（缺一个它连 import 都过不去）。
    from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest, ToolAnnotations

    assert ToolAnnotations is not None
    assert CallToolRequest and CallToolRequestParams and ListToolsRequest

    # 本后端真正用到的 SDK 符号（改名/删除会在这里先红，而不是等真机跑对话）。
    from qoder_agent_sdk import (
        AssistantMessage,
        HookMatcher,
        PermissionResultAllow,
        PermissionResultDeny,
        QoderAgentOptions,
        QoderSDKClient,
        ResultMessage,
        StreamEvent,
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        access_token,
        qodercli_auth,
        service_account,
    )

    # 关键选项字段名（SDK 改字段我们会静默传不进去，所以按名字钉住）。
    fields = set(QoderAgentOptions.__dataclass_fields__)
    for name in (
        "allowed_tools",
        "allowed_mcp_server_names",
        "can_use_tool",
        "cli_path",
        "cwd",
        "disallowed_tools",
        "env",
        "hooks",
        "include_partial_messages",
        "max_turns",
        "mcp_servers",
        "model",
        "permission_mode",
        "proxy",
        "resolve_model",
        "setting_sources",
        "skills",
        "strict_mcp_config",
        "system_prompt",
        "tools",
    ):
        assert name in fields, f"QoderAgentOptions 缺字段 {name}"
