"""``AntigravityBackend`` —— 第四个 agent 后端的接缝、事件翻译、审批闸门与网关补丁。

全部离线（不打真网关、不连共享 MCP、不起 Go 进程）：

1. **身份与能力声明**：``kind == "antigravity"``，六项能力如实。声明错了前端会
   渲染出不存在的控件（插话框 / 审批卡），而用户敲进去的话会被丢弃。
2. **结构化满足协议**：``isinstance(AntigravityBackend(), AgentBackend)``。
3. **事件翻译**：``Text`` / ``Thought`` 增量 → ``delta`` / ``thinking``；
   工具事件**只走钩子**（``chunks`` 里没有，且两处 ``id`` 不同源，见模块 docstring）。
4. **工具名解包**：eager 原生工具与惰性 ``call_mcp_tool`` 两种形状都要解出**真实**
   工具名与入参——不解包，审批分级只看得到壳名，闸门会静默失效。
5. **审批闸门**：HIGH/CRITICAL 走 ``request_approval``；拒绝 → ``allow=False`` +
   一条 ``is_error`` 的 ``tool_result``；LOW 直过；开关 ``off`` 时不问审批且能力
   声明同步为 False。
6. **网关解析**：模型必须来自库（``LLMProvider``），``RunContext.api_key`` 有值就
   不再轮转（四栏并答靠它避免撞 key）。
7. **loopback 代理**：注册/注销、未知 token 401、``tool_choice`` 归一（vLLM 400 的
   真实复现）、路径拼接不重复 ``/v1``。
8. **注册**：``ensure_registered()`` 后 ``antigravity`` 在注册表里；SDK 缺失时
   静默降级、不抛。

``antigravity_backend`` 顶层 ``import google.antigravity``，所以本文件用
``pytest.importorskip`` 兜住「SDK 没装」的环境——那时跳过的是 import 层面的用例，
而不是把它们改成假绿。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

pytest.importorskip("google.antigravity", reason="google-antigravity SDK 未安装，跳过 antigravity 后端用例")

from google.antigravity import types

from apps.agent.backends import AgentBackend, BackendError, BackendErrorKind, RunContext
from apps.agent.backends import antigravity_backend as backend_module
from apps.agent.backends import builtin as builtin_module
from apps.agent.backends import gateway_cache, registry
from apps.agent.backends.antigravity_backend import (
    APPROVAL_ENV,
    APPROVAL_REJECTED_MESSAGE,
    BLOCKED_TOOL_NAMES,
    AntigravityBackend,
    _EventSink,
    _RunSlots,
    _ToolDecideHook,
    _ToolResultHook,
    _usage_frame,
    agent_home,
    approval_enabled,
    backend_capabilities,
    max_runs,
    tool_identity,
    tool_tier,
)
from apps.agent.backends.antigravity_gateway import (
    ROUTE_PREFIX,
    GatewayLease,
    LoopbackGateway,
    get_loopback_gateway,
    normalize_request_body,
    reset_loopback_gateway,
)
from apps.agent.services import approval as approval_service
from apps.core.llm.gateway_profile import GATEWAY_EFFORTS


class _Session:
    session_id = "sess-ag"


def _ctx(
    run_id: str = "sess-ag:antigravity:1",
    *,
    model: str | None = None,
    token: str = "tok",
    user_id: int | None = None,
) -> RunContext:
    return RunContext(
        run_id=run_id,
        session=_Session(),
        user_id=user_id,
        prompt="你好",
        user_token=token,
        model=model,
        tool_selection=None,
    )


def _settings(**overrides: Any) -> Any:
    """网关配置快照桩（``GatewaySettings`` 的形状）。"""
    fields: dict[str, Any] = {
        "name": "律所 kimi",
        "base_url": "http://gw.internal:4000/v1",
        "api_keys": ("sk-test-1", "sk-test-2"),  # pragma: allowlist secret
        "models": ("kimi-2.6",),
        "default_model": "kimi-2.6",
        "enable_thinking": False,
    }
    fields.update(overrides)
    return gateway_cache.GatewaySettings(**fields)


# ── 1. 身份与能力 ────────────────────────────────────────────────────────


class TestIdentity:
    def test_kind_is_antigravity(self) -> None:
        assert AntigravityBackend().kind == "antigravity"

    def test_capabilities_are_fact_statements(self) -> None:
        caps = AntigravityBackend().capabilities
        assert caps.streaming is True  # Text/Thought 是真增量
        assert caps.tool_calls is True  # 钩子产出 tool_call/tool_result
        assert caps.approval is approval_enabled()
        assert caps.compaction is False  # 不配 CompactionConfig，上下文归编排层
        assert caps.steer is False  # SDK 只有 cancel，没有插话接口
        assert caps.concurrent_in_session is True  # 每轮自建 Agent + 独立进程

    def test_satisfies_agent_backend_protocol(self) -> None:
        assert isinstance(AntigravityBackend(), AgentBackend)

    def test_results_are_keyed_by_run_id(self) -> None:
        backend = AntigravityBackend()
        backend._results["run-a"] = backend_module.AntigravityRunResult(model="kimi-2.6")
        assert backend.result_for("run-a").model == "kimi-2.6"  # type: ignore[union-attr]
        assert backend.result_for("run-b") is None

    def test_approval_env_off_flips_capability(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(APPROVAL_ENV, "off")
        assert approval_enabled() is False
        assert backend_capabilities().approval is False
        assert AntigravityBackend().capabilities.approval is False

    def test_tool_tier_defaults_to_lite(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(backend_module.TOOL_TIER_ENV, raising=False)
        assert tool_tier() == "lite"
        monkeypatch.setenv(backend_module.TOOL_TIER_ENV, "FULL")
        assert tool_tier() == "full"
        monkeypatch.setenv(backend_module.TOOL_TIER_ENV, "whatever")
        assert tool_tier() == "lite"

    def test_max_runs_falls_back_on_garbage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(backend_module.MAX_RUNS_ENV, "abc")
        assert max_runs() == backend_module.DEFAULT_MAX_RUNS
        monkeypatch.setenv(backend_module.MAX_RUNS_ENV, "0")
        assert max_runs() == 1  # 下限 1：0 会让 acquire 永远等不到

    def test_agent_home_follows_fachuan_agent_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_HOME", str(tmp_path))
        assert agent_home() == tmp_path / "antigravity"


# ── 2. 事件翻译 ──────────────────────────────────────────────────────────


class TestTranslateChunk:
    def test_text_becomes_delta(self) -> None:
        assert AntigravityBackend._translate_chunk(types.Text(step_index=0, text="你好")) == [
            {"type": "delta", "content": "你好"}
        ]

    def test_thought_becomes_thinking(self) -> None:
        assert AntigravityBackend._translate_chunk(types.Thought(step_index=0, text="想")) == [
            {"type": "thinking", "content": "想"}
        ]

    def test_empty_text_produces_nothing(self) -> None:
        assert AntigravityBackend._translate_chunk(types.Text(step_index=0, text="")) == []

    def test_usage_maps_cache_and_thoughts(self) -> None:
        usage = types.UsageMetadata(
            prompt_token_count=100,
            cached_content_token_count=40,
            candidates_token_count=10,
            thoughts_token_count=5,
        )
        assert _usage_frame(usage) == {
            "type": "usage",
            "input_tokens": 60,  # prompt 含 cached，单列出去
            "output_tokens": 15,  # 思考也计费
            "cache_read_tokens": 40,
            "cache_write_tokens": 0,
        }

    def test_usage_never_goes_negative(self) -> None:
        usage = types.UsageMetadata(prompt_token_count=10, cached_content_token_count=99)
        assert _usage_frame(usage)["input_tokens"] == 0


# ── 3. 工具名解包 ────────────────────────────────────────────────────────


class TestToolIdentity:
    def test_eager_native_tool_keeps_short_name(self) -> None:
        short, args, full = tool_identity("list_cases", "fachuan", {"limit": 3})
        assert short == "list_cases"
        assert args == {"limit": 3}
        assert full == "mcp__fachuan__list_cases"

    def test_lazy_channel_unwraps_real_tool(self) -> None:
        short, args, full = tool_identity(
            "call_mcp_tool",
            "fachuan",
            {"ToolName": "delete_case", "Arguments": {"id": 7}, "ServerName": "fachuan"},
        )
        assert short == "delete_case"
        assert args == {"id": 7}
        assert full == "mcp__fachuan__delete_case"

    def test_lazy_channel_without_name_falls_back(self) -> None:
        short, _args, full = tool_identity("call_mcp_tool", "fachuan", {})
        assert short == "call_mcp_tool"
        assert full == "mcp__fachuan__call_mcp_tool"

    def test_missing_server_defaults_to_fachuan(self) -> None:
        _short, _args, full = tool_identity("list_cases", None, {})
        assert full == "mcp__fachuan__list_cases"


# ── 4. 审批闸门 ──────────────────────────────────────────────────────────


def _decide_hook(ctx: RunContext) -> tuple[_ToolDecideHook, _EventSink]:
    sink = _EventSink(ctx, "antigravity")
    return _ToolDecideHook(sink, ctx), sink


def _tool_call(name: str, args: dict[str, Any] | None = None, call_id: str = "call-1") -> types.ToolCall:
    return types.ToolCall(name=name, args=args or {}, id=call_id, server_name="fachuan")


class TestApprovalGate:
    @pytest.mark.asyncio
    async def test_low_risk_tool_passes_without_asking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        asked: list[str] = []

        async def fake_request(**kwargs: Any) -> Any:  # pragma: no cover - 不该被调用
            asked.append(kwargs["tool_name"])
            return True, "ap", ""

        monkeypatch.setattr(approval_service, "request_approval", fake_request)
        hook, sink = _decide_hook(_ctx())
        result = await hook.run(hook_types_ctx(), _tool_call("list_cases", {"limit": 1}))
        assert result.allow is True
        assert asked == []
        frames = sink.drain_nowait()
        assert [f["type"] for f in frames] == ["tool_call"]
        assert frames[0]["name"] == "list_cases"
        assert frames[0]["agent"] == "antigravity"

    @pytest.mark.asyncio
    async def test_high_risk_denied_blocks_tool_and_reports_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_request(**kwargs: Any) -> Any:
            return False, "ap-1", "律师拒绝"

        monkeypatch.setattr(approval_service, "request_approval", fake_request)
        hook, sink = _decide_hook(_ctx(user_id=7))
        result = await hook.run(hook_types_ctx(), _tool_call("delete_case", {"case_id": 9}))
        assert result.allow is False
        assert result.message == APPROVAL_REJECTED_MESSAGE
        frames = sink.drain_nowait()
        assert [f["type"] for f in frames] == ["tool_call", "tool_result"]
        assert frames[1]["is_error"] is True
        assert frames[1]["result"] == APPROVAL_REJECTED_MESSAGE
        assert "call-1" in hook.denied

    @pytest.mark.asyncio
    async def test_high_risk_approved_allows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_request(**kwargs: Any) -> Any:
            return True, "ap-2", ""

        monkeypatch.setattr(approval_service, "request_approval", fake_request)
        hook, sink = _decide_hook(_ctx(user_id=7))
        result = await hook.run(hook_types_ctx(), _tool_call("delete_case", {"case_id": 9}))
        assert result.allow is True
        assert [f["type"] for f in sink.drain_nowait()] == ["tool_call"]

    @pytest.mark.asyncio
    async def test_approval_off_never_asks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(APPROVAL_ENV, "off")

        async def fake_request(**kwargs: Any) -> Any:  # pragma: no cover - 不该被调用
            raise AssertionError("审批关闭时不应发起审批")

        monkeypatch.setattr(approval_service, "request_approval", fake_request)
        hook, _sink = _decide_hook(_ctx())
        result = await hook.run(hook_types_ctx(), _tool_call("delete_case", {"case_id": 9}))
        assert result.allow is True

    @pytest.mark.asyncio
    async def test_post_hook_skips_denied_calls(self) -> None:
        ctx = _ctx()
        sink = _EventSink(ctx, "antigravity")
        decide = _ToolDecideHook(sink, ctx)
        decide.denied.add("call-1")
        post = _ToolResultHook(sink, decide)
        await post.run(hook_types_ctx(), types.ToolResult(name="delete_case", id="call-1", result="x"))
        assert sink.drain_nowait() == []
        assert decide.denied == set()

    @pytest.mark.asyncio
    async def test_post_hook_flags_errors(self) -> None:
        ctx = _ctx()
        sink = _EventSink(ctx, "antigravity")
        decide = _ToolDecideHook(sink, ctx)
        post = _ToolResultHook(sink, decide)
        await post.run(
            hook_types_ctx(),
            types.ToolResult(name="list_cases", id="call-2", result=None, error="boom"),
        )
        frames = sink.drain_nowait()
        assert frames[0]["type"] == "tool_result"
        assert frames[0]["is_error"] is True
        assert frames[0]["result"] == "boom"


def hook_types_ctx() -> Any:
    """钩子上下文桩（钩子只把它透传，不读任何字段）。"""
    from google.antigravity.hooks import hooks as hook_types

    return hook_types.OperationContext(hook_types.TurnContext(hook_types.SessionContext()))


# ── 5. 事件合流（tick 让位） ─────────────────────────────────────────────


class TestMerge:
    @pytest.mark.asyncio
    async def test_idle_tick_yields_none(self) -> None:
        """SDK 静默期必须 ``yield None``：编排层只在后端 yield 时排空审批总线。"""
        ctx = _ctx()
        sink = _EventSink(ctx, "antigravity")
        chat_task = asyncio.ensure_future(asyncio.sleep(0.4))
        frames = []
        async for frame in AntigravityBackend()._merge(chat_task, sink):
            frames.append(frame)
            if len(frames) >= 2:
                break
        await chat_task
        assert frames[0] is None

    @pytest.mark.asyncio
    async def test_queued_frames_are_flushed_before_exit(self) -> None:
        ctx = _ctx()
        sink = _EventSink(ctx, "antigravity")
        chat_task = asyncio.ensure_future(asyncio.sleep(0))
        sink.push({"type": "tool_call", "tool_call_id": "c", "name": "x", "arguments": None})
        frames = [f async for f in AntigravityBackend()._merge(chat_task, sink)]
        assert [f["type"] for f in frames if f is not None] == ["tool_call"]


# ── 6. 网关解析（与 openai-agents 共用同一个解析器） ──────────────────────


class TestGatewayResolution:
    def test_model_comes_from_database(self) -> None:
        target = gateway_cache.resolve_gateway_target(_settings(default_model="glm53"), None)
        assert target is not None
        assert target.model == "glm53"
        assert target.base_url == "http://gw.internal:4000/v1"

    def test_model_hint_wins(self) -> None:
        target = gateway_cache.resolve_gateway_target(_settings(), "kimi-2.6")
        assert target is not None
        assert target.model == "kimi-2.6"

    def test_explicit_api_key_is_not_rotated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: Any, **_k: Any) -> str:  # pragma: no cover - 不该被调用
            raise AssertionError("编排层指定了 key 就不该轮转")

        monkeypatch.setattr("apps.agent.pi.model_config._next_key", boom)
        target = gateway_cache.resolve_gateway_target(_settings(), None, api_key="sk-pinned")  # pragma: allowlist secret
        assert target is not None
        assert target.api_key == "sk-pinned"  # pragma: allowlist secret

    def test_missing_base_url_is_unavailable(self) -> None:
        assert gateway_cache.resolve_gateway_target(_settings(base_url=""), None) is None

    def test_missing_keys_is_unavailable(self) -> None:
        assert gateway_cache.resolve_gateway_target(_settings(api_keys=()), None) is None

    def test_no_model_at_all_is_unavailable(self) -> None:
        assert gateway_cache.resolve_gateway_target(_settings(models=(), default_model=""), None) is None

    def test_thinking_extra_follows_platform_switch(self) -> None:
        """平台开关 + 模型能力共同决定；非推理模型一律不注入（网关会 400）。

        字段形状与档位均来自 ``apps.core.llm.gateway_profile.wire_fields``——
        本模块不再自己拼字面量（两份拼法必然分叉，见 ``gateway_profile`` 的
        模块 docstring）。
        """
        extra = backend_module.thinking_extra(_settings(enable_thinking=True), "kimi-2.6")
        assert extra == {"chat_template_kwargs": {"thinking": True}, "reasoning_effort": "max"}
        # ``kimi-k2`` 命中宽匹配 "kimi"：正是服务通道（只认 "kimi26"）曾判反的那个模型
        wide = backend_module.thinking_extra(_settings(enable_thinking=True), "kimi-k2")
        assert wide["chat_template_kwargs"] == {"thinking": True}
        assert wide["reasoning_effort"] in GATEWAY_EFFORTS
        assert backend_module.thinking_extra(_settings(enable_thinking=False), "kimi-2.6") == {}
        # glm53 不在推理模型特征表里 → 不注入
        assert backend_module.thinking_extra(_settings(enable_thinking=True), "glm53") == {}

    def test_target_repr_hides_key(self) -> None:
        target = gateway_cache.resolve_gateway_target(_settings(), None, api_key="sk-secret")
        assert target is not None
        assert "sk-secret" not in repr(target)


# ── 7. loopback 代理 ─────────────────────────────────────────────────────


class TestLoopbackGateway:
    def test_normalize_drops_tool_choice_without_tools(self) -> None:
        """实测 vLLM：``tool_choice`` 而没有 ``tools`` → 400（原文见函数 docstring）。"""
        body = json.dumps({"model": "m", "tool_choice": "auto", "tools": [], "messages": []}).encode()
        payload = json.loads(normalize_request_body(body))
        assert "tool_choice" not in payload
        assert payload["model"] == "m"

    def test_normalize_keeps_tool_choice_with_tools(self) -> None:
        body = json.dumps({"tool_choice": "auto", "tools": [{"type": "function"}]}).encode()
        assert json.loads(normalize_request_body(body))["tool_choice"] == "auto"

    def test_normalize_injects_thinking_fields(self) -> None:
        """思考参数只能由代理补：harness 的 OpenAI 通道不发这两个字段。

        网关（LiteLLM → vLLM）要 ``chat_template_kwargs.thinking`` +
        ``reasoning_effort`` 才开思考；不补的症状是**静默变浅**（不报错、
        ``thoughts_token_count`` 恒 0），所以这条注入必须有用例守着。

        注入内容直接取 :func:`thinking_extra` 的产物（即
        ``gateway_profile.wire_fields``）：本模块与代理都不自己拼字面量，否则
        又是一份会分叉的权威。
        """
        extra = backend_module.thinking_extra(_settings(enable_thinking=True), "kimi-k2")
        body = json.dumps({"model": "m", "messages": []}).encode()
        payload = json.loads(normalize_request_body(body, extra))
        assert payload["chat_template_kwargs"] == {"thinking": True}
        assert payload["reasoning_effort"] in GATEWAY_EFFORTS

    def test_normalize_never_overrides_harness_values(self) -> None:
        """只补缺不覆盖：harness 将来自己带这些字段时，以它为准。

        两个字段都要验：代理补的是**缺**，不是「模型侧的选择」——把 ``thinking``
        或 ``reasoning_effort`` 强行改成平台默认值，等于绕过 harness 自己的决定。
        """
        extra = backend_module.thinking_extra(_settings(enable_thinking=True), "kimi-k2")
        body = json.dumps(
            {"model": "m", "reasoning_effort": "low", "chat_template_kwargs": {"thinking": False}}
        ).encode()
        payload = json.loads(normalize_request_body(body, extra))
        assert payload["reasoning_effort"] == "low"
        assert payload["chat_template_kwargs"] == {"thinking": False}

    def test_normalize_passes_through_non_json(self) -> None:
        raw = b"not json"
        assert normalize_request_body(raw) == raw
        assert normalize_request_body(b"") == b""

    @pytest.mark.asyncio
    async def test_register_returns_lease_and_route(self) -> None:
        gateway = LoopbackGateway()
        try:
            lease = await gateway.register(base_url="http://gw.internal:4000/v1", api_key="sk-1")  # pragma: allowlist secret
            assert isinstance(lease, GatewayLease)
            assert lease.base_url.startswith("http://127.0.0.1:")
            assert f"{ROUTE_PREFIX}{lease.token}/v1" in lease.base_url
            assert gateway.route_count() == 1
            gateway.unregister(lease.token)
            assert gateway.route_count() == 0
        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_register_rejects_missing_key(self) -> None:
        gateway = LoopbackGateway()
        with pytest.raises(ValueError):
            await gateway.register(base_url="http://gw.internal:4000/v1", api_key="")
        await gateway.stop()

    @pytest.mark.asyncio
    async def test_unknown_token_is_401_not_404(self) -> None:
        """未知 route 必须是 401：404 会被 harness 当成「端点不存在」直接放弃。"""
        import httpx

        gateway = LoopbackGateway()
        try:
            await gateway.ensure_started()
            async with httpx.AsyncClient(trust_env=False) as client:
                response = await client.post(
                    f"http://127.0.0.1:{gateway.port}/r/nope/v1/chat/completions", json={}
                )
            assert response.status_code == 401
            # 只断言状态码不算测过：401 的语义是"路由存在但 token 不认"，
            # 正文必须点明这一点（404 会静默，见 gateway 的注释）
            assert "unknown gateway route" in response.text
        finally:
            await gateway.stop()
            reset_loopback_gateway()

    def test_singleton_is_stable(self) -> None:
        try:
            assert get_loopback_gateway() is get_loopback_gateway()
        finally:
            reset_loopback_gateway()


# ── 8. 配置装配 ──────────────────────────────────────────────────────────


class TestBuildConfig:
    def _config(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        monkeypatch.setenv("FACHUAN_AGENT_HOME", str(agent_home().parent))
        monkeypatch.setattr(backend_module, "port_open", lambda *_a: True)
        monkeypatch.setattr(backend_module, "shared_enabled", lambda: True)
        backend = AntigravityBackend()
        ctx = _ctx()
        target = backend_module.ResolvedTarget(
            base_url="http://gw.internal:4000/v1",
            api_key="sk-1",  # pragma: allowlist secret
            model="kimi-2.6",
            thinking={},
        )
        servers = backend._mcp_servers(ctx)
        return backend._build_config(
            ctx, target, "http://127.0.0.1:1234/r/tok/v1", hooks=[], mcp_servers=servers
        )

    def test_builtin_tools_are_all_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        config = self._config(monkeypatch)
        assert config.capabilities.enabled_tools == []
        assert config.capabilities.enable_subagents is False

    def test_system_instructions_replace_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``str`` 只会追加一节，Antigravity 身份仍在——必须用 CustomSystemInstructions。"""
        config = self._config(monkeypatch)
        assert isinstance(config.system_instructions, types.CustomSystemInstructions)
        assert "律师助理" in config.system_instructions.text

    def test_mcp_server_is_eager_and_bears_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        config = self._config(monkeypatch)
        assert len(config.mcp_servers) == 1
        server = config.mcp_servers[0]
        assert server.force_all_tools_eager is True
        assert server.disabled_tools == list(BLOCKED_TOOL_NAMES)
        assert server.headers["Authorization"] == "Bearer tok"
        assert server.headers["x-fachuan-session"] == "sess-ag"
        assert server.headers["x-fachuan-tool-tier"] in {"lite", "full"}

    def test_no_policies_because_hooks_own_the_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SDK 默认的 ``confirm_run_command`` 只认内置 run_command，对 MCP 工具无效。"""
        assert self._config(monkeypatch).policies == []

    def test_env_strips_loopback_from_proxies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        config = self._config(monkeypatch)
        assert "127.0.0.1" in config.env["NO_PROXY"]

    def test_missing_token_means_no_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(backend_module, "port_open", lambda *_a: True)
        monkeypatch.setattr(backend_module, "shared_enabled", lambda: True)
        assert AntigravityBackend()._mcp_servers(_ctx(token="")) == []

    def test_dead_mcp_port_means_no_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(backend_module, "port_open", lambda *_a: False)
        monkeypatch.setattr(backend_module, "shared_enabled", lambda: True)
        assert AntigravityBackend()._mcp_servers(_ctx()) == []


# ── 9. 错误分类 ──────────────────────────────────────────────────────────


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("message", "kind", "retryable"),
        [
            ("401 unauthorized", BackendErrorKind.AUTH, False),
            ("429 rate limit exceeded", BackendErrorKind.RATE_LIMITED, True),
            ("context window overflow", BackendErrorKind.CONTEXT_OVERFLOW, False),
            ("something odd", BackendErrorKind.UNKNOWN, False),
        ],
    )
    def test_keyword_classification(self, message: str, kind: BackendErrorKind, retryable: bool) -> None:
        error = AntigravityBackend._wrap_error(RuntimeError(message))
        assert error.kind is kind
        assert error.retryable is retryable

    def test_connection_failure_is_unavailable(self) -> None:
        error = AntigravityBackend._wrap_error(ConnectionError("refused"))
        assert error.kind is BackendErrorKind.UNAVAILABLE
        assert error.retryable is True

    def test_backend_error_passes_through(self) -> None:
        original = BackendError(BackendErrorKind.AUTH, "nope")
        assert AntigravityBackend._wrap_error(original) is original

    def test_cancel_is_not_an_error(self) -> None:
        with pytest.raises(asyncio.CancelledError):
            AntigravityBackend._wrap_error(asyncio.CancelledError())


# ── 10. 执行位 ───────────────────────────────────────────────────────────


class TestRunSlots:
    @pytest.mark.asyncio
    async def test_reports_waiting_and_frees_the_slot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(backend_module.MAX_RUNS_ENV, "1")
        slots = _RunSlots()
        assert await slots.acquire() == (False, 1)
        try:
            waiter = asyncio.ensure_future(slots.acquire())
            await asyncio.sleep(0.01)
            assert not waiter.done()
            slots.release()
            assert await waiter == (True, 1)
        finally:
            slots.release()


# ── 11. 注册 ─────────────────────────────────────────────────────────────


class TestRegistration:
    def test_registered_after_ensure_registered(self) -> None:
        registry.clear()
        try:
            builtin_module.ensure_registered()
            assert "antigravity" in registry.available_kinds()
            assert isinstance(registry.get("antigravity"), AntigravityBackend)
        finally:
            registry.clear()

    def test_missing_sdk_degrades_silently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """缺 SDK 时只记一次、不抛：pi 会话不能因为可选后端缺依赖而跟着起不来。"""
        import builtins

        registry.clear()
        builtin_module._attempted.discard("antigravity")
        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name.endswith("antigravity_backend"):
                raise ImportError("simulated missing google-antigravity")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        try:
            builtin_module._register_antigravity()
            assert "antigravity" not in registry.available_kinds()
            assert "antigravity" in builtin_module._attempted
        finally:
            registry.clear()
            builtin_module._attempted.discard("antigravity")
