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
        assert is_high_risk("mcp__fachuan__submit_court_document")
        assert is_high_risk("delete_client")
        assert not is_high_risk("mcp__fachuan__list_cases")
        assert not is_high_risk("mcp__fachuan__get_case")

    def test_only_approved_is_granted(self) -> None:
        """fail-closed：只有 approved 放行。"""
        from apps.agent.models import AgentApproval

        for status in AgentApproval.Status:
            approval = AgentApproval(status=status)
            expected = status == AgentApproval.Status.APPROVED
            assert approval.is_granted is expected, status

    def test_server_and_extension_lists_in_sync(self) -> None:
        """服务端清单必须与 pi extension 的清单一致，防止两侧脱节。"""
        from pathlib import Path

        from apps.agent.services.approval import HIGH_RISK_TOOLS

        extension = Path(__file__).resolve().parents[4] / "apps" / "agent" / "pi" / "approval-gate.ts"
        source = extension.read_text(encoding="utf-8")
        for tool in HIGH_RISK_TOOLS:
            assert f'"{tool}"' in source, f"extension 缺少高危工具 {tool}"


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
