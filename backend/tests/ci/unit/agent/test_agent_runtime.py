"""apps.agent 单元测试。

覆盖三块：
1. 事件翻译（pi 记录 → 前端 SSE 事件）
2. 高危工具判定与两层清单一致性
3. 事件总线（按会话分发、多订阅、积压保护）
"""

from __future__ import annotations

import pytest

from apps.agent.pi.bridge import DeltaTracker, translate
from apps.agent.pi.rpc_client import PiEvent


def _ev(kind: str, **raw: object) -> PiEvent:
    return PiEvent(kind, dict(raw))


class TestTranslate:
    def test_message_update_yields_delta(self) -> None:
        event = _ev(
            "event",
            type="message_update",
            assistantMessageEvent={"type": "text_delta", "delta": "你好"},
        )
        assert translate(event, tracker=DeltaTracker()) == {"type": "delta", "content": "你好"}

    def test_empty_delta_dropped(self) -> None:
        event = _ev("event", type="message_update", assistantMessageEvent={"delta": ""})
        assert translate(event, tracker=DeltaTracker()) is None

    def test_thinking_delta_becomes_thinking_event(self) -> None:
        """开启思考模式后 pi 推 thinking_delta，必须转成独立的 thinking 事件。"""
        event = _ev(
            "event",
            type="message_update",
            assistantMessageEvent={"type": "thinking_delta", "delta": "先分析当事人主体资格"},
        )
        assert translate(event, tracker=DeltaTracker()) == {
            "type": "thinking",
            "content": "先分析当事人主体资格",
        }

    def test_thinking_delta_does_not_consume_text_watermark(self) -> None:
        """思考内容不得推高正文水位，否则后续正文会被 diff 吞掉。"""
        tracker = DeltaTracker()
        think = _ev(
            "event",
            type="message_update",
            assistantMessageEvent={"type": "thinking_delta", "delta": "思考若干字"},
        )
        assert translate(think, tracker=tracker) is not None
        text = _ev("event", type="message_update", assistantMessageEvent={"type": "text_delta", "delta": "结论"})
        assert translate(text, tracker=tracker) == {"type": "delta", "content": "结论"}

    def test_empty_thinking_delta_dropped(self) -> None:
        event = _ev("event", type="message_update", assistantMessageEvent={"type": "thinking_delta", "delta": ""})
        assert translate(event, tracker=DeltaTracker()) is None

    def test_tool_call_maps_fields(self) -> None:
        event = _ev("event", type="tool_call", toolCallId="c1", toolName="delete_case", input={"case_id": 1})
        out = translate(event)
        assert out is not None
        assert out["type"] == "tool_call"
        assert out["name"] == "delete_case"
        assert out["tool_call_id"] == "c1"
        assert out["arguments"] == {"case_id": 1}

    def test_tool_result_truncated(self) -> None:
        event = _ev("event", type="tool_result", toolCallId="c1", toolName="x", result="a" * 5000)
        out = translate(event)
        assert out is not None
        assert len(out["result"]) == 2000

    def test_agent_start_becomes_activity(self) -> None:
        assert translate(_ev("event", type="agent_start"), agent="pi") == {
            "type": "activity",
            "status": "thinking",
            "agent": "pi",
        }

    def test_error_passthrough(self) -> None:
        assert translate(_ev("event", type="error", message="boom")) == {"type": "error", "message": "boom"}

    def test_unknown_event_dropped(self) -> None:
        assert translate(_ev("event", type="internal_noise")) is None

    def test_extension_ui_not_forwarded(self) -> None:
        """审批走独立 HTTP 通道，extension UI 不应泄漏到前端。"""
        assert translate(_ev("extension_ui", method="select")) is None


