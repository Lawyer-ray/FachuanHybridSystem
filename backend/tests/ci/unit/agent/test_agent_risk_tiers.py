"""审批风险分级（P1-3）。

从布尔升级为四级的原因：`delete_case(case_id=1)` 与 `clear_all_xxx()` 走同一档
审批，用户无法区分「删一条草稿」和「清空全库」，久了就闭眼点同意——审批
形同虚设。同时补上「只按工具名判高危」的漏洞：`update_contract` 免审批，
但它能改金额。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from apps.agent.services.approval import (
    CRITICAL_PATTERNS,
    DANGER_PATTERNS,
    SENSITIVE_ARG_MARKERS,
    WRITE_PREFIXES,
    RiskLevel,
    approval_timeout,
    classify_risk,
    is_high_risk,
    needs_second_confirmation,
)

EXTENSION = Path(__file__).resolve().parents[4] / "apps" / "agent" / "pi" / "approval-gate.ts"


def _ts_list(name: str) -> list[str]:
    source = EXTENSION.read_text(encoding="utf-8")
    match = re.search(rf"{name}: readonly string\[\] = \[(.*?)\]", source, re.S)
    assert match is not None, f"approval-gate.ts 缺少 {name}"
    return re.findall(r'"([^"]+)"', match.group(1))


class TestClassification:
    def test_read_is_low(self) -> None:
        assert classify_risk("mcp__fachuan__list_cases") is RiskLevel.LOW
        assert classify_risk("mcp__fachuan__get_case") is RiskLevel.LOW

    def test_delete_is_high(self) -> None:
        assert classify_risk("mcp__fachuan__delete_case") is RiskLevel.HIGH

    def test_clear_all_is_critical(self) -> None:
        """批量清空必须比普通删除更吓人。"""
        assert classify_risk("mcp__fachuan__clear_all_data") is RiskLevel.CRITICAL
        assert classify_risk("mcp__fachuan__reset_and_rebuild") is RiskLevel.CRITICAL

    def test_plain_create_is_medium(self) -> None:
        """常规写入静默执行（不打断用户），但留审计标记。"""
        assert classify_risk("mcp__fachuan__create_case_log", {"note": "x"}) is RiskLevel.MEDIUM

    def test_update_amount_escalates_to_high(self) -> None:
        """回归：只按工具名判高危会漏掉改金额的写操作。"""
        assert classify_risk("mcp__fachuan__update_contract", {"fixed_amount": 100}) is RiskLevel.HIGH
        assert classify_risk("mcp__fachuan__update_case", {"target_amount": 5}) is RiskLevel.HIGH

    def test_update_deadline_escalates(self) -> None:
        assert classify_risk("mcp__fachuan__update_reminder", {"due_at": "2026-01-01"}) is RiskLevel.HIGH

    def test_update_status_escalates(self) -> None:
        assert classify_risk("mcp__fachuan__update_case", {"status": "closed"}) is RiskLevel.HIGH

    def test_update_without_sensitive_args_stays_medium(self) -> None:
        assert classify_risk("mcp__fachuan__update_case", {"note": "备注"}) is RiskLevel.MEDIUM

    def test_exempt_suffix_wins(self) -> None:
        """豁免后缀优先于一切模式（新增例外必须写明理由）。"""
        from apps.agent.services import approval as mod

        original = mod.APPROVAL_EXEMPT_SUFFIXES
        try:
            mod.APPROVAL_EXEMPT_SUFFIXES = frozenset({"preview_delete"})
            assert classify_risk("mcp__fachuan__preview_delete") is RiskLevel.LOW
        finally:
            mod.APPROVAL_EXEMPT_SUFFIXES = original

    def test_sensitive_marker_is_case_insensitive(self) -> None:
        assert classify_risk("mcp__fachuan__update_case", {"Target_Amount": 1}) is RiskLevel.HIGH

    def test_short_name_extraction(self) -> None:
        """带前缀与不带前缀的工具名判定一致。"""
        assert classify_risk("delete_case") is RiskLevel.HIGH
        assert classify_risk("mcp__fachuan__delete_case") is RiskLevel.HIGH


class TestHighRiskGate:
    def test_high_and_critical_require_approval(self) -> None:
        assert is_high_risk("mcp__fachuan__delete_case") is True
        assert is_high_risk("mcp__fachuan__clear_all_x") is True

    def test_low_and_medium_do_not(self) -> None:
        assert is_high_risk("mcp__fachuan__list_cases") is False
        assert is_high_risk("mcp__fachuan__create_case_log") is False

    def test_sensitive_args_change_the_verdict(self) -> None:
        """同一工具、不同参数 → 一个放行、一个要审批。"""
        assert is_high_risk("mcp__fachuan__update_case", {"note": "x"}) is False
        assert is_high_risk("mcp__fachuan__update_case", {"target_amount": 9}) is True


class TestTierPolicy:
    def test_second_confirmation_only_for_critical(self) -> None:
        assert needs_second_confirmation(RiskLevel.CRITICAL) is True
        assert needs_second_confirmation(RiskLevel.HIGH) is False
        assert needs_second_confirmation(RiskLevel.MEDIUM) is False
        assert needs_second_confirmation(RiskLevel.LOW) is False

    def test_critical_gets_longer_timeout(self) -> None:
        """紧急操作值得让用户多想一会儿。"""
        assert approval_timeout(RiskLevel.CRITICAL) > approval_timeout(RiskLevel.HIGH)


class TestServerExtensionParity:
    """两侧策略必须逐项对齐：extension 可被绕过，但脱节会让人查不出为什么。"""

    def test_danger_patterns_in_sync(self) -> None:
        assert set(_ts_list("HIGH_RISK_PATTERNS")) == set(DANGER_PATTERNS)

    def test_critical_patterns_in_sync(self) -> None:
        assert set(_ts_list("CRITICAL_PATTERNS")) == set(CRITICAL_PATTERNS)

    def test_sensitive_markers_in_sync(self) -> None:
        assert set(_ts_list("SENSITIVE_ARG_MARKERS")) == set(SENSITIVE_ARG_MARKERS)

    def test_write_prefixes_in_sync(self) -> None:
        assert set(_ts_list("WRITE_PREFIXES")) == set(WRITE_PREFIXES)

    def test_extension_has_classify_function(self) -> None:
        """extension 必须实现分级（只发 tool 名会导致服务端无法做参数级判定）。"""
        source = EXTENSION.read_text(encoding="utf-8")
        assert "classifyRisk" in source
        assert "risk_level" in source


class TestRegistryCoverage:
    """对账 mcp_server 实际注册表：新增破坏性工具忘了进审批必须红灯。"""

    @pytest.fixture(scope="class")
    def tool_names(self) -> list[str]:
        import asyncio

        from mcp_server.server import mcp

        names = [t.name for t in asyncio.run(mcp.list_tools())]
        assert len(names) > 300, "mcp 工具注册表加载异常"
        return names

    def test_destructive_tools_are_gated(self, tool_names: list[str]) -> None:
        destructive = re.compile(r"delete|remove|destroy")
        uncovered = [n for n in tool_names if destructive.search(n) and not is_high_risk(f"mcp__fachuan__{n}")]
        assert not uncovered, f"删除类工具脱离审批: {uncovered}"

    def test_external_tools_are_gated(self, tool_names: list[str]) -> None:
        external = re.compile(r"^send_|^submit_|^upload_|^file_|^confirm_|clear_all|reset_and_")
        uncovered = [n for n in tool_names if external.search(n) and not is_high_risk(f"mcp__fachuan__{n}")]
        assert not uncovered, f"外发/递交/批量类工具脱离审批: {uncovered}"

    def test_sensitive_write_tools_gated_with_amount_arg(self, tool_names: list[str]) -> None:
        """真实注册表里那些能改金额的写工具，带上金额参数就必须被拦。"""
        writers = [n for n in tool_names if n.startswith(("create_", "update_", "set_"))]
        assert writers, "注册表里没有写类工具，对账逻辑可能失效"
        gated = [n for n in writers if n in {"create_contract", "update_case", "create_case", "update_reminder"}]
        for name in gated:
            assert is_high_risk(f"mcp__fachuan__{name}", {"amount": 1}) is True, f"{name} 带金额参数仍未拦"

    def test_read_tools_stay_low_risk(self, tool_names: list[str]) -> None:
        """别把读类工具也拦了——那会让 agent 不可用。"""
        readers = [n for n in tool_names if n.startswith(("list_", "get_", "search_"))]
        assert readers
        wrongly_gated = [n for n in readers if classify_risk(f"mcp__fachuan__{n}") != RiskLevel.LOW]
        assert not wrongly_gated, f"读类工具被误判为需审批: {wrongly_gated[:10]}"


@pytest.mark.django_db(transaction=True)
class TestApprovalEventPayload:
    @pytest.mark.asyncio
    async def test_event_carries_risk_level_and_second_confirmation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """前端要拿到 risk_level / needs_second_confirmation 才能做二次确认。"""
        from apps.agent.services import approval as mod

        published: list[dict[str, Any]] = []

        class _Bus:
            async def has_subscribers(self, sid: str) -> bool:
                return True

            async def publish(self, sid: str, event: dict[str, Any]) -> int:
                published.append(event)
                return 1

        monkeypatch.setattr("apps.agent.services.event_bus.get_bus", lambda: _Bus())
        monkeypatch.setattr(mod, "redis_cache_enabled", lambda: False)

        # 让等待立即超时，避免测试卡 900 秒
        await mod.request_approval(
            tool_name="mcp__fachuan__clear_all_data",
            tool_args={},
            session_id="sess-tier",
            timeout=0.05,
        )
        assert published, "没有推送审批事件"
        event = published[0]
        assert event["risk_level"] == "critical"
        assert event["needs_second_confirmation"] is True
        assert "批量" in event["message"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_medium_risk_passes_without_approval(self) -> None:
        """中级（常规写）不该弹窗，否则 agent 每写一条都要人点。"""
        from apps.agent.services.approval import request_approval

        approved, _ = await request_approval(
            tool_name="mcp__fachuan__create_case_log",
            tool_args={"note": "记一笔"},
            session_id="sess-medium",
            timeout=0.05,
        )
        assert approved is True

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_risk_level_persisted_for_audit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """审批记录的 risk_level 要落库，审计时分得清轻重。"""
        from apps.agent.models import AgentApproval
        from apps.agent.services import approval as mod
        from apps.agent.services.approval import request_approval

        # CI 无 Redis：不 mock 时要么挂在真实总线的网络调用上、要么因
        # 离线审批默认开启而等 OFFLINE_TIMEOUT（7200s），被 pytest-timeout 处决。
        class _Bus:
            async def has_subscribers(self, sid: str) -> bool:
                return False

            async def publish(self, sid: str, event: dict[str, Any]) -> int:
                return 0

        monkeypatch.setattr("apps.agent.services.event_bus.get_bus", lambda: _Bus())
        monkeypatch.setattr(mod, "redis_cache_enabled", lambda: False)
        monkeypatch.setattr(mod, "allow_offline_approval", lambda: False)

        await request_approval(
            tool_name="mcp__fachuan__delete_case",
            tool_args={},
            session_id="sess-audit-none",  # 无订阅者 → fail-closed
            timeout=0.05,
        )
        record = await AgentApproval.objects.filter(tool_name="mcp__fachuan__delete_case").afirst()
        assert record is not None
        assert record.risk_level == "high"
