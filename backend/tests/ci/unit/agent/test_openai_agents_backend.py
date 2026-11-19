"""``OpenAiAgentsBackend`` —— openai-agents 后端的接缝、事件翻译与网关解析。

全部离线（不打真网关、不起共享 MCP）：

1. **身份与能力声明**：``kind == "openai-agents"``，六项能力如实。声明错了前端会
   渲染出不存在的控件（插话框 / 审批卡），而用户敲进去的话会被丢弃。
2. **结构化满足协议**：``isinstance(OpenAiAgentsBackend(), AgentBackend)``。
3. **事件翻译**：用 SDK 的真实事件对象（``ResponseTextDeltaEvent`` 等）喂
   ``_translate_stream_event``，断言产出符合 ``sse_types.py`` 契约。
4. **网关解析**：provider 桩 → ``(base_url, api_key, model)``，**模型必须来自库**，
   不许硬编码。
5. **代理剔除**：构造客户端的那一刻环境里不能有代理变量（内网网关会 502）。
6. **注册**：``ensure_registered()`` 后 ``openai-agents`` 在注册表里；SDK 缺失时
   静默降级、不抛。
7. **端到端**：跑 ``stream()``（SDK 的 ``Runner`` / ``AsyncOpenAI`` / MCP 全部打桩），
   断言事件序列、``done`` 收尾、``result_for`` 的模型回填。

``openai_agents_backend`` 顶层 ``import agents``，所以本文件用 ``pytest.importorskip``
兜住「SDK 没装」的 CI 环境——那时跳过的是 import 层面的用例，而不是把它们改成假绿。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("agents", reason="openai-agents SDK 未安装，跳过 openai-agents 后端用例")

from agents import Agent
from agents.items import MessageOutputItem, ToolCallItem, ToolCallOutputItem
from agents.stream_events import AgentUpdatedStreamEvent, RawResponsesStreamEvent, RunItemStreamEvent
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseTextDeltaEvent,
)

from apps.agent.backends import (
    AgentBackend,
    BackendCapabilities,
    BackendError,
    BackendErrorKind,
    RunContext,
    gateway_cache,
    mcp_session_pool,
)
from apps.agent.backends import openai_agents_backend as backend_module
from apps.agent.backends import registry as registry_module
from apps.agent.backends.dsh_config import proxy_env_keys, without_proxy_env
from apps.agent.backends.openai_agents_backend import (
    BLOCKED_TOOL_NAMES,
    MAX_TURNS,
    OpenAiAgentsBackend,
    gateway_from_provider,
    resolve_gateway,
)


class _Session:
    session_id = "sess-1"


def _ctx(run_id: str = "sess-1:openai-agents:1", *, model: str | None = None, token: str = "tok") -> RunContext:
    return RunContext(
        run_id=run_id,
        session=_Session(),
        user_id=None,
        prompt="你好",
        user_token=token,
        model=model,
        tool_selection=None,
    )


def _provider(**overrides: Any) -> Any:
    """足以映射出网关配置的 provider 桩（形状照 ``LLMProvider``）。"""

    class _P:
        base_url = "http://gw.internal:4000/v1"
        api_keys = "sk-test"  # pragma: allowlist secret
        default_model = "kimi-2.6"
        extra_models = ""

    provider = _P()
    for key, value in overrides.items():
        setattr(provider, key, value)
    return provider


def _settings(**overrides: Any) -> Any:
    """网关配置快照桩（``GatewaySettings`` 的形状）。"""
    fields: dict[str, Any] = {
        "base_url": "http://gw.internal:4000/v1",
        "api_keys": ("sk-test",),  # pragma: allowlist secret
        "models": ("kimi-2.6",),
        "default_model": "kimi-2.6",
        "enable_thinking": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _text_delta(text: str) -> RawResponsesStreamEvent:
    """SDK 的正文增量事件（字段与真实 ``ResponseTextDeltaEvent`` 一致）。"""
    return RawResponsesStreamEvent(
        data=ResponseTextDeltaEvent(
            content_index=0,
            delta=text,
            item_id="msg_1",
            logprobs=[],
            output_index=0,
            sequence_number=1,
            type="response.output_text.delta",
        )
    )


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    """注册表是模块级全局状态；串用例会出假绿。"""
    registry_module.clear()
    yield
    registry_module.clear()


class TestIdentity:
    def test_kind_is_openai_agents(self) -> None:
        assert OpenAiAgentsBackend.kind == "openai-agents"

    def test_capabilities_are_fact_statements(self) -> None:
        """逐项对齐规格 §3.2 与 SDK 事实。

        ``steer=False``：``RunResultStreaming`` 只有 ``cancel``，没有插话接口。
        ``approval=False``：SDK 有 ``require_approval``，但本轮不接（规格明示）。
        ``concurrent_in_session=True``：每次 ``stream()`` 自建 client / agent / 连接。
        """
        caps = OpenAiAgentsBackend.capabilities
        assert isinstance(caps, BackendCapabilities)
        assert caps.streaming is True
        assert caps.tool_calls is True
        assert caps.approval is False
        assert caps.compaction is False
        assert caps.steer is False
        assert caps.concurrent_in_session is True

    def test_satisfies_agent_backend_protocol(self) -> None:
        """``runtime_checkable`` 协议：不继承也要能过 isinstance。"""
        assert isinstance(OpenAiAgentsBackend(), AgentBackend)

    def test_results_are_keyed_by_run_id(self) -> None:
        """收尾事实按 ``run_id`` 归集：注册表里是单例，单值属性会在并发会话间串号。"""
        backend = OpenAiAgentsBackend()
        backend._results["a"] = backend_module.OpenAiAgentsRunResult(model="m1")
        backend._results["b"] = backend_module.OpenAiAgentsRunResult(model="m2")
        assert backend.result_for("a") == backend_module.OpenAiAgentsRunResult(model="m1")
        assert backend.result_for("missing") is None


class TestEventTranslation:
    """用真实 SDK 事件对象断言翻译结果（不经过网络）。"""

    def _frames(self, event: Any) -> list[dict[str, Any]]:
        return OpenAiAgentsBackend()._translate_stream_event(event)

    def test_text_delta_becomes_delta(self) -> None:
        assert self._frames(_text_delta("答")) == [{"type": "delta", "content": "答"}]

    def test_empty_text_delta_produces_nothing(self) -> None:
        # 空增量下发会让前端多出无意义的渲染 tick，且难以与「模型卡住」区分。
        assert self._frames(_text_delta("")) == []

    def test_reasoning_text_delta_becomes_thinking(self) -> None:
        event = RawResponsesStreamEvent(
            data=ResponseReasoningTextDeltaEvent(
                content_index=0,
                delta="先查案件",
                item_id="rs_1",
                output_index=0,
                sequence_number=2,
                type="response.reasoning_text.delta",
            )
        )
        assert self._frames(event) == [{"type": "thinking", "content": "先查案件"}]

    def test_reasoning_summary_delta_becomes_thinking(self) -> None:
        """网关返回摘要而不是原文时，律师仍应看到「思考中」的内容。"""
        event = RawResponsesStreamEvent(
            data=ResponseReasoningSummaryTextDeltaEvent(
                delta="检索法条",
                item_id="rs_1",
                output_index=0,
                sequence_number=3,
                summary_index=0,
                type="response.reasoning_summary_text.delta",
            )
        )
        assert self._frames(event) == [{"type": "thinking", "content": "检索法条"}]

    def test_unrelated_raw_event_is_dropped(self) -> None:
        """生命周期事件（``response.created`` 之类）不透传：每轮几十条纯噪音。"""
        lifecycle = SimpleNamespace(type="response.created")
        assert self._frames(RawResponsesStreamEvent(data=cast(Any, lifecycle))) == []

    def test_agent_updated_event_is_dropped(self) -> None:
        """本后端不配 handoff；``agent_updated`` 出现了也没有用户可见语义。"""
        event = AgentUpdatedStreamEvent(new_agent=Agent(name="other"))
        assert self._frames(event) == []

    def test_tool_called_becomes_tool_call(self) -> None:
        agent = Agent(name="t")
        raw = ResponseFunctionToolCall(
            arguments='{"query":"合同"}',
            call_id="call_1",
            name="mcp__fachuan__search_case",
            type="function_call",
        )
        item = ToolCallItem(agent=agent, raw_item=raw)
        frames = self._frames(RunItemStreamEvent(name="tool_called", item=item))
        assert frames == [
            {
                "type": "tool_call",
                "tool_call_id": "call_1",
                "name": "mcp__fachuan__search_case",
                "arguments": '{"query":"合同"}',
            }
        ]

    def test_tool_output_becomes_tool_result(self) -> None:
        """工具名由前面的 ``tool_called`` 按 call_id 配对补上。

        SDK 的 ``ToolCallOutputItem.raw_item`` 是 ``function_call_output``，**没有**
        name 字段（实测），不配对就只剩空串，前端只能显示一个匿名工具。
        """
        agent = Agent(name="t")
        backend = OpenAiAgentsBackend()
        call_raw = ResponseFunctionToolCall(
            arguments='{"query":"合同"}',
            call_id="call_1",
            name="mcp__fachuan__search_case",
            type="function_call",
        )
        assert backend._translate_stream_event(
            RunItemStreamEvent(name="tool_called", item=ToolCallItem(agent=agent, raw_item=call_raw))
        )
        raw = {"type": "function_call_output", "call_id": "call_1", "output": "找到 3 个案件"}
        item = ToolCallOutputItem(agent=agent, raw_item=raw, output="找到 3 个案件")
        frames = backend._translate_stream_event(RunItemStreamEvent(name="tool_output", item=item))
        assert frames == [
            {
                "type": "tool_result",
                "tool_call_id": "call_1",
                "name": "mcp__fachuan__search_case",
                "result": "找到 3 个案件",
                "is_error": False,
            }
        ]

    def test_tool_output_failure_is_flagged(self) -> None:
        """SDK 把工具失败包成一段文本而不是抛异常，必须按前缀识别成 ``is_error``。"""
        agent = Agent(name="t")
        raw = {"type": "function_call_output", "call_id": "call_2"}
        item = ToolCallOutputItem(agent=agent, raw_item=raw, output="Error executing tool x: boom")
        frames = self._frames(RunItemStreamEvent(name="tool_output", item=item))
        assert frames[0]["is_error"] is True
        assert frames[0]["tool_call_id"] == "call_2"

    def test_message_output_item_is_dropped(self) -> None:
        """正文已由 delta 逐字发过，再发 ``message_output_created`` 会出现双份回答。"""
        agent = Agent(name="t")
        raw = ResponseOutputMessage(id="m1", content=[], role="assistant", status="completed", type="message")
        item = MessageOutputItem(agent=agent, raw_item=raw)
        assert self._frames(RunItemStreamEvent(name="message_output_created", item=item)) == []


class TestGatewayResolution:
    """网关三要素必须来自库，模型名绝不硬编码。"""

    def test_maps_base_url_key_and_default_model(self) -> None:
        assert gateway_from_provider(_provider(), None) == (
            "http://gw.internal:4000/v1",
            "sk-test",  # pragma: allowlist secret
            "kimi-2.6",
        )

    def test_model_hint_wins_over_default(self) -> None:
        """用户在 Admin 里换模型后，本轮显式选择优先——不许回落到写死的常量。"""
        resolved = gateway_from_provider(_provider(), "deepseek-v4")
        assert resolved is not None
        assert resolved[2] == "deepseek-v4"

    def test_model_hint_not_in_whitelist_is_still_used(self) -> None:
        """白名单表达「有哪些可选」，不是硬闸门（与 dsh_config 同口径）。"""
        resolved = gateway_from_provider(_provider(extra_models="a,b"), "zzz")
        assert resolved is not None
        assert resolved[2] == "zzz"

    def test_default_model_missing_falls_back_to_whitelist(self) -> None:
        """没有 default_model 时取 ``extra_models`` 首项，而不是空串。"""
        resolved = gateway_from_provider(_provider(default_model="", extra_models="alpha;beta"), None)
        assert resolved is not None
        assert resolved[2] == "alpha"

    def test_missing_base_url_is_unavailable(self) -> None:
        assert gateway_from_provider(_provider(base_url=""), None) is None

    def test_missing_keys_is_unavailable(self) -> None:
        assert gateway_from_provider(_provider(api_keys=""), None) is None

    def test_no_model_at_all_is_unavailable(self) -> None:
        assert gateway_from_provider(_provider(default_model="", extra_models=""), None) is None

    def test_key_rotation_uses_shared_helper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """多 key 时轮流用：全压在同一把 key 上会触发网关限流。"""
        seen: list[str] = []

        def _next(keys_in: list[str]) -> str:
            chosen = keys_in[len(seen) % len(keys_in)]
            seen.append(chosen)
            return chosen

        monkeypatch.setattr(backend_module, "_next_key", _next)
        provider = _provider(api_keys="k1\nk2\nk3")
        for _ in range(4):
            gateway_from_provider(provider, None)
        assert seen == ["k1", "k2", "k3", "k1"]


class TestProxyStripping:
    """网关是内网地址，代理变量必须缺席。

    真实事故：``HTTPS_PROXY`` 指向本地 Clash，请求被送到代理 → 无法回源内网 →
    网关返回 **502 no body**，表现得像「模型不回话」。``without_proxy_env`` 是
    dsh 侧验证过的同一份实现（复用而不是新写一份）。
    """

    def test_proxy_keys_absent_inside_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in proxy_env_keys():
            monkeypatch.setenv(key, "http://127.0.0.1:7897")
        with without_proxy_env():
            for key in proxy_env_keys():
                assert key not in os.environ

    def test_proxy_keys_restored_after_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
        with without_proxy_env():
            pass
        assert os.environ.get("HTTPS_PROXY") == "http://127.0.0.1:7897"

    def test_backend_module_reuses_the_shared_helper(self) -> None:
        """``openai_agents_backend`` 里的 ``without_proxy_env`` 就是 dsh 那份实现。

        各写一份迟早漂移（其中一份忘了恢复变量 → 本进程其它网络代码失去代理），
        所以这里钉住对象身份。
        """
        from apps.agent.backends import dsh_config

        assert backend_module.without_proxy_env is dsh_config.without_proxy_env

    def test_client_is_built_while_proxies_are_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """客户端构造那一刻环境里不能有代理变量（httpx 在构造期固定 mounts）。"""
        for key in proxy_env_keys():
            monkeypatch.setenv(key, "http://127.0.0.1:7897")
        seen: dict[str, Any] = {}

        def _client(**kwargs: Any) -> Any:
            seen["kwargs"] = kwargs
            seen["proxies_present"] = [key for key in proxy_env_keys() if key in os.environ]
            return SimpleNamespace(**kwargs)

        monkeypatch.setattr(backend_module, "AsyncOpenAI", _client)
        # 假 key，只为验证「构造期必须剔除代理」这条行为
        backend_module.build_openai_client(
            base_url="http://gw.internal:4000/v1",
            api_key="sk-test",  # pragma: allowlist secret
        )
        assert seen["proxies_present"] == [], "构造客户端时环境里还带着代理，请求会被送到 Clash（502 no body）"
        assert seen["kwargs"] == {
            "base_url": "http://gw.internal:4000/v1",
            "api_key": "sk-test",  # pragma: allowlist secret
        }  # pragma: allowlist secret
        for key in proxy_env_keys():
            assert os.environ.get(key) == "http://127.0.0.1:7897", "构造完必须原样恢复：os.environ 是进程全局"

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_proxies_are_restored_before_the_first_frame(
        self, _wired: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """剔除窗口只覆盖构造，不覆盖整轮。

        一轮是秒级、三 agent 并发时窗口近乎连续；若整轮都在窗口里，本进程其他
        出网调用（GitHub OAuth / 企微 / 法院系统）在这几秒内会一起失去代理。
        所以在**第一个 frame 产出时**环境里的代理就必须已经恢复。
        """
        for key in proxy_env_keys():
            monkeypatch.setenv(key, "http://127.0.0.1:7897")

        stream = OpenAiAgentsBackend().stream(_ctx())
        first = await stream.__anext__()
        await stream.aclose()
        assert first is not None and first["type"] == "delta", "桩事件的第一帧应当是正文增量"
        for key in proxy_env_keys():
            assert os.environ.get(key) == "http://127.0.0.1:7897", f"流开始后 {key} 仍缺席：窗口覆盖了整轮"


class TestToolFace:
    def test_filter_only_blocks_destructive_tools(self) -> None:
        """「工具面越多越好」：过滤器只排除不可逆删除，不做收窄。"""
        assert set(BLOCKED_TOOL_NAMES) == {"delete_case"}

    def test_mcp_server_uses_static_filter_and_bearer_header(self) -> None:
        """静态 dict 过滤器（callable 抛异常会被 SDK 静默吞掉）+ 律师 token 走 Bearer。"""
        server = backend_module.build_mcp_server(url="http://127.0.0.1:8011/mcp", user_token="tok-abc")
        assert server.name == "fachuan"
        assert server.params["url"] == "http://127.0.0.1:8011/mcp"
        assert server.params["headers"]["Authorization"] == "Bearer tok-abc"
        assert server.tool_filter == {"blocked_tool_names": ["delete_case"]}
        assert server.client_session_timeout_seconds == backend_module.MCP_CLIENT_TIMEOUT_SECONDS

    def test_max_turns_is_bounded(self) -> None:
        """超过 8 轮基本是模型空转，继续跑只烧 token。"""
        assert MAX_TURNS == 8


class TestErrorClassification:
    """异常必须在边界处转成 ``BackendError``，分类决定用户看到哪句话。"""

    @pytest.mark.parametrize(
        ("message", "kind", "retryable"),
        [
            ("Incorrect API key provided", BackendErrorKind.AUTH, False),
            ("Error code: 401 - unauthorized", BackendErrorKind.AUTH, False),
            ("Error code: 429 - rate limit exceeded", BackendErrorKind.RATE_LIMITED, True),
            ("context length exceeded the window", BackendErrorKind.CONTEXT_OVERFLOW, False),
            ("something odd happened", BackendErrorKind.UNKNOWN, False),
        ],
    )
    def test_message_keywords_map_to_kinds(self, message: str, kind: BackendErrorKind, retryable: bool) -> None:
        wrapped = OpenAiAgentsBackend._wrap_error(RuntimeError(message))
        assert wrapped.kind is kind
        assert wrapped.retryable is retryable

    def test_status_errors_map_by_type(self) -> None:
        """网关 4xx/5xx 会被包成 ``APIStatusError`` 的具体子类，按类型判比消息匹配可靠。

        实测：网关没起来时 ``AsyncOpenAI`` 抛 ``InternalServerError``——归 ``UNKNOWN``
        会让用户看到「未知错误」而不是「稍后重试」。
        """
        import httpx
        import openai

        request = httpx.Request("POST", "http://gw.internal:4000/v1/chat/completions")

        def _status_error(cls: Any, status: int) -> Exception:
            response = httpx.Response(status, request=request)
            return cast(Exception, cls("boom", response=response, body=None))

        cases = [
            (_status_error(openai.InternalServerError, 502), BackendErrorKind.UNAVAILABLE, True),
            (_status_error(openai.RateLimitError, 429), BackendErrorKind.RATE_LIMITED, True),
            (_status_error(openai.AuthenticationError, 401), BackendErrorKind.AUTH, False),
            (_status_error(openai.PermissionDeniedError, 403), BackendErrorKind.AUTH, False),
            (
                openai.APIConnectionError(request=cast(Any, request)),
                BackendErrorKind.UNAVAILABLE,
                True,
            ),
        ]
        for exc, kind, retryable in cases:
            wrapped = OpenAiAgentsBackend._wrap_error(exc)
            assert wrapped.kind is kind, f"{type(exc).__name__} 分类错误: {wrapped.kind}"
            assert wrapped.retryable is retryable

    def test_original_exception_is_kept_as_cause(self) -> None:
        """排障要看原始类型与堆栈，不能只留字符串。"""
        original = RuntimeError("Error code: 429")
        wrapped = OpenAiAgentsBackend._wrap_error(original)
        assert wrapped.__cause__ is original

    def test_backend_error_passes_through(self) -> None:
        original = BackendError(BackendErrorKind.BUSY, "忙")
        assert OpenAiAgentsBackend._wrap_error(original) is original


class TestRegistration:
    def test_ensure_registered_includes_openai_agents(self) -> None:
        from apps.agent.backends.builtin import ensure_registered

        ensure_registered()
        assert "openai-agents" in registry_module.available_kinds()

    def test_registration_is_idempotent(self) -> None:
        """``ensure_registered`` 每轮对话都调：第二次必须是空操作（重复注册会报错）。"""
        from apps.agent.backends.builtin import ensure_registered

        ensure_registered()
        ensure_registered()
        kinds = registry_module.available_kinds()
        assert kinds.count("openai-agents") == 1

    def test_missing_sdk_degrades_silently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SDK 没装时只跳过本后端，绝不能让整个应用起不来。"""
        import builtins

        from apps.agent.backends import builtin

        real_import = builtins.__import__

        def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name.endswith("openai_agents_backend") or name == "agents":
                raise ImportError("no sdk")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        monkeypatch.setattr(builtin, "_attempted", set())
        builtin._register_openai_agents()  # 不抛即通过
        assert "openai-agents" not in registry_module.available_kinds()