class TestApprovalPolicy:
    def test_high_risk_detection(self) -> None:
        from apps.agent.services.approval import is_high_risk

        assert is_high_risk("mcp__fachuan__delete_case")
        assert is_high_risk("mcp__fachuan__delete_lawyer")  # 旧名单漏掉的 31 个 delete_* 之一
        assert is_high_risk("mcp__fachuan__submit_court_sms")
        assert is_high_risk("mcp__fachuan__upload_invoices")
        assert is_high_risk("mcp__fachuan__confirm_archive")
        assert is_high_risk("mcp__fachuan__clear_all_archive_materials")
        assert not is_high_risk("mcp__fachuan__list_cases")
        assert not is_high_risk("mcp__fachuan__get_case")
        assert not is_high_risk("mcp__fachuan__create_case")  # 常规业务写不拦
        assert not is_high_risk("mcp__fachuan__sync_lpr_rates")  # 拉取/同步不拦

    def test_only_approved_is_granted(self) -> None:
        """fail-closed：只有 approved 放行。"""
        from apps.agent.models import AgentApproval

        for status in AgentApproval.Status:
            approval = AgentApproval(status=status)
            expected = status == AgentApproval.Status.APPROVED
            assert approval.is_granted is expected, status

    def test_server_and_extension_patterns_in_sync(self) -> None:
        """服务端与服务端两侧的模式清单必须一致，防止两侧脱节。"""
        import re
        from pathlib import Path

        from apps.agent.services.approval import DANGER_PATTERNS

        extension = Path(__file__).resolve().parents[4] / "apps" / "agent" / "pi" / "approval-gate.ts"
        source = extension.read_text(encoding="utf-8")
        match = re.search(r"HIGH_RISK_PATTERNS: readonly string\[\] = \[(.*?)\]", source, re.S)
        assert match is not None, "approval-gate.ts 缺少 HIGH_RISK_PATTERNS 定义"
        ts_patterns = re.findall(r'"([^"]+)"', match.group(1))
        assert set(ts_patterns) == set(DANGER_PATTERNS), (
            f"两侧模式清单不一致: ts={sorted(ts_patterns)} py={sorted(DANGER_PATTERNS)}"
        )

    def test_danger_patterns_cover_mcp_registry(self) -> None:
        """注册表对账：mcp_server 里每一个删除类工具都必须被审批模式拦住。

        旧清单 6 个名字有 3 个在 378 个工具里不存在、39 个 delete_* 只拦住
        8 个——名单是拍脑袋写的。此测试让「新增 delete_xxx 工具忘了进审批」
        变成红灯，而不是静默免审批。
        """
        import asyncio
        import re

        from apps.agent.services.approval import is_high_risk
        from mcp_server.server import mcp

        tools = asyncio.run(mcp.list_tools())
        names = [t.name for t in tools]
        assert len(names) > 300, "mcp 工具注册表加载异常"

        destructive = re.compile(r"delete|remove|destroy")
        uncovered = [n for n in names if destructive.search(n) and not is_high_risk(f"mcp__fachuan__{n}")]
        assert not uncovered, f"删除类工具脱离审批: {uncovered}"

        external = re.compile(r"^send_|^submit_|^upload_|^file_|^confirm_|clear_all|reset_and_")
        uncovered_ext = [n for n in names if external.search(n) and not is_high_risk(f"mcp__fachuan__{n}")]
        assert not uncovered_ext, f"外发/递交/批量类工具脱离审批: {uncovered_ext}"


class TestEventBus:
    @pytest.mark.asyncio
    async def test_publish_reaches_subscriber(self) -> None:
        from apps.agent.services.event_bus import EventBus

        bus = EventBus()
        queue = await bus.register("s1")
        delivered = await bus.publish("s1", {"type": "approval_request"})
        assert delivered == 1
        assert await queue.get() == {"type": "approval_request"}

    @pytest.mark.asyncio
    async def test_publish_unknown_session_is_noop(self) -> None:
        from apps.agent.services.event_bus import EventBus

        bus = EventBus()
        assert await bus.publish("missing", {"type": "x"}) == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive(self) -> None:
        from apps.agent.services.event_bus import EventBus

        bus = EventBus()
        q1 = await bus.register("s1")
        q2 = await bus.register("s1")
        assert await bus.publish("s1", {"type": "x"}) == 2
        assert await q1.get() == {"type": "x"}
        assert await q2.get() == {"type": "x"}

    @pytest.mark.asyncio
    async def test_redis_client_helper_tolerates_both_layouts(self) -> None:
        """回归：Django 5.x 的 RedisCache 没有 ``cache.client``。

        早期写成 ``cache.client.get_client()``，在 Django 5 上直接 AttributeError，
        异常被吞后跨进程分发全程静默失效（表现为「审批在别的 worker 收不到」）。
        """
        from apps.agent.services.event_bus import _redis_client

        # 当前项目用 Redis，能拿到客户端；拿不到也只应是 RuntimeError（明确报错）
        client = None
        try:
            client = _redis_client()
        except RuntimeError:
            pytest.skip("当前缓存后端不是 Redis")
        assert client is not None and hasattr(client, "lrange")

    @pytest.mark.asyncio
    async def test_unregister_stops_delivery(self) -> None:
        from apps.agent.services.event_bus import EventBus

        bus = EventBus()
        queue = await bus.register("s1")
        await bus.unregister("s1", queue)
        assert await bus.publish("s1", {"type": "x"}) == 0
        assert await bus.subscriber_count("s1") == 0


