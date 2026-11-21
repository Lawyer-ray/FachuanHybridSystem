"""``DshBackend`` / ``dsh_config`` —— DeepSeek Harness 后端的接缝与事件翻译。

本文件只验**不需要真 SDK、不需要真 API key** 的部分：

1. **身份与能力声明**：``kind == "dsh"``，五项能力如实（``steer`` 为 ``False``，
   因为 SDK 未暴露 steer/abort）。声明错了前端会渲染出不存在的控件。
2. **结构化满足协议**：``isinstance(DshBackend(), AgentBackend)``。
3. **事件翻译**：构造 dsh notification payload，断言产出正确的 SSE 事件。
   全部走纯函数 ``DshBackend._translate``，不起子进程。
4. **``dsh_config`` 映射**：构造 provider 桩，断言 base_url / api_key / model
   与 dsh_home 的 user 级隔离。
5. **注册表**：``builtin._register_dsh`` 在 SDK 缺失时静默降级、不抛。

``dsh_backend`` 顶层 ``import deepseek_harness``（注册表要用 SDK 类型），所以本文件
用 ``pytest.importorskip`` 兜住「SDK 没装」的 CI 环境：那时跳过的是 import 层面的
用例，而不是把它们改成假绿。
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("deepseek_harness", reason="deepseek-harness-sdk 未安装，跳过 dsh 后端用例")

from apps.agent.backends import AgentBackend, BackendCapabilities, RunContext
from apps.agent.backends import registry as registry_module
from apps.agent.backends.dsh_backend import _APPROVAL_WIRED, DshBackend, DshRunResult, _HarnessPool, _log_unmapped
from apps.agent.backends.dsh_config import DSH_HOME_ENV, DshProviderConfig, build_config, dsh_home_for, dsh_patches


class _Session:
    session_id = "sess-1"


def _ctx(run_id: str = "sess-1:dsh:1", user_id: int | None = None) -> RunContext:
    return RunContext(
        run_id=run_id,
        session=_Session(),
        user_id=user_id,
        prompt="你好",
        user_token="tok",
        model=None,
        tool_selection=None,
    )


def _provider(**overrides: Any) -> Any:
    """足以映射出 dsh 配置的 provider 桩（形状照 ``LLMProvider``）。"""

    class _P:
        base_url = "http://gw.example/v1"
        api_keys = "sk-test"  # pragma: allowlist secret
        default_model = "kimi-2.6"
        extra_models = ""

    p = _P()
    for key, value in overrides.items():
        setattr(p, key, value)
    return p


def _notification(event_type: str, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """构造一条 ``session.event`` 通知（dsh 的正文/工具/结束都走这个外壳）。"""
    return (
        "session.event",
        {"sessionId": "sess-1", "event": {"type": event_type, "data": data}},
    )


@pytest.fixture(autouse=True)
def _isolated_registry() -> Any:
    """注册表是模块级全局状态；串用例会出假绿。"""
    registry_module.clear()
    yield
    registry_module.clear()


class TestIdentity:
    def test_kind_is_dsh(self) -> None:
        assert DshBackend.kind == "dsh"

    def test_capabilities_match_sdk_facts(self) -> None:
        """能力声明必须逐项等于现实，不是「目标状态」。

        ``steer=False``：SDK 的 ``Session`` 没有 steer/abort 方法。声明 ``True``
        会让前端显示插话输入框，而用户敲进去的话会被直接丢弃——比禁用更糟
        （见 ``base.py`` 的 ``steer`` 注释）。

        ``approval`` 同理，而且后果更重：本栏**没有人工审批闸门**——
        ``approval_requests`` 从未传 ``True``，runtime 不发 ``approval/request``
        给我们（allow/deny 由 runtime 自带 answerer 决定），律师看不到任何审批卡；
        高危调用的强制闸门在 MCP 服务端（``tool_approval_gate``）。原先写死 ``True``
        让 ``/backends`` 把「有四级审批闸门」这条谎话透给前端——**合规红线级别的
        错误能力声明**。现在绑定到 ``_APPROVAL_WIRED``：真正接上审批时只改一个
        常量，声明自动跟上。
        """
        caps = DshBackend.capabilities
        assert isinstance(caps, BackendCapabilities)
        assert caps.streaming is True
        assert caps.tool_calls is True
        assert caps.approval is _APPROVAL_WIRED
        assert caps.compaction is True
        assert caps.steer is False
        assert caps.concurrent_in_session is False

    def test_satisfies_agent_backend_protocol(self) -> None:
        """``runtime_checkable`` 协议：不继承也要能过 isinstance。"""
        assert isinstance(DshBackend(), AgentBackend)


class TestEventTranslation:
    """``_translate`` 是纯函数：给 notification，断言 SSE 事件。"""

    def _translate(self, notification: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        backend = DshBackend()
        method, payload = notification
        return backend._translate(method, payload)

    def test_assistant_text_becomes_delta(self) -> None:
        frames = self._translate(
            _notification("assistant/message", {"message": {"content": [{"type": "text", "text": "答"}]}})
        )
        assert frames == [{"type": "delta", "content": "答"}]

    def test_assistant_message_without_wrapper_is_supported(self) -> None:
        """``final_response`` 里 ``content_owner = message if isinstance(message, dict) else data``，
        说明两种形状都可能出现；这里两种都得认。"""
        frames = self._translate(_notification("assistant/message", {"content": [{"type": "text", "text": "嗯"}]}))
        assert frames == [{"type": "delta", "content": "嗯"}]

    def test_thinking_block_becomes_thinking(self) -> None:
        frames = self._translate(
            _notification("assistant/message", {"message": {"content": [{"type": "thinking", "text": "想"}]}})
        )
        assert frames == [{"type": "thinking", "content": "想"}]

    def test_tool_call_block_becomes_tool_call(self) -> None:
        frames = self._translate(
            _notification(
                "assistant/message",
                {
                    "message": {
                        "content": [
                            {
                                "type": "toolCall",
                                "id": "call-1",
                                "name": "mcp__fachuan__get_case",
                                "arguments": '{"id": 7}',
                            }
                        ]
                    }
                },
            )
        )
        # ``arguments`` 由 ``_tool_call_arguments`` 解成对象（参数级展示与审批卡的
        # ``tool_args`` 都要按键取值；``sse_types`` 里该字段是 ``Any``，前端两种
        # 形状都认，所以解成对象不会让任何一侧退化）。
        assert frames == [
            {
                "type": "tool_call",
                "tool_call_id": "call-1",
                "name": "mcp__fachuan__get_case",
                "arguments": {"id": 7},
            }
        ]

    def test_hyphenated_tool_call_block_becomes_tool_call(self) -> None:
        """dsh 的 assistant 消息里工具块类型是 **``tool-call``**（连字符）。

        原先只认 ``toolCall`` / ``tool_call``（早期推断名），结果 dsh 真实流里
        一帧 ``tool_call`` 都不产：前端看不到工具名与参数，审批卡也就没有工具信息。
        字段是 ``callId`` / ``name`` / ``arguments``（与 run 事件 ``tool/call`` 同名）。
        """
        frames = self._translate(
            _notification(
                "assistant/message",
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool-call",
                                "callId": "call-9",
                                "name": "mcp__fachuan__list_cases",
                                "arguments": '{"limit": 5}',
                            }
                        ]
                    }
                },
            )
        )
        [frame] = frames
        assert frame["type"] == "tool_call"
        assert frame["tool_call_id"] == "call-9"
        assert frame["name"] == "mcp__fachuan__list_cases"
        assert frame["arguments"] == {"limit": 5}

    def test_tool_call_run_event_becomes_tool_call(self) -> None:
        """``tool/call`` 运行事件也要出 ``tool_call`` 帧（字段名与帧字段不同）。

        dsh 侧是 ``callId`` / ``name`` / ``arguments``（raw JSON 字符串），帧侧是
        ``tool_call_id`` / ``name`` / ``arguments``；不翻这一条前端只看得到正文。
        """
        from apps.agent.sse_types import ToolCallEvent

        frames = self._translate(
            _notification("tool/call", {"callId": "call-7", "name": "mcp__fachuan__get_case", "arguments": '{"id": 7}'})
        )
        assert frames == [
            {
                "type": "tool_call",
                "tool_call_id": "call-7",
                "name": "mcp__fachuan__get_case",
                "arguments": {"id": 7},
            }
        ]
        # 帧必须能过契约模型（字段改名后不同步会静默失效）
        assert isinstance(ToolCallEvent.model_validate(frames[0]), ToolCallEvent)

    def test_non_json_tool_arguments_do_not_raise(self) -> None:
        """参数不是合法 JSON（截断 / 单引号）时不能让整轮事件流崩掉：原样进 ``_raw``。"""
        from apps.agent.sse_types import ToolCallEvent

        broken = "{'id': 7"
        for notification in (
            _notification("tool/call", {"callId": "c1", "name": "n", "arguments": broken}),
            _notification(
                "assistant/message",
                {"message": {"content": [{"type": "tool-call", "callId": "c2", "name": "n", "arguments": broken}]}},
            ),
        ):
            [frame] = self._translate(notification)
            assert frame["arguments"] == {"_raw": broken}
            assert isinstance(ToolCallEvent.model_validate(frame), ToolCallEvent)

    def test_mixed_blocks_keep_order(self) -> None:
        """一段 assistant 消息里可同时有思考与正文；顺序不能乱（前端按序拼接）。"""
        frames = self._translate(
            _notification(
                "assistant/message",
                {
                    "message": {
                        "content": [
                            {"type": "thinking", "text": "想"},
                            {"type": "text", "text": "答"},
                        ]
                    }
                },
            )
        )
        assert [f["type"] for f in frames] == ["thinking", "delta"]

    def test_turn_end_error_becomes_error_event(self) -> None:
        """``turn/end`` 的 ``reason.kind == "error"`` 是模型侧失败，必须报 error。

        帧要走 ``errors.project_message``：SDK 只给一句话，但那句话可能就是 429 /
        上下文超限 / 网关卡住。手写帧时前端拿不到 ``code``，多答时律师会把
        「等 60 秒就好」读成「这一栏的后端废了」。
        """
        frames = self._translate(_notification("turn/end", {"reason": {"kind": "error", "message": "上游 429"}}))
        [frame] = frames
        assert frame["type"] == "error"
        assert (frame["code"], frame["scope"]) == ("rate_limited", "account")
        # 中文原文原样保留（它已经是写给人看的句子），原文同时进 detail 供排障。
        assert frame["message"] == "上游 429"
        assert frame["detail"]["reason"] == "上游 429"

    def test_turn_end_normal_produces_no_event(self) -> None:
        """正常结束由编排层发 done，本层不重复发（协议：一轮只一个 done）。"""
        assert self._translate(_notification("turn/end", {"reason": {"kind": "stop"}})) == []

    def test_inbox_receipt_is_silent(self) -> None:
        """``agent/inbox/spliced`` 是 prompt 入队回执，无内容也不算未知事件。"""
        assert self._translate(_notification("agent/inbox/spliced", {"inserted": []})) == []

    def test_session_status_is_silent(self) -> None:
        assert self._translate(("session.status", {"sessionId": "sess-1", "status": "idle"})) == []

    def test_unknown_method_passes_through_as_unknown(self) -> None:
        """未识别的方法透传 ``unknown`` 而不是丢弃：SDK 是 rc 版，静默丢会让
        「前端少了一栏内容」变成无迹可查。"""
        frames = self._translate(("some.new/event", {"foo": 1}))
        assert frames == [{"type": "unknown", "raw": {"method": "some.new/event", "payload": {"foo": 1}}}]

    def test_unknown_event_type_passes_through_as_unknown(self) -> None:
        frames = self._translate(_notification("some/new-type", {"x": 1}))
        assert frames == [
            {
                "type": "unknown",
                "raw": {"method": "session.event", "event": {"type": "some/new-type", "data": {"x": 1}}},
            }
        ]

    def test_log_unmapped_does_not_raise(self) -> None:
        """未映射事件的日志助手必须容错（它会在 SDK 回调线程上被调用）。"""
        # 显式断言返回值：该助手约定「只记日志、永远返回 None」。
        # 零断言的「不抛即通过」在本仓质量门禁里是不允许的——若以后有人把它
        # 改成返回可抛的结构（比如把 payload 回传给调用方），这里会立刻红。
        assert _log_unmapped("whatever", {"k": "v"}) is None


class TestTranslationShapesMatchSseContract:
    """产出的事件必须能被 ``sse_types`` 的 pydantic 模型校验（契约不同步会静默失效）。"""

    def test_delta_and_thinking_validate(self) -> None:
        from apps.agent.sse_types import DeltaEvent, ErrorEvent, ThinkingEvent, ToolCallEvent

        backend = DshBackend()
        frames = backend._translate(
            *_notification(
                "assistant/message",
                {
                    "message": {
                        "content": [
                            {"type": "thinking", "text": "想"},
                            {"type": "text", "text": "答"},
                            {"type": "toolCall", "id": "c1", "name": "n"},
                        ]
                    }
                },
            )
        )
        by_type = {f["type"]: f for f in frames}
        assert isinstance(ThinkingEvent.model_validate(by_type["thinking"]), ThinkingEvent)
        assert isinstance(DeltaEvent.model_validate(by_type["delta"]), DeltaEvent)
        assert isinstance(ToolCallEvent.model_validate(by_type["tool_call"]), ToolCallEvent)
        [error] = backend._translate(*_notification("turn/end", {"reason": {"kind": "error", "message": "x"}}))
        assert isinstance(ErrorEvent.model_validate(error), ErrorEvent)


class _StubHarness:
    """``DeepSeekHarness`` 的最小桩：``run`` 在调用线程上发通知后返回。

    这是同步→异步桥的测试替身。真 SDK 的行为就是「同一线程上连续调用回调、
    最后一次调用后返回到达」——桩必须复现这一点，否则测不出回调线程投递与
    生成器侧消费之间的竞态。
    """

    def __init__(self, notifications: list[tuple[str, dict[str, Any]]], error: BaseException | None = None) -> None:
        self._notifications = notifications
        self._error = error
        self.thread_names: list[str] = []
        self.closed = False

    def __init_subclass__(cls, **kwargs: Any) -> None:  # pragma: no cover - 仅为子类可读
        super().__init_subclass__(**kwargs)

    def run(self, prompt: str, *, session_id: str, on_notification: Any) -> None:
        """**旧形状**：``harness.run(prompt, session_id=...)``。

        生产路径已不再用它（改用 ``resume_session().run()``，见下）。保留是为了
        让「有人误用旧接口」时测试能立刻红——真 SDK 的 ``run(session_id=...)``
        对已存在会话会抛 ``already exists``。
        """
        import threading

        from deepseek_harness.models import Notification

        self.thread_names.append(threading.current_thread().name)
        for method, payload in self._notifications:
            on_notification(Notification(method=method, payload=payload))
        if self._error is not None:
            raise self._error

    def resume_session(self, session_id: str) -> Any:
        """返回一个可 ``run(prompt, on_notification=...)`` 的 Session 桩。

        对应 SDK 的 ``DeepSeekHarness.resume_session``：恢复磁盘上的历史再续跑。
        生产代码用它处理「同一 AgentSession 的第二轮」——直接用
        ``harness.run(session_id=...)`` 会命中 ``session ... already exists``
        （真实事故 2026-11-19）。
        """
        harness = self

        class _Session:
            id = session_id

            def run(self, prompt: str, *, on_notification: Any) -> None:
                harness.run(prompt, session_id=session_id, on_notification=on_notification)

        return _Session()

    def start_session(self, session_id: str) -> Any:
        return self.resume_session(session_id)

    def close(self) -> None:
        self.closed = True


class _StubPoolForStream(_HarnessPool):
    """池桩：不启动子进程，直接交出预置 harness。"""

    def __init__(self, harness: _StubHarness) -> None:
        super().__init__(max_size=2)
        self._stub = harness
        self.released = 0

    def acquire(self, ctx: RunContext, config: Any) -> Any:
        return self._stub

    def release(self, ctx: RunContext) -> None:
        self.released += 1
        self._stub.close()


class TestStreamBridge:
    """同步 SDK 桥成异步事件流（不需要真 SDK 运行时，也不需要数据库）。

    真实 LLMProvider 查询被替掉：``_resolve_config`` 的读库行为属于编排层的事，
    这里只验「回调 → 队列 → 生成器」这条线。
    """

    def _backend(self, harness: _StubHarness) -> tuple[DshBackend, _StubPoolForStream]:
        pool = _StubPoolForStream(harness)
        backend = DshBackend(pool=pool)
        return backend, pool

    @staticmethod
    def _patch_config(monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.backends import dsh_config

        monkeypatch.setattr(
            dsh_config,
            "build_config",
            lambda **kwargs: DshProviderConfig(
                dsh_home="/tmp/x", provider="deepseek-official", model="kimi-2.6", base_url="u", api_key="k"
            ),
        )

    def test_notifications_become_sse_events_with_agent_and_run_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """桥的核心断言：回调里的事件最终带 ``agent`` / ``run_id`` 到达消费侧。

        两个 agent 同题并行时前端靠这两个字段分流，缺了就挂错栏。
        """
        self._patch_config(monkeypatch)
        harness = _StubHarness(
            [
                _notification("agent/inbox/spliced", {"inserted": []}),
                _notification("assistant/message", {"message": {"content": [{"type": "text", "text": "答"}]}}),
                _notification("turn/end", {"reason": {"kind": "stop"}}),
            ]
        )
        backend, pool = self._backend(harness)
        ctx = _ctx("sess-1:dsh:1")

        async def collect() -> list[dict[str, Any]]:
            return [e async for e in backend.stream(ctx) if e is not None]

        events = asyncio.run(collect())
        assert events == [{"type": "delta", "content": "答", "agent": "dsh", "run_id": "sess-1:dsh:1"}]
        # 一轮结束必须释放子进程，否则 dsh 会一直占着池位与内存。
        assert pool.released >= 1
        assert harness.closed

    def test_tool_call_frame_carries_agent_and_run_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """工具帧与正文帧同口径：出口处统一补 ``agent`` / ``run_id``。

        两个后端同题并行时，前端靠这两个字段把工具行挂到正确的那一栏；只给正文
        补、给工具帧不补，工具调用就会挂错栏。
        """
        self._patch_config(monkeypatch)
        harness = _StubHarness(
            [
                _notification("tool/call", {"callId": "call-3", "name": "get_case", "arguments": '{"id": 7}'}),
                _notification("turn/end", {"reason": {"kind": "stop"}}),
            ]
        )
        backend, _pool = self._backend(harness)

        async def collect() -> list[dict[str, Any]]:
            return [e async for e in backend.stream(_ctx("sess-1:dsh:2")) if e is not None]

        events = asyncio.run(collect())
        assert events == [
            {
                "type": "tool_call",
                "tool_call_id": "call-3",
                "name": "get_case",
                "arguments": {"id": 7},
                "agent": "dsh",
                "run_id": "sess-1:dsh:2",
            }
        ]

    def test_run_happens_off_the_event_loop_thread(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``run()`` 是同步阻塞的：跑在主线程会把整个事件循环卡死（其它会话全停）。"""
        self._patch_config(monkeypatch)
        harness = _StubHarness([])
        backend, _pool = self._backend(harness)

        async def collect() -> None:
            async for _ in backend.stream(_ctx()):
                pass

        asyncio.run(collect())
        assert harness.thread_names
        assert harness.thread_names[0].startswith("dsh-run")

    def test_result_is_ready_after_stream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """收尾事实（本轮实际模型）必须在流结束时可取，编排层靠它回写会话模型。"""
        self._patch_config(monkeypatch)
        backend, _pool = self._backend(
            _StubHarness([_notification("assistant/message", {"content": [{"type": "text", "text": "x"}]})])
        )
        ctx = _ctx()

        async def collect() -> None:
            async for _ in backend.stream(ctx):
                pass

        asyncio.run(collect())
        result = backend.result_for(ctx.run_id)
        assert isinstance(result, DshRunResult)
        assert result.model == "kimi-2.6"

    def test_sdk_error_becomes_backend_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SDK 异常必须在边界处转 ``BackendError``（否则编排层的 except 全落空）。"""
        from apps.agent.backends import BackendError, BackendErrorKind

        self._patch_config(monkeypatch)
        backend, _pool = self._backend(_StubHarness([], error=RuntimeError("upstream 429 rate limit")))

        async def collect() -> None:
            async for _ in backend.stream(_ctx()):
                pass

        with pytest.raises(BackendError) as info:
            asyncio.run(collect())
        assert info.value.kind == BackendErrorKind.RATE_LIMITED
        assert info.value.retryable is True

    def test_missing_provider_raises_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无可用 provider 必须报可读错误，不能静默用 dsh 的默认 provider。"""
        from apps.agent.backends import BackendError, BackendErrorKind, dsh_config

        monkeypatch.setattr(dsh_config, "build_config", lambda **kwargs: None)
        backend, _pool = self._backend(_StubHarness([]))

        async def collect() -> None:
            async for _ in backend.stream(_ctx()):
                pass

        with pytest.raises(BackendError) as info:
            asyncio.run(collect())
        assert info.value.kind == BackendErrorKind.UNAVAILABLE

    def test_cancel_releases_harness(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """取消（用户按停止）必须释放 harness，且不把取消包成 ``BackendError``。"""
        self._patch_config(monkeypatch)

        class _BlockingHarness(_StubHarness):
            def run(self, prompt: str, *, session_id: str, on_notification: Any) -> None:
                import time

                time.sleep(0.2)
                super().run(prompt, session_id=session_id, on_notification=on_notification)

        backend, pool = self._backend(_BlockingHarness([]))

        async def cancel_soon() -> None:
            task = asyncio.ensure_future(_drain(backend.stream(_ctx())))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(cancel_soon())
        assert pool.released >= 1


async def _drain(stream: Any) -> None:
    async for _ in stream:
        pass


class TestRunResult:
    def test_result_for_missing_run_is_none(self) -> None:
        assert DshBackend().result_for("nope") is None

    def test_run_result_is_frozen_and_honest_about_context(self) -> None:
        """水位恒为 None：SDK 未暴露上下文统计，编造 0 会让前端显示「已满」。"""
        result = DshRunResult(model="kimi-2.6")
        assert result.context_used is None
        assert result.context_total is None


class TestHarnessPool:
    def test_key_uses_user_and_plain_session_id(self) -> None:
        """dsh 要的是纯 session id；``run_id`` 是编排层寻址键，不能当会话 id 用。"""
        assert _HarnessPool.key_for(_ctx("sess-1:dsh:9", user_id=42)) == (42, "sess-1")

    def test_pool_rejects_when_full(self) -> None:
        """池满必须快速失败（BUSY），不排队：dsh 是可选后端，排队只会拖到超时。"""
        from apps.agent.backends import BackendError, BackendErrorKind

        pool = _HarnessPool(max_size=1)
        # 直接占位，避免真起子进程。
        pool._harnesses[(1, "a")] = object()  # type: ignore[assignment]
        with pytest.raises(BackendError) as info:
            pool.acquire(_ctx(user_id=2), SimpleNamespace())
        assert info.value.kind == BackendErrorKind.BUSY
        assert info.value.retryable is True

    def test_release_is_idempotent_for_unknown_session(self) -> None:
        pool = _HarnessPool()
        # 释放一个从没 acquire 过的会话：不能抛，也不能把池子搞成非空
        pool.release(_ctx())
        assert pool.size == 0


@pytest.fixture(autouse=True)
def _no_dsh_profile_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认关闭 dsh profile 自动引导。

    ``dsh_home_for()`` 会调 ``_ensure_profile()``，后者在缺 profile 时会**真的去跑
    ``dsh plugin add``（联网装包）**。单测不需要它，而且在 CI（无网络 / 无 pnpm）
    里会以 exit 127 失败——实测曾让 8 个用例全红。

    要验引导行为本身的用例自己打开（或直接测 ``_ensure_profile``）。
    """
    monkeypatch.setenv("FACHUAN_DSH_AUTO_PROFILE", "0")


class TestDshConfig:
    def test_maps_base_url_key_and_model(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path))
        config = build_config(user_id=7, provider=_provider())
        assert isinstance(config, DshProviderConfig)
        assert config.base_url == "http://gw.example/v1"
        assert config.api_key == "sk-test"  # pragma: allowlist secret
        assert config.model == "kimi-2.6"
        # dsh home 按 user_id 隔离（共目录会串号，见模块注释）
        assert config.dsh_home == str(tmp_path / "7")

    def test_model_hint_wins_over_default(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path))
        config = build_config(user_id=1, model_hint="glm53", provider=_provider())
        assert config is not None
        assert config.model == "glm53"

    def test_returns_none_without_provider(self) -> None:
        """无可用 provider 必须返回 None 让调用方报友好错误，不能静默用默认值。"""
        assert build_config(user_id=1, provider=None) is None

    def test_returns_none_without_keys(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path))
        assert build_config(user_id=1, provider=_provider(api_keys="")) is None

    def test_returns_none_without_base_url(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path))
        assert build_config(user_id=1, provider=_provider(base_url="  ")) is None

    def test_key_model_scope_format_is_reused(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """``key|model1,model2`` 是仓库既有格式，必须走 ``parse_key_entries`` 而不是当字符串。"""
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path))
        config = build_config(user_id=1, provider=_provider(api_keys="sk-a|kimi-2.6"))
        assert config is not None
        assert config.api_key == "sk-a"  # pragma: allowlist secret

    def test_sdk_kwargs_are_exactly_sdk_fields(self) -> None:
        """``sdk_kwargs`` 的键必须是 ``DeepSeekHarnessConfig`` 的真实字段（否则 TypeError）。"""
        from deepseek_harness import DeepSeekHarnessConfig

        config = DshProviderConfig(
            dsh_home="/tmp/x", provider="deepseek-official", model="m", base_url="u", api_key="k"
        )
        sdk = DeepSeekHarnessConfig(**config.sdk_kwargs())
        assert sdk.dsh_home == "/tmp/x"
        assert sdk.base_url == "u"
        assert sdk.api_key == "k"
        assert sdk.model == "m"

    def test_shared_home_without_user(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """无用户身份落到 ``_shared``：不能回退成「谁先来算谁的」。"""
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path))
        assert dsh_home_for(None) == str(tmp_path / "_shared")

    def test_home_permissions_are_private(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """目录里有凭据缓存，必须是 0700（与 pi 的 agent_home 同口径）。"""
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path))
        path = dsh_home_for(3)
        assert oct(os.stat(path).st_mode)[-3:] == "700"


class TestDshPatches:
    def test_empty_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FACHUAN_DSH_PATCHES", raising=False)
        assert dsh_patches() == ()

    def test_existing_files_are_kept_missing_are_dropped(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """不存在的 patch 会让 dsh 启动失败、报错落在 initialize 超时上——必须剔除。"""
        real = tmp_path / "mcp.patch.yml"
        real.write_text("[]", encoding="utf-8")
        missing = tmp_path / "nope.yml"
        monkeypatch.setenv("FACHUAN_DSH_PATCHES", os.pathsep.join([str(real), str(missing)]))
        assert dsh_patches() == (str(real),)


class TestRegistration:
    def test_register_dsh_is_idempotent(self) -> None:
        from apps.agent.backends.builtin import _register_dsh
        from apps.agent.backends.registry import available_kinds, get

        _register_dsh()
        _register_dsh()
        assert "dsh" in available_kinds()
        assert isinstance(get("dsh"), DshBackend)

    def test_ensure_registered_keeps_dsh(self) -> None:
        """注册表被 ``clear()`` 后，``ensure_registered`` 必须把 dsh 补回来。"""
        from apps.agent.backends.builtin import ensure_registered
        from apps.agent.backends.registry import available_kinds

        ensure_registered()
        registry_module.clear()
        ensure_registered()
        assert "dsh" in available_kinds()

    def test_missing_sdk_degrades_silently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SDK 没装时只跳过 dsh，绝不能让整个应用起不来（注册表装不上是可选失败）。"""
        import builtins

        from apps.agent.backends import builtin

        real_import = builtins.__import__

        def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name.endswith("dsh_backend") or name == "deepseek_harness":
                raise ImportError("no sdk")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        monkeypatch.setattr(builtin, "_attempted", set())
        builtin._register_dsh()  # 不抛即通过
        assert "dsh" not in registry_module.available_kinds()


# ============ 正式验收阶段补的守护测试（真实网关跑出来才发现的三件事）============


class TestProxyStripping:
    """代理变量必须从 dsh 子进程环境里消失。

    真实事故：律所网关是内网地址（`http://152.16.10.110:4000/v1`），开发机
    `HTTPS_PROXY` 指向本地 Clash。dsh SDK 用 `os.environ.copy()` 构造子进程
    环境（只能加不能删），请求被送到代理 → 无法回源内网 → **502 no body**，
    重试 5 次后返回空回复。表现为「模型不回话」，极易误判成模型或 key 的问题。

    同一条 key + base_url 直连 `chat/completions` 正常，走代理则 502 —— 这条
    测试锁的是「不要再让人踩一遍」。
    """

    def test_proxy_keys_removed_inside_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.backends.dsh_config import proxy_env_keys, without_proxy_env

        for key in proxy_env_keys():
            monkeypatch.setenv(key, "http://127.0.0.1:7897")

        import os

        with without_proxy_env():
            for key in proxy_env_keys():
                assert key not in os.environ, f"{key} 仍在内进程环境里，子进程会继承到代理"

    def test_proxy_keys_restored_after_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.backends.dsh_config import proxy_env_keys, without_proxy_env

        for key in proxy_env_keys():
            monkeypatch.setenv(key, "http://127.0.0.1:7897")

        import os

        with without_proxy_env():
            pass
        for key in proxy_env_keys():
            assert os.environ.get(key) == "http://127.0.0.1:7897", f"{key} 退出后未恢复"

    def test_restored_on_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.backends.dsh_config import without_proxy_env

        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
        import os

        with pytest.raises(RuntimeError):
            with without_proxy_env():
                raise RuntimeError("boom")
        assert os.environ.get("HTTPS_PROXY") == "http://127.0.0.1:7897"


class TestProviderPatch:
    """网关路由 patch：三个字段缺一不可，models 必须是对象数组。

    真实报错对照（都踩过）：
      - 缺 api      → `no adapter registered for provider "fachuan"`
      - 缺 models   → `provider "fachuan" resolves no models`
      - models 写错 → `expected array but got [object Object]` / `expected object but got str`
    """

    def test_patch_declares_required_fields(self, tmp_path: object) -> None:
        from apps.agent.backends.dsh_config import _provider_patch_path

        path = _provider_patch_path(str(tmp_path), base_url="http://gw.internal:4000/v1", models=["kimi-2.6"])
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        assert "openai-completions" in text
        assert "http://gw.internal:4000/v1" in text
        assert "apiKeyEnv: DEEPSEEK_API_KEY" in text
        # models 必须是「对象数组」，每项带 id
        assert "- id:" in text

    def test_patch_quotes_are_balanced(self, tmp_path: object) -> None:
        # YAML 引号不配对会让整层解析失败，而报错落在 ini 化阶段、极难定位
        from apps.agent.backends.dsh_config import _provider_patch_path

        path = _provider_patch_path(str(tmp_path), base_url="http://a/b", models=["m"])
        with open(path, encoding="utf-8") as handle:
            lines = list(handle)
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("baseURL:") or stripped.startswith("- id:"):
                assert stripped.count('"') % 2 == 0, f"引号不配对: {stripped}"


class TestLockdownPatch:
    """安全收紧层：法务场景不允许 dsh 默认的编码 agent 能力。"""

    def _text(self, tmp_path: object) -> str:
        from apps.agent.backends.dsh_config import _lockdown_patch_path

        with open(_lockdown_patch_path(str(tmp_path)), encoding="utf-8") as handle:
            return handle.read()

    @pytest.mark.parametrize(
        "plugin_id",
        [
            "tool-bash",
            "tool-pwsh",
            "tool-fs",
            "tool-fs-search",
            "skill-filesystem",
            "agent-instructions",
            "tool-plugin-manager",
        ],
    )
    def test_dangerous_plugins_disabled(self, tmp_path: object, plugin_id: str) -> None:
        text = self._text(tmp_path)
        # 必须出现「该 id + 紧随其后 disabled: true」
        assert f"- id: {plugin_id}\n  disabled: true" in text

    def test_web_tools_disabled(self, tmp_path: object) -> None:
        # 联网必须走法穿自己的 web_search MCP 工具（可审计/可限流），
        # dsh 自带的会绕过全部约束
        text = self._text(tmp_path)
        for pid in ("web", "tool-web", "web-search-deepseek", "web-fetch-http"):
            assert f"- id: {pid}\n  disabled: true" in text

    def test_subagent_and_workflow_disabled(self, tmp_path: object) -> None:
        # 这些是「再起一个模型循环」的入口，多一层循环就多一处不受主会话审批约束的工具面
        text = self._text(tmp_path)
        for pid in ("subagent", "tool-subagent", "tool-workflow", "tool-schedule"):
            assert f"- id: {pid}\n  disabled: true" in text

    def test_lockdown_listed_before_provider_patch(self, tmp_path: object) -> None:
        """顺序有意义：收紧层必须在前，否则后面的 patch 能把红线重新打开。"""
        from apps.agent.backends.dsh_config import dsh_patches

        paths = dsh_patches(str(tmp_path), base_url="http://gw/v1", models=["m"])
        assert len(paths) >= 2
        assert "lockdown" in paths[0]
        assert "provider" in paths[1]


class TestProviderDefault:
    def test_default_provider_is_litellm_compatible(self) -> None:
        """default provider 必须走 OpenAI 兼容，而不是 DeepSeek 原生 Messages。

        实测：`deepseek-official` 打律所 LiteLLM 网关直接 502（协议不认）。
        """
        from apps.agent.backends.dsh_config import DEFAULT_API, DEFAULT_PROVIDER

        assert DEFAULT_API == "openai-completions"
        assert DEFAULT_PROVIDER == "fachuan"


# ============ 思考模式（2026-11-19 真实反馈）============


class TestThinkingConfiguration:
    """dsh 必须和 pi 一样把「思考」透传到网关。

    真实反馈：「dsh 没有开启思考强度」。排查发现 ``dsh_config`` 完全没读
    ``enable_thinking``，也没写 reasoning/compat —— 而 pi 侧（`model_config._model_entry`）
    早就踩过同一个坑：律所 LiteLLM 网关把思考开关放在
    ``chat_template_kwargs.thinking``，不显式声明 compat 时适配器会误判，
    网关不返回 reasoning_content，表现为「平台开了思考但模型永远不思考」。
    """

    def test_thinking_block_emitted_when_enabled(self, tmp_path: object) -> None:
        from apps.agent.backends.dsh_config import _provider_patch_path

        with open(
            _provider_patch_path(str(tmp_path), base_url="http://gw/v1", models=["kimi-2.6"], thinking=True),
            encoding="utf-8",
        ) as handle:
            text = handle.read()
        # 三件套缺一不可（见 _provider_patch_path 的注释）
        assert "reasoningEfforts:" in text
        assert "thinkingFormat: chat-template" in text
        assert "chatTemplateKwargs:" in text
        assert "thinking: true" in text

    def test_thinking_block_absent_when_disabled(self, tmp_path: object) -> None:
        """未开思考时不能声明能力：给普通模型错报会让网关收到它不认的参数而 400。"""
        from apps.agent.backends.dsh_config import _provider_patch_path

        with open(
            _provider_patch_path(str(tmp_path), base_url="http://gw/v1", models=["m"], thinking=False),
            encoding="utf-8",
        ) as handle:
            text = handle.read()
        assert "reasoningEfforts" not in text
        assert "chatTemplateKwargs" not in text

    def test_thinking_requires_both_switch_and_model_capability(self, tmp_path: object) -> None:
        """平台开关 + 该模型确实是推理模型，两个条件都要满足。"""
        from types import SimpleNamespace

        from apps.agent.backends import dsh_config as mod

        class _P:
            base_url = "http://gw/v1"
            api_keys = "sk-a"  # pragma: allowlist secret
            default_model = "kimi-2.6"
            extra_models = ""
            fallback_models = ""

            def __init__(self, on: bool, capable: bool) -> None:
                self.enable_thinking = on
                self._capable = capable

            def supports_thinking(self, model: str = "") -> bool:
                return self._capable

            def parsed_key_entries(self):
                return [("sk-a", [])]  # pragma: allowlist secret

        def _thinking_for(provider: object, home: object) -> bool:
            # 直接调 dsh_patches，检查生成的 patch 里有没有思考块
            paths = mod.dsh_patches(
                str(home),
                base_url="http://gw/v1",
                models=["kimi-2.6"],
                thinking=bool(
                    getattr(provider, "enable_thinking", False)
                    and getattr(provider, "supports_thinking", None)
                    and provider.supports_thinking("kimi-2.6")  # type: ignore[attr-defined]
                ),
            )
            provider_patch = [p for p in paths if "provider" in p][0]
            with open(provider_patch, encoding="utf-8") as handle:
                return "thinkingFormat" in handle.read()

        assert _thinking_for(_P(True, True), tmp_path) is True
        assert _thinking_for(_P(True, False), tmp_path) is False
        assert _thinking_for(_P(False, True), tmp_path) is False


class TestMultiTurnResume:
    """同一 AgentSession 的第二轮必须走 resume，不能重新 start_session。

    真实事故（2026-11-19）：律师第二次发言时后端报
    ``deepseek_harness.errors.JsonRpcError: session "<uuid>" already exists``，
    SSE 直接断流。根因是 ``harness.run(prompt, session_id=...)`` 内部走
    ``start_session()``，而 dsh 把会话**持久化在磁盘**上——第二轮必然撞号。
    """

    def test_second_turn_uses_resume_not_start(self) -> None:
        """生产代码必须先 resume_session 再 run（否则第二轮必炸）。"""
        import inspect

        from apps.agent.backends import dsh_backend as mod

        # `_stream` 里嵌套了 `_run_blocking`，`getsource(_stream)` 拿不到那段，
        # 所以查整个模块的源码。
        src = inspect.getsource(mod)
        assert "harness.resume_session(session_id).run(" in src, "生产路径必须用 resume_session 续跑已有会话"
        # 反向断言：不能再出现裸 `harness.run(..., session_id=...)`（那是撞号的老写法）
        assert "harness.run(ctx.prompt, session_id=session_id" not in src

    def test_stub_exposes_both_paths(self) -> None:
        """桩与真 SDK 同形：resume_session 与 start_session 都存在。"""
        stub = _StubHarness([])
        assert hasattr(stub, "resume_session")
        assert hasattr(stub, "start_session")
        # resume 出来的 Session 能直接 run
        called: list[str] = []

        class _H(_StubHarness):
            def run(self, prompt: str, *, session_id: str, on_notification: Any) -> None:
                called.append(prompt)

        _H([]).resume_session("s-1").run("hello", on_notification=lambda _n: None)
        assert called == ["hello"]