# ── 端到端（SDK 与网络全部打桩） ─────────────────────────────────────────


class _FakeStreamResult:
    """``RunResultStreaming`` 的最小替身：按固定顺序吐事件。"""

    def __init__(self, events: list[Any], *, error: BaseException | None = None) -> None:
        self._events = events
        self._error = error
        self.is_complete = False
        self.cancelled = False

    async def stream_events(self) -> AsyncIterator[Any]:
        for event in self._events:
            yield event
        if self._error is not None:
            raise self._error
        self.is_complete = True

    def cancel(self) -> None:
        self.cancelled = True


class _FakeServer:
    """MCP 客户端的替身：连接/关闭/调用都只记账，不发网络请求。

    形状照 ``MCPServerStreamableHttp`` 的公开面（``connect`` / ``cleanup`` /
    ``call_tool``）——池与后端只碰这三样，所以替身只要它们就够。
    """

    def __init__(self, *, connect_error: BaseException | None = None) -> None:
        self.connect_error = connect_error
        self.connect_count = 0
        self.cleanup_count = 0

    async def connect(self) -> None:
        self.connect_count += 1
        if self.connect_error is not None:
            raise self.connect_error

    async def cleanup(self) -> None:
        self.cleanup_count += 1


@pytest.fixture(autouse=True)
def _fresh_gateway_cache() -> Iterator[None]:
    """网关缓存是进程级全局状态；串用例会出假绿（A 用例的 provider 喂给 B 用例）。"""
    gateway_cache.invalidate_gateway_cache()
    yield
    gateway_cache.invalidate_gateway_cache()