class TestSharedMcp:
    def test_endpoint_url_shape(self) -> None:
        from apps.agent.pi.shared_mcp import McpEndpoint

        assert McpEndpoint().url == "http://127.0.0.1:8011/mcp"
        assert McpEndpoint(host="0.0.0.0", port=9000).url == "http://0.0.0.0:9000/mcp"

    def test_shared_enabled_default_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.pi import shared_mcp

        monkeypatch.delenv(shared_mcp.SHARED_ENV, raising=False)
        assert shared_mcp.shared_enabled() is True

    def test_shared_can_be_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.pi import shared_mcp

        monkeypatch.setenv(shared_mcp.SHARED_ENV, "0")
        assert shared_mcp.shared_enabled() is False


class TestDeltaTracker:
    """回归：pi 同时给 message_update 的 delta 与 message_end 的全文，
    若两处都直接发会导致同一段文本重复（实测「全链路联调成功」被推 3 次）。"""

    def test_note_then_diff_does_not_repeat(self) -> None:
        tracker = DeltaTracker()
        tracker.note("联")
        tracker.note("调OK")
        # message_end 给全文，水位已到 3，不应再发
        assert tracker.diff("联调OK") == ""

    def test_diff_emits_only_new_tail(self) -> None:
        tracker = DeltaTracker()
        tracker.note("联")
        assert tracker.diff("联调OK") == "调OK"

    def test_empty_full_text_returns_empty(self) -> None:
        assert DeltaTracker().diff("") == ""


class TestCleanEnv:
    """回归：Django 继承的 PI_* 与环境代理会破坏 pi 子进程。"""

    def test_strips_pi_model_and_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.pi.rpc_client import _clean_env

        monkeypatch.setenv("PI_MODEL", "magpie/x")
        monkeypatch.setenv("PI_PROVIDER", "magpie")
        monkeypatch.setenv("PI_SESSION_ID", "abc")
        env = _clean_env()
        assert "PI_MODEL" not in env
        assert "PI_PROVIDER" not in env
        assert "PI_SESSION_ID" not in env

    def test_strips_proxy_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """内网 LLM 网关经代理会 Connection error，必须剔除。"""
        from apps.agent.pi.rpc_client import _clean_env

        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7897")
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
        monkeypatch.setenv("https_proxy", "http://127.0.0.1:7897")
        env = _clean_env()
        assert "HTTP_PROXY" not in env
        assert "HTTPS_PROXY" not in env
        assert "https_proxy" not in env

    def test_keeps_unrelated_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.pi.rpc_client import _clean_env

        monkeypatch.setenv("FACHUAN_TEST_KEEP", "yes")
        assert _clean_env().get("FACHUAN_TEST_KEEP") == "yes"


class TestToolRestriction:
    """红线：pi 内置 bash/edit/write 不得向模型声明（提示注入 → 服务器 RCE 面）。"""

    def test_tool_selection_excludes_dangerous_builtins(self) -> None:
        """断言**红线本身**（而不是精确字符串）：危险内置工具一个都不能出现。

        为什么不再断言 ``== "mcp__fachuan__*"``：工具面分层后需要额外列出
        ``tool_search``（否则 350+ 个 deferred 工具永远不可达）。但 ``tool_search``
        只做工具发现，不提供文件系统或 shell 能力，不构成新攻击面。
        真正要守的是「哪些工具不得出现」，那才是安全属性。
        """
        from apps.agent.pi.rpc_client import TOOL_SELECTION

        entries = {part.strip() for part in TOOL_SELECTION.split(",")}
        dangerous = {"read", "bash", "edit", "write", "powershell", "grep", "find", "ls"}
        leaked = entries & dangerous
        assert not leaked, (
            f"危险内置工具被声明给模型了: {sorted(leaked)}——它们能以 Django 进程权限读写文件/执行命令，且不在审批清单内"
        )
        assert "mcp__fachuan__*" in entries, "法穿业务工具必须整体声明"

    def test_tool_selection_allows_tool_search(self) -> None:
        """分层生效时必须能搜索 deferred 工具，否则长尾 350+ 工具不可达。"""
        from apps.agent.pi.rpc_client import TOOL_SELECTION

        assert "tool_search" in TOOL_SELECTION, "缺少 tool_search：deferred 工具将永远无法被模型发现"

    def test_tool_selection_is_allowlist_not_delta(self) -> None:
        """不得用 ``+name``/``-name`` 形式——那是「改默认选择」，会保留 bash 等内置。"""
        from apps.agent.pi.rpc_client import TOOL_SELECTION

        entries = [part.strip() for part in TOOL_SELECTION.split(",") if part.strip()]
        assert not any(e.startswith(("+", "-")) for e in entries), (
            "``--tools`` 用 +name/-name 形式会保留内置工具，必须用 allowlist"
        )

    @pytest.mark.asyncio
    async def test_start_refuses_missing_extension(self) -> None:
        """审批 extension 缺失时 fail-closed 拒绝启动，而不是告警后裸奔。"""
        from apps.agent.pi.rpc_client import PiError, PiRpcSession

        session = PiRpcSession(cwd=".", extension_path="/nonexistent/approval-gate.ts")
        with pytest.raises(PiError, match="审批 extension"):
            await session.start()


