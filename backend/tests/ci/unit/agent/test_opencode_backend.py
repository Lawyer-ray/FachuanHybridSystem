"""``OpenCodeBackend`` —— 第六个 agent 后端的接缝、事件翻译、审批闸门与故障注入。

全部离线（不打真网关、不连共享 MCP、不起 opencode 子进程）：

1. **身份与能力声明**：``kind == "opencode"``，六项能力如实；``approval`` 与
   :data:`APPROVAL_ENV` 同源（声明错了前端会渲染出不存在的控件，或者反过来
   有闸门却不敢显示）。
2. **结构化满足协议**：``isinstance(OpenCodeBackend(), AgentBackend)``。
3. **事件翻译**：``agent_message_chunk`` / ``agent_thought_chunk`` → ``delta`` /
   ``thinking``；``tool_call`` 只在首次出现时发；``tool_call_update`` 只在
   ``completed`` / ``failed`` 时补 ``tool_result``；被审批拒掉的不重复发。
4. **工具名归一化**：``fachuan_delete_case`` → ``mcp__fachuan__delete_case``。
   这条不做，四级审批会把写类工具判成低风险（静默失效家族）。
5. **审批闸门**：认不出名字 / 内置工具一律 fail-closed；HIGH 走
   ``request_approval``；拒绝要**自己补一条** ``is_error`` 的 ``tool_result``。
6. **配置生成**：``agent.tools`` 把 14 个内置工具全关、``permission`` 为 ``ask``、
   provider 段全部来自入参（不写死模型名）。
7. **故障注入**：二进制不存在 → ``UNAVAILABLE``；JSON-RPC error → 鉴权/限流/超窗
   三类分类正确。
8. **用户中止不是错误**：``_pump`` 被取消时发 ``session/cancel`` 并把
   ``CancelledError`` 原样上抛（包成 ``BackendError`` 会让成功率统计失真）。
9. **收尾事实**：``result_for`` 能取到模型名（``AgentRun.model`` 靠它回写），
   并且有界（不会无限增长）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from apps.agent.backends import opencode_backend as mod
from apps.agent.backends import registry
from apps.agent.backends.base import AgentBackend, BackendError, BackendErrorKind, RunContext

pytestmark = pytest.mark.usefixtures("_no_env_leak")


@pytest.fixture()
def _no_env_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认把审批开关置回「开」，避免跑测试的机器上设了 0 导致用例时好时坏。"""
    monkeypatch.delenv(mod.APPROVAL_ENV, raising=False)


def _ctx(**kw: Any) -> RunContext:
    """造一个最小 RunContext（后端只读 session_id / user_id / prompt / user_token）。"""
    base: dict[str, Any] = {
        "run_id": "run-test-1",
        "session": SimpleNamespace(session_id="sess-test-1"),
        "user_id": 1,
        "prompt": "hello",
        "user_token": "tok",
        "model": None,
        "tool_selection": None,
    }
    base.update(kw)
    return RunContext(**base)


class TestIdentityAndCapabilities:
    """身份与能力声明。"""

    def test_kind_is_stable(self) -> None:
        """``kind`` 会进事件流、进 AgentRun 归因，改名等于历史数据对不上。"""
        assert mod.OpenCodeBackend().kind == "opencode"

    def test_capabilities_are_facts(self) -> None:
        caps = mod.backend_capabilities()
        assert caps.streaming is True
        assert caps.tool_calls is True
        assert caps.compaction is True  # 会话历史归 opencode 自己管
        assert caps.steer is False  # ACP 只有 session/cancel
        assert caps.concurrent_in_session is True

    def test_approval_capability_follows_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """开关关了就不能再声明「有闸门」——两处各写一份必然说谎。"""
        monkeypatch.setenv(mod.APPROVAL_ENV, "0")
        assert mod.approval_enabled() is False
        assert mod.backend_capabilities().approval is False
        monkeypatch.setenv(mod.APPROVAL_ENV, "1")
        assert mod.backend_capabilities().approval is True

    def test_satisfies_protocol(self) -> None:
        assert isinstance(mod.OpenCodeBackend(), AgentBackend)


class TestToolNameNormalization:
    """工具名归一化：opencode 用 ``fachuan_x``，审批口径要求 ``mcp__fachuan__x``。"""

    def test_mcp_tool(self) -> None:
        assert mod.normalize_tool_name("fachuan_delete_case") == ("delete_case", "mcp__fachuan__delete_case")

    def test_unknown_title_is_rejected(self) -> None:
        """bash 的 title 是命令原文（"echo hi"），认不出工具名时必须返回空 → fail-closed。"""
        assert mod.normalize_tool_name("echo hello-probe") == ("", "")

    def test_builtin_tool_keeps_short_name(self) -> None:
        assert mod.normalize_tool_name("bash") == ("bash", "bash")

    def test_other_server_prefix(self) -> None:
        short, full = mod.normalize_tool_name("other__some_tool")
        assert short == "some_tool"
        assert full == "other__some_tool"