@pytest.fixture(autouse=True)
def _isolated_mcp_pool(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每个用例一个干净的连接池。

    池是模块级单例（进程内复用是它的全部意义），跨用例共享会让
    「A 用例建立了几条连接」影响 B 用例的断言。测试里换成新的实例，
    生产代码不变。
    """
    pool = mcp_session_pool.McpSessionPool()
    monkeypatch.setattr(mcp_session_pool, "_pool", pool)
    yield
    asyncio.run(pool.close_all())


@pytest.fixture
def _wired(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """把网关解析、MCP 探测、SDK 三处打桩，留下可断言的把手。"""
    captured: dict[str, Any] = {}
    server = _FakeServer()
    servers: list[_FakeServer] = [server]
    events = [_text_delta("答"), _text_delta("案")]
    result = _FakeStreamResult(events)

    monkeypatch.setattr(
        backend_module,
        "get_gateway_settings",
        lambda model_hint: _settings(default_model="resolved-model"),
    )
    monkeypatch.setattr(backend_module, "port_open", lambda host, port: True)
    monkeypatch.setattr(backend_module, "shared_enabled", lambda: True)
    monkeypatch.setattr(
        backend_module,
        "endpoint_from_env",
        lambda: SimpleNamespace(host="127.0.0.1", port=8011, url="http://127.0.0.1:8011/mcp"),
    )
    monkeypatch.setattr(backend_module, "build_mcp_server", lambda **kwargs: servers[-1])
    monkeypatch.setattr(backend_module, "AsyncOpenAI", lambda **kwargs: captured.setdefault("client", kwargs))
    monkeypatch.setattr(backend_module.Runner, "run_streamed", lambda *a, **kw: captured.update(run=kw) or result)

    def _agent(**kwargs: Any) -> Any:
        captured["agent"] = kwargs
        return SimpleNamespace(**kwargs)

    def _next_server(**kwargs: Any) -> _FakeServer:
        """下一轮「新建」出来的客户端：记录调用参数，便于断言 token 隔离。"""
        fresh = _FakeServer()
        fresh.kwargs = kwargs  # type: ignore[attr-defined]
        servers.append(fresh)
        return fresh

    monkeypatch.setattr(backend_module, "build_mcp_server", _next_server)
    monkeypatch.setattr(backend_module, "Agent", _agent)
    return SimpleNamespace(captured=captured, server=server, servers=servers, result=result)


class TestStreamEndToEnd:
    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_emits_delta_frames_with_agent_and_run_id(self, _wired: SimpleNamespace) -> None:
        frames = [frame async for frame in OpenAiAgentsBackend().stream(_ctx())]
        deltas = [f for f in frames if f and f["type"] == "delta"]
        assert [f["content"] for f in deltas] == ["答", "案"]
        assert all(f["agent"] == "openai-agents" for f in deltas)
        assert all(f["run_id"] == "sess-1:openai-agents:1" for f in deltas)

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_ends_with_exactly_one_done(self, _wired: SimpleNamespace) -> None:
        """协议要求一轮恰好一个 ``done``；没有它编排层会当截断（前端一直显示生成中）。"""
        frames = [frame async for frame in OpenAiAgentsBackend().stream(_ctx())]
        done = [f for f in frames if f and f["type"] == "done"]
        assert len(done) == 1
        assert done[0]["session_id"] == "sess-1"
        assert done[0]["agent"] == "openai-agents"
        # 水位不编造：SDK 没有窗口大小，给 None 而不是 0（0 会让前端显示「已满」）。
        assert done[0]["context_used_tokens"] is None
        assert done[0]["context_total_tokens"] is None
        assert frames[-1] is done[0], "done 必须是最后一帧"

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_model_comes_from_provider_and_is_recorded(self, _wired: SimpleNamespace) -> None:
        """模型来自库（这里被桩成 ``resolved-model``），并回填到 ``result_for``。"""
        backend = OpenAiAgentsBackend()
        _ = [frame async for frame in backend.stream(_ctx(run_id="r-1"))]
        assert _wired.captured["client"]["base_url"] == "http://gw.internal:4000/v1"
        assert _wired.captured["client"]["api_key"] == "sk-test"  # pragma: allowlist secret
        assert _wired.captured["agent"]["model"].model == "resolved-model"
        assert _wired.captured["run"]["max_turns"] == MAX_TURNS
        recorded = backend.result_for("r-1")
        assert recorded is not None
        assert recorded.model == "resolved-model"
        assert recorded.context_used is None

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_mcp_server_is_connected_and_reused(self, _wired: SimpleNamespace) -> None:
        """同一 token 的第二轮**不再建连**（首字延迟里约 2.9s 就是这条链路）。

        但连接也不会在本轮结束时被关掉——那等于没有复用（见 ``mcp_session_pool``）。
        """
        backend = OpenAiAgentsBackend()
        _ = [frame async for frame in backend.stream(_ctx(run_id="r-1"))]
        _ = [frame async for frame in backend.stream(_ctx(run_id="r-2"))]

        # 断言看**池的台账**，不看 ``servers`` 的长度：
        #
        # ``_wired`` fixture 在打桩时**先预建了一个** ``_FakeServer`` 放进
        # ``servers[0]``（给「不经过池的路径」用），所以 ``len(servers)`` 天然至少
        # 是 1。用它判「factory 被调用几次」会永远差一个——这条用例最初就是这么
        # 写的，把「复用成功」误判成「没复用」（实测 ``servers[0].connect_count``
        # 恒为 0，因为池用的是 factory 现造的那条，不是这个预建对象）。
        #
        # 真正要验的是：**同一 token 的两轮只产生一条连接，且它在本轮结束后
        # 没有被关掉**（关掉=没有复用）。这两件事池的台账里都有。
        from apps.agent.backends.mcp_session_pool import get_mcp_session_pool

        pool = get_mcp_session_pool()
        url = "http://127.0.0.1:8011/mcp"
        assert pool.connection_count(url=url, user_token="tok") == 1, (
            "同一 token 的两轮应只有一条连接（第二轮复用，不重建）"
        )
        assert pool.leased_count(url=url, user_token="tok") == 0, (
            "两轮都结束后连接应已归还（leases 归零），而不是还挂在某一轮名下"
        )
        assert len(_wired.captured["agent"]["mcp_servers"]) == 1

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_no_token_means_no_tools_but_conversation_works(self, _wired: SimpleNamespace) -> None:
        """无律师 token 时降级为「无工具但能对话」，而不是整轮 401 失败。"""
        frames = [frame async for frame in OpenAiAgentsBackend().stream(_ctx(token=""))]
        assert _wired.captured["agent"]["mcp_servers"] == []
        assert any(f and f["type"] == "done" for f in frames)

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_unavailable_gateway_raises_backend_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """没有可用平台配置时明确报错，而不是回退到官方端点（用错 key、记错账）。"""
        monkeypatch.setattr(backend_module, "get_gateway_settings", lambda model_hint: None)
        with pytest.raises(BackendError) as excinfo:
            _ = [frame async for frame in OpenAiAgentsBackend().stream(_ctx())]
        assert excinfo.value.kind is BackendErrorKind.UNAVAILABLE
        assert "LLMProvider" not in str(excinfo.value), "文案要面向用户，不暴露内部模型名"
        assert "管理员" in str(excinfo.value)

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_sdk_failure_is_wrapped_as_backend_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SDK 抛出的异常在边界处转成 ``BackendError``，否则编排层的 except 收不到。"""
        monkeypatch.setattr(backend_module, "Agent", lambda **kwargs: SimpleNamespace(**kwargs))
        monkeypatch.setattr(backend_module, "get_gateway_settings", lambda model_hint: _settings())
        monkeypatch.setattr(backend_module, "port_open", lambda host, port: False)
        monkeypatch.setattr(
            backend_module.Runner,
            "run_streamed",
            lambda *a, **kw: _FakeStreamResult([], error=RuntimeError("Error code: 401 - unauthorized")),
        )
        with pytest.raises(BackendError) as excinfo:
            _ = [frame async for frame in OpenAiAgentsBackend().stream(_ctx())]
        assert excinfo.value.kind is BackendErrorKind.AUTH

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_cancel_is_propagated_verbatim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """用户按停止不是错误：包成 ``BackendError`` 会让成功率统计失真。"""
        monkeypatch.setattr(backend_module, "Agent", lambda **kwargs: SimpleNamespace(**kwargs))
        monkeypatch.setattr(backend_module, "get_gateway_settings", lambda model_hint: _settings())
        monkeypatch.setattr(backend_module, "port_open", lambda host, port: False)

        class _CancellingResult(_FakeStreamResult):
            async def stream_events(self) -> AsyncIterator[Any]:
                raise asyncio.CancelledError
                yield None  # pragma: no cover - 只满足生成器协议

        monkeypatch.setattr(backend_module.Runner, "run_streamed", lambda *a, **kw: _CancellingResult([]))
        with pytest.raises(asyncio.CancelledError):
            _ = [frame async for frame in OpenAiAgentsBackend().stream(_ctx())]