class TestTranslateAll:
    """一条 pi 记录可产出多个事件；水位按 assistant 消息边界复位。"""

    def test_text_and_tool_call_both_emitted(self) -> None:
        """assistant 消息同时带文本和工具调用时两件事都要发（曾只发文本吞掉工具）。"""
        from apps.agent.pi.bridge import translate_all

        event = _ev(
            "event",
            type="message_end",
            message={
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "先查一下案件"},
                    {"type": "toolCall", "id": "c1", "name": "get_case", "input": {"id": 1}},
                ],
            },
        )
        events = translate_all(event, tracker=DeltaTracker())
        assert [e["type"] for e in events] == ["delta", "tool_call"]
        assert events[1]["name"] == "get_case"

    def test_tracker_resets_between_assistant_messages(self) -> None:
        """工具循环里第二段 assistant 文本比第一段短时，不能被旧水位吞掉。"""
        from apps.agent.pi.bridge import translate_all

        tracker = DeltaTracker()
        first = translate_all(
            _ev("event", type="message_end", message={"role": "assistant", "content": "第一段较长的回答"}),
            tracker=tracker,
        )
        assert first and first[0]["content"] == "第一段较长的回答"

        translate_all(_ev("event", type="message_start", message={"role": "assistant"}), tracker=tracker)

        second = translate_all(
            _ev("event", type="message_end", message={"role": "assistant", "content": "短的"}),
            tracker=tracker,
        )
        assert second and second[0]["content"] == "短的"


class TestUsagePassthrough:
    def test_message_end_with_usage_emits_usage_event(self) -> None:
        """assistant message_end 带 usage：delta/usage 并存都要发（token 精确计数）。"""
        from apps.agent.pi.bridge import DeltaTracker, translate_all

        event = PiEvent(
            "event",
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "答案"}],
                    "usage": {"input": 120, "output": 8, "totalTokens": 128},
                },
            },
        )
        events = translate_all(event, tracker=DeltaTracker())
        assert [e["type"] for e in events] == ["delta", "usage"]
        assert events[1]["output_tokens"] == 8
        assert events[1]["input_tokens"] == 120

    def test_usage_missing_or_nonnumeric_dropped(self) -> None:
        from apps.agent.pi.bridge import DeltaTracker, translate_all

        for usage in (None, {}, {"input": 3}):
            event = PiEvent(
                "event",
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "答案"}],
                        "usage": usage,
                    },
                },
            )
            assert all(e["type"] != "usage" for e in translate_all(event, tracker=DeltaTracker()))