class TestTranslate:
    """事件翻译（纯函数级：构造 ACP 通知，断言产出帧）。"""

    def setup_method(self) -> None:
        self.backend = mod.OpenCodeBackend()
        self.state = mod._RunState()

    @staticmethod
    def _update(**kw: Any) -> dict[str, Any]:
        return {"params": {"update": kw}}

    def test_text_chunk_to_delta(self) -> None:
        frames = self.backend._translate(self._update(sessionUpdate="agent_message_chunk", content={"text": "你好"}), self.state)
        assert frames == [{"type": "delta", "content": "你好"}]

    def test_thought_chunk_to_thinking(self) -> None:
        frames = self.backend._translate(self._update(sessionUpdate="agent_thought_chunk", content={"text": "想"}), self.state)
        assert frames == [{"type": "thinking", "content": "想"}]

    def test_empty_text_produces_nothing(self) -> None:
        assert self.backend._translate(self._update(sessionUpdate="agent_message_chunk", content={}), self.state) == []

    def test_tool_call_only_once(self) -> None:
        update = {"sessionUpdate": "tool_call", "toolCallId": "c1", "title": "fachuan_asean_law_search", "rawInput": {"keyword": "投资"}}
        first = self.backend._translate(self._update(**update), self.state)
        assert first[0]["type"] == "tool_call"
        assert first[0]["name"] == "asean_law_search"
        assert "投资" in (first[0]["arguments"] or "")
        # 同 id 再来一次不重复发
        assert self.backend._translate(self._update(**update), self.state) == []

    def test_tool_call_update_completed_to_result(self) -> None:
        self.backend._translate(self._update(**{"sessionUpdate": "tool_call", "toolCallId": "c2", "title": "fachuan_x"}), self.state)
        frames = self.backend._translate(
            self._update(
                sessionUpdate="tool_call_update",
                toolCallId="c2",
                status="completed",
                content=[{"type": "content", "content": {"type": "text", "text": "ok"}}],
            ),
            self.state,
        )
        assert frames == [{"type": "tool_result", "tool_call_id": "c2", "name": "x", "result": "ok", "is_error": False}]

    def test_in_progress_update_produces_nothing(self) -> None:
        assert self.backend._translate(self._update(sessionUpdate="tool_call_update", toolCallId="c3", status="in_progress"), self.state) == []

    def test_denied_tool_result_not_duplicated(self) -> None:
        """审批已拒：拒绝文案发过了，opencode 的 failed update 不再补一条。"""
        self.state.denied.add("c4")
        frames = self.backend._translate(self._update(sessionUpdate="tool_call_update", toolCallId="c4", status="failed"), self.state)
        assert frames == []

    def test_unknown_update_ignored(self) -> None:
        assert self.backend._translate(self._update(sessionUpdate="available_commands_update"), self.state) == []


class TestUsage:
    """用量帧。"""

    def test_records_and_frames(self) -> None:
        state = mod._RunState()
        mod.OpenCodeBackend._record_usage(state, {"inputTokens": 80810, "outputTokens": 12, "cachedReadTokens": 3712})
        frame = mod.OpenCodeBackend._usage_frame(state)
        assert frame == {
            "type": "usage",
            "input_tokens": 80810,
            "output_tokens": 12,
            "cache_read_tokens": 3712,
            "cache_write_tokens": 0,
        }

    def test_zero_usage_is_not_reported(self) -> None:
        """全 0 时宁可不报，也不要报一个假的 0（成本账会被当成真实值）。"""
        assert mod.OpenCodeBackend._usage_frame(mod._RunState()) is None