class TestHistoryTranscript:
    """多轮上下文渲染：无历史不包壳、超预算丢最旧。"""

    @staticmethod
    def _msg(role: str, content: str, tool_name: str = "") -> object:
        from types import SimpleNamespace

        return SimpleNamespace(role=role, content=content, tool_name=tool_name)

    def test_no_history_returns_raw_message(self) -> None:
        from apps.agent.services.history import render_transcript

        assert render_transcript([], "你好") == "你好"

    def test_history_wrapped_with_labels(self) -> None:
        from apps.agent.services.history import render_transcript

        messages = [
            self._msg("user", "查案件"),
            self._msg("assistant", "已查到"),
            self._msg("tool", "案号（2026）示例", tool_name="get_case"),
        ]
        out = render_transcript(messages, "继续")
        assert "【历史对话】" in out
        assert "【最新用户消息】" in out
        assert "用户: 查案件" in out
        assert "助手: 已查到" in out
        assert "工具[get_case]" in out
        assert out.endswith("继续")

    def test_over_budget_drops_oldest_keeps_latest(self) -> None:
        from apps.agent.services.history import render_transcript

        messages = [
            self._msg("user", "a" * 100),
            self._msg("assistant", "b" * 100),
            self._msg("user", "最新问题"),
        ]
        out = render_transcript(messages, "最新问题", total_limit=150)
        assert "a" * 100 not in out  # 最旧的被丢
        assert "b" * 100 in out or "最新问题" in out

    def test_per_message_truncated(self) -> None:
        from apps.agent.services.history import render_transcript

        messages = [self._msg("assistant", "x" * 500)]
        out = render_transcript(messages, "问", per_message_limit=100)
        assert "x" * 100 in out
        assert "x" * 101 not in out


class TestAgentsMd:
    """系统提示词注入：pi 无条件读取工作目录的 AGENTS.md。"""

    def test_writes_bundled_template(self, tmp_path: object) -> None:
        from pathlib import Path

        from apps.agent.pi.shared_mcp import _write_agents_md

        target = Path(str(tmp_path))
        _write_agents_md(target)
        content = (target / "AGENTS.md").read_text(encoding="utf-8")
        assert "法穿" in content
        assert "mcp__fachuan__" in content

    def test_env_override(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        from pathlib import Path

        from apps.agent.pi.shared_mcp import _write_agents_md

        custom = Path(str(tmp_path)) / "custom.md"
        custom.write_text("自定义人格", encoding="utf-8")
        monkeypatch.setenv("FACHUAN_PI_AGENTS_PATH", str(custom))

        target = Path(str(tmp_path)) / "work"
        target.mkdir()
        _write_agents_md(target)
        assert (target / "AGENTS.md").read_text(encoding="utf-8") == "自定义人格"


class TestApprovalOwnership:
    """审批归属：会话所有者或超级用户；无主会话仅超级用户。"""

    @staticmethod
    def _user(pk: int, superuser: bool = False) -> object:
        from types import SimpleNamespace

        return SimpleNamespace(pk=pk, is_superuser=superuser)

    @staticmethod
    def _record(owner_id: int | None) -> object:
        from types import SimpleNamespace

        session = SimpleNamespace(user_id=owner_id) if owner_id is not None else None
        return SimpleNamespace(session=session)

    def test_owner_may_decide(self) -> None:
        from apps.agent.api.agent_api import _may_decide

        assert _may_decide(self._user(7), self._record(7)) is True

    def test_other_user_may_not(self) -> None:
        from apps.agent.api.agent_api import _may_decide

        assert _may_decide(self._user(8), self._record(7)) is False

    def test_superuser_always(self) -> None:
        from apps.agent.api.agent_api import _may_decide

        assert _may_decide(self._user(1, superuser=True), self._record(7)) is True

    def test_orphan_session_superuser_only(self) -> None:
        from apps.agent.api.agent_api import _may_decide

        assert _may_decide(self._user(7), self._record(None)) is False
        assert _may_decide(self._user(1, superuser=True), self._record(None)) is True


class _FakeStdin:
    """记录写进 pi stdin 的协议行，供中止路径断言。"""

    def __init__(self) -> None:
        self.written: list[str] = []
        self._closing = False

    def write(self, data: bytes) -> None:
        self.written.extend(line for line in data.decode("utf-8").splitlines() if line)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self._closing = True

    def is_closing(self) -> bool:
        return self._closing


class _FakeProc:
    """假 pi 子进程：只需 stdin 与 returncode。"""

    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.returncode: int | None = None

    async def wait(self) -> int:
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.returncode = -9


class TestAbortOnCancel:
    """P0-1：用户点停止时必须真的把 abort 传给 pi。

    ``abort()`` 曾是死代码——客户端断开只关进程，模型仍在服务端跑完继续烧 token。
    """

    def test_abort_clears_queue_then_aborts(self) -> None:
        """先撤排队消息再中止（Esc 语义：排队消息不会继续跑）。"""
        import asyncio

        from apps.agent.pi.rpc_client import PiRpcSession

        async def run() -> tuple[bool, list[str]]:
            session = PiRpcSession(cwd="/tmp")
            session._proc = _FakeProc()  # type: ignore[assignment]
            sent: list[str] = []

            async def fake_send(payload: dict[str, object]) -> dict[str, object]:
                sent.append(str(payload.get("type")))
                return {"success": True, "data": {"steering": ["改方向"], "followUp": ["再补一句"]}}

            session._send = fake_send  # type: ignore[assignment]
            return await session.abort(), sent

        ok, sent = asyncio.run(run())
        assert ok is True
        assert sent == ["clear_queue", "abort"]

    def test_close_before_abort_writes_both_commands(self) -> None:
        """close(abort_running=True) 直接往 stdin 写 clear_queue + abort。

        这条路径不复用 _send()：取消时读协程即将被取消，等不到 response。
        """
        import asyncio
        import json

        from apps.agent.pi.rpc_client import PiRpcSession

        async def run() -> _FakeStdin:
            session = PiRpcSession(cwd="/tmp")
            proc = _FakeProc()
            session._proc = proc  # type: ignore[assignment]
            await session._abort_before_close(proc)  # type: ignore[arg-type]
            return proc.stdin

        stdin = asyncio.run(run())
        assert [json.loads(line)["type"] for line in stdin.written] == ["clear_queue", "abort"]

    def test_close_without_abort_flag_sends_nothing(self) -> None:
        """正常跑完的路径不额外发 abort（避免无意义握手）。"""
        import asyncio

        from apps.agent.pi.rpc_client import PiRpcSession

        async def run() -> _FakeStdin:
            session = PiRpcSession(cwd="/tmp")
            proc = _FakeProc()
            session._proc = proc  # type: ignore[assignment]
            await session.close()
            return proc.stdin

        assert asyncio.run(run()).written == []

    def test_abort_swallows_send_failure(self) -> None:
        """进程已退出时 abort 不抛异常（取消路径不能因收尾失败而炸）。"""
        import asyncio

        from apps.agent.pi.rpc_client import PiError, PiRpcSession

        async def run() -> bool:
            session = PiRpcSession(cwd="/tmp")

            async def boom(payload: dict[str, object]) -> dict[str, object]:
                raise PiError("pi 进程已关闭")

            session._send = boom  # type: ignore[assignment]
            return await session.abort()

        assert asyncio.run(run()) is False


class TestPoolAbortWiring:
    """P0-1 端到端：真实 PiProcessPool 的取消分支必须把 abort_running=True 传下去。

    上一条只测到 PiRpcSession 层；pool 若没转交这个标志，abort 依旧发不出去。
    """

    @staticmethod
    def _run_pool(raise_cancel: bool) -> list[bool]:
        import asyncio
        from pathlib import Path as _Path

        from apps.agent.pi import pool as pool_module
        from apps.agent.pi.pool import PiProcessPool, PoolConfig

        seen: list[bool] = []

        class _StubSession:
            def __init__(self, **kwargs: object) -> None:
                return None

            async def start(self) -> None:
                return None

            async def close(self, *, abort_running: bool = False) -> None:
                seen.append(abort_running)

        async def run() -> None:
            p = PiProcessPool(PoolConfig(size=1))
            async with p.acquire():
                if raise_cancel:
                    raise asyncio.CancelledError

        saved = (
            pool_module.write_pi_config,
            pool_module.PiRpcSession,
            pool_module.layout,
        )
        pool_module.write_pi_config = lambda *a, **k: None  # type: ignore[assignment]
        pool_module.PiRpcSession = _StubSession  # type: ignore[assignment]
        pool_module.layout = lambda: (  # type: ignore[assignment]
            _Path("/tmp/stub-work"),
            _Path("/tmp/stub-config"),
            _Path("/tmp/stub-sessions"),
        )
        try:
            asyncio.run(run())
        except asyncio.CancelledError as exc:
            # 预期路径：用例自己要验的正是取消处理，吞掉后看 seen 断言。
            del exc
        finally:
            (
                pool_module.write_pi_config,
                pool_module.PiRpcSession,
                pool_module.layout,
            ) = saved
        return seen

    def test_cancel_closes_with_abort(self) -> None:
        assert self._run_pool(raise_cancel=True) == [True]

    def test_normal_exit_closes_without_abort(self) -> None:
        assert self._run_pool(raise_cancel=False) == [False]