class TestConfig:
    """写进 ``opencode.json`` 的配置。"""

    def test_provider_comes_from_arguments(self) -> None:
        cfg = mod.build_provider_config(base_url="http://gw/v1", api_key="k", model="kimi-2.6", models=["glm53"])
        provider = cfg["provider"][mod.SERVER_NAME]
        assert provider["options"] == {"baseURL": "http://gw/v1", "apiKey": "k"}
        assert cfg["model"] == f"{mod.SERVER_NAME}/kimi-2.6"
        assert "glm53" in provider["models"]

    def test_agent_disables_all_builtin_tools(self) -> None:
        payload = mod.OpenCodeBackend()._config_payload({"base_url": "u", "api_key": "k", "model": "m", "models": []})
        agent = payload["agent"][mod.FACHUAN_AGENT]
        assert agent["mode"] == "primary"
        assert set(agent["tools"]) == set(mod.BUILTIN_TOOLS)
        assert all(value is False for value in agent["tools"].values())

    def test_permission_is_ask_when_approval_on(self) -> None:
        payload = mod.OpenCodeBackend()._config_payload({"base_url": "u", "api_key": "k", "model": "m", "models": []})
        assert payload["permission"] == {"*": "ask"}

    def test_permission_is_allow_when_approval_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(mod.APPROVAL_ENV, "0")
        payload = mod.OpenCodeBackend()._config_payload({"base_url": "u", "api_key": "k", "model": "m", "models": []})
        assert payload["permission"] == {"*": "allow"}

    def test_env_strips_proxy(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """内网网关 + Clash = 「502 无 body」，代理必须在子进程环境里被剔掉。"""
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
        monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:7890")
        env = mod.build_env(tmp_path)
        lowered = {k.lower() for k in env}
        assert "https_proxy" not in lowered
        assert "all_proxy" not in lowered
        assert env["NO_PROXY"] == "*"
        assert env["XDG_CONFIG_HOME"].startswith(str(tmp_path))
        assert env["XDG_DATA_HOME"].startswith(str(tmp_path))


class TestMcpServers:
    """共享 MCP 的挂载参数。"""

    def test_carries_token_session_and_tier(self) -> None:
        servers = mod.OpenCodeBackend()._mcp_servers(_ctx(), "sess-9")
        assert len(servers) == 1
        server = servers[0]
        assert server["type"] == "http"
        assert server["name"] == mod.SERVER_NAME
        headers = {h["name"]: h["value"] for h in server["headers"]}
        assert headers["Authorization"] == "Bearer tok"
        assert headers[mod.SESSION_HEADER] == "sess-9"
        assert headers[mod.TOOL_TIER_HEADER] in {mod.TIER_FULL, mod.TIER_LITE}

    def test_no_token_means_no_tool_face(self) -> None:
        """没有律师凭证就不挂工具面：宁可「能对话但没工具」，也不能退回服务账号。"""
        assert mod.OpenCodeBackend()._mcp_servers(_ctx(user_token=""), "sess-9") == []


class TestDecide:
    """审批决策（``session/request_permission`` → once / reject）。"""

    def setup_method(self) -> None:
        self.backend = mod.OpenCodeBackend()
        self.state = mod._RunState()
        self.ctx = _ctx()

    @staticmethod
    def _params(title: str, call_id: str = "c1") -> dict[str, Any]:
        return {"toolCall": {"toolCallId": call_id, "title": title}}

    def test_unknown_name_fails_closed(self) -> None:
        outcome = asyncio.run(self.backend._decide(self.ctx, self.state, self._params("echo hi")))
        assert outcome == mod._reject_outcome()
        assert "c1" in self.state.denied

    def test_builtin_tool_rejected(self) -> None:
        outcome = asyncio.run(self.backend._decide(self.ctx, self.state, self._params("bash")))
        assert outcome == mod._reject_outcome()

    def test_low_risk_allowed_without_asking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []

        async def _boom(**kw: Any) -> Any:
            called.append(kw.get("tool_name", ""))
            raise AssertionError("低风险不该找律师确认")

        monkeypatch.setattr("apps.agent.services.approval.request_approval", _boom)
        outcome = asyncio.run(self.backend._decide(self.ctx, self.state, self._params("fachuan_asean_law_countries")))
        assert outcome == mod._allow_outcome()
        assert called == []

    def test_high_risk_approved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        asked: list[str] = []

        async def _approve(**kw: Any) -> tuple[bool, str, str]:
            asked.append(kw["tool_name"])
            return True, "aid", "ok"

        monkeypatch.setattr("apps.agent.services.approval.request_approval", _approve)
        outcome = asyncio.run(self.backend._decide(self.ctx, self.state, self._params("fachuan_delete_case")))
        assert outcome == mod._allow_outcome()
        # 审批用的必须是归一化后的全名，否则四级判定落空
        assert asked == ["mcp__fachuan__delete_case"]

    def test_high_risk_rejected_queues_tool_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _reject(**kw: Any) -> tuple[bool, str, str]:
            return False, "", "no"

        monkeypatch.setattr("apps.agent.services.approval.request_approval", _reject)
        outcome = asyncio.run(self.backend._decide(self.ctx, self.state, self._params("fachuan_delete_case")))
        assert outcome == mod._reject_outcome()
        assert "c1" in self.state.denied
        assert len(self.state.pending) == 1
        frame = self.state.pending[0]
        assert frame["type"] == "tool_result"
        assert frame["is_error"] is True
        assert frame["result"] == mod.APPROVAL_REJECTED_MESSAGE

    def test_approval_off_allows_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(mod.APPROVAL_ENV, "0")
        outcome = asyncio.run(self.backend._decide(self.ctx, self.state, self._params("fachuan_delete_case")))
        assert outcome == mod._allow_outcome()


class TestFailureInjection:
    """故障注入：错误分类与「装没装」。"""

    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            ("401 unauthorized", BackendErrorKind.AUTH),
            ("403 Forbidden", BackendErrorKind.AUTH),
            ("429 rate limit exceeded", BackendErrorKind.RATE_LIMITED),
            ("context length exceeded: too many token", BackendErrorKind.CONTEXT_OVERFLOW),
            ("boom", BackendErrorKind.UNKNOWN),
        ],
    )
    def test_error_classification(self, message: str, expected: BackendErrorKind) -> None:
        error = mod._error_from_jsonrpc("session/prompt", {"message": message})
        assert error.kind == expected
        assert isinstance(error, BackendError)

    def test_rate_limited_is_retryable(self) -> None:
        assert mod._error_from_jsonrpc("x", {"message": "429"}).retryable is True

    def test_missing_binary_is_unavailable(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        """二进制不在 → UNAVAILABLE（不是 UNKNOWN），前端才能给出「联系管理员」。"""
        monkeypatch.setenv(mod.BIN_ENV, str(tmp_path / "definitely-missing-opencode"))
        backend = mod.OpenCodeBackend()
        with pytest.raises(BackendError) as excinfo:
            asyncio.run(anull(backend._spawn(tmp_path)))
        assert excinfo.value.kind == BackendErrorKind.UNAVAILABLE

    def test_is_available_false_for_missing_binary(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.setenv(mod.BIN_ENV, str(tmp_path / "nope"))
        assert mod.is_available() is False


async def anull(coro: Any) -> None:
    """把协程跑完（只为触发异常），返回值丢弃。"""
    await coro


class _FakeConn:
    """``_AcpConnection`` 的最小替身：只实现 ``_pump`` 用到的三个方法。

    ``next_event`` 故意**永远挂起**（等一个不会被 set 的 Event）：这样生成器会停在
    ``await`` 上，取消才有落点。返回 ``None`` 会让 ``__anext__`` 立刻带着 ``None``
    结束——测的就不再是「取消」，而是「空 tick 让位」。
    """

    def __init__(self) -> None:
        self.notified: list[tuple[str, dict[str, Any]]] = []
        self.replied = asyncio.Event()
        self._no_events = asyncio.Event()

    async def request(self, method: str, params: dict[str, Any], *, timeout: float = 0) -> dict[str, Any]:
        await self.replied.wait()
        return {}

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        self.notified.append((method, params))
        self.replied.set()

    async def next_event(self) -> dict[str, Any] | None:
        await self._no_events.wait()
        return None


class TestCancel:
    """用户按停止：发 ``session/cancel``，异常原样上抛。"""

    def test_cancel_sends_session_cancel_and_propagates(self) -> None:
        backend = mod.OpenCodeBackend()
        conn = _FakeConn()
        state = mod._RunState()

        async def scenario() -> None:
            agen = backend._pump(_ctx(), conn, "sess-1", state)
            task = asyncio.ensure_future(agen.__anext__())
            # 让生成器跑到 ``await conn.next_event()`` 上挂住，取消才有意义
            await asyncio.sleep(0.05)
            assert task.done() is False
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())
        assert conn.notified and conn.notified[0][0] == "session/cancel"
        assert conn.notified[0][1] == {"sessionId": "sess-1"}


class TestResultFor:
    """收尾事实（``AgentRun.model`` 与 ``AgentSession.llm_model`` 靠它回写）。"""

    def test_result_roundtrip_and_bound(self) -> None:
        backend = mod.OpenCodeBackend()
        backend._remember_result("r1", mod.OpenCodeRunResult(model="kimi-2.6"))
        assert backend.result_for("r1") is not None
        assert backend.result_for("r1").model == "kimi-2.6"
        assert backend.result_for("missing") is None
        for i in range(mod.MAX_KEPT_RESULTS + 5):
            backend._remember_result(f"x{i}", mod.OpenCodeRunResult(model="m"))
        assert len(backend._results) == mod.MAX_KEPT_RESULTS


class TestRegistration:
    """注册表接线。"""

    def test_registered_after_ensure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "is_available", lambda: True)
        registry.clear()
        try:
            from apps.agent.backends import builtin

            builtin._attempted.discard("opencode")
            builtin.ensure_registered()
            assert "opencode" in registry.available_kinds()
        finally:
            registry.clear()
            builtin._registered = False
