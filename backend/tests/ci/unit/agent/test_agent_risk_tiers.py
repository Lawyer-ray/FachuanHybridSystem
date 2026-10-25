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
    HARD_DENY_PATTERNS,
    SENSITIVE_ARG_MARKERS,
    WRITE_PREFIXES,
    RiskLevel,
    approval_timeout,
    classify_risk,
    is_high_risk,
    needs_second_confirmation,
)

EXTENSION = Path(__file__).resolve().parents[4] / "apps" / "agent" / "pi" / "approval-gate.ts"


@pytest.fixture(autouse=True)
def _fresh_annotation_cache() -> Any:
    """每个用例前重置工具注解缓存。

    为什么需要：注解表是进程级快照（从 ``mcp_server`` 注册表读一次），而
    ``mcp_server`` 在其它测试文件里可能被重新导入/重建。不重置就会出现
    「单独跑通过、全量跑失败」的顺序依赖（本文件实测踩到）。

    审批是安全路径——宁可每个用例多读一次内存表，也不能让判定结果
    取决于测试执行顺序。
    """
    from apps.agent.services import approval

    approval._reset_annotation_cache()
    yield
    approval._reset_annotation_cache()


def _ts_list(name: str) -> list[str]:
    source = EXTENSION.read_text(encoding="utf-8")
    match = re.search(rf"{name}: readonly string\[\] = \[(.*?)\]", source, re.S)
    assert match is not None, f"approval-gate.ts 缺少 {name}"
    return re.findall(r'"([^"]+)"', match.group(1))


class TestAnnotationFallback:
    """MCP 注解是名字黑名单的**补漏层**（两层取较大者）。

    背景：415 个工具全部带 MCP 注解（225 只读 / 119 写 / 71 破坏性），
    但名字黑名单只覆盖其中一部分——`clear_cache`、`cleanup_resources`、
    `reset_performance_metrics` 这类不含 `delete/remove` 的破坏性操作，
    光看名字永远漏。
    """

    def test_destructive_annotation_raises_to_high(self) -> None:
        """注解声明破坏性 → 至少高，即便名字看着是写类。"""
        level = classify_risk(
            "mcp__fachuan__update_something",
            annotations={"read_only_hint": None, "destructive_hint": True, "open_world_hint": None},
        )
        assert level is RiskLevel.HIGH

    def test_open_world_annotation_raises_to_high(self) -> None:
        """非只读 + 开放世界（外发公网/第三方）→ 至少高。"""
        level = classify_risk(
            "mcp__fachuan__sync_data",
            annotations={"read_only_hint": None, "destructive_hint": False, "open_world_hint": True},
        )
        assert level is RiskLevel.HIGH

    def test_readonly_annotation_keeps_low(self) -> None:
        """显式只读不得被注解层抬高——否则读类全变中级留痕，审计噪声淹没真实风险。"""
        level = classify_risk(
            "mcp__fachuan__list_cases",
            annotations={"read_only_hint": True, "destructive_hint": None, "open_world_hint": None},
        )
        assert level is RiskLevel.LOW

    def test_annotation_cannot_lower_name_blacklist(self) -> None:
        """两层取较大者：注解说只读，也不能把名字黑名单命中的删除工具降级。"""
        level = classify_risk(
            "mcp__fachuan__delete_case",
            annotations={"read_only_hint": True, "destructive_hint": None, "open_world_hint": None},
        )
        assert level is RiskLevel.HIGH

    def test_missing_annotation_falls_back_to_name(self) -> None:
        """拿不到注解时退回纯名字判定，不得因缺注解而抬高读类。"""
        assert classify_risk("mcp__fachuan__list_cases", annotations=None) is RiskLevel.LOW


class TestHardDeny:
    """硬拒绝层：不允许由模型自主发起的操作（extension 直接 block）。"""

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__fachuan__clear_all_data",
            "mcp__fachuan__delete_all_cases",
            "mcp__fachuan__bulk_delete_contracts",
            "mcp__fachuan__reset_and_seed",
        ],
    )
    def test_hard_denied_tools_are_critical(self, tool_name: str) -> None:
        assert classify_risk(tool_name) is RiskLevel.CRITICAL

    def test_hard_deny_patterns_non_empty(self) -> None:
        """硬拒绝清单不得被误删空（它存在本身就是一道安全边界）。"""
        assert HARD_DENY_PATTERNS, "硬拒绝清单为空 = 批量清空类操作无人拦截"


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
        assert "classifyByName" in source
        assert "risk_level" in source

    def test_hard_deny_patterns_in_sync(self) -> None:
        """硬拒绝层两侧必须逐项对齐：漏一边就有一边能绕过。"""
        assert set(_ts_list("HARD_DENY_PATTERNS")) == set(HARD_DENY_PATTERNS)

    def test_extension_has_hard_deny_layer(self) -> None:
        """extension 必须存在硬拒绝层（命中即 block，不进审批）。"""
        source = EXTENSION.read_text(encoding="utf-8")
        assert "isHardDenied" in source
        assert "block: true" in source

    def test_extension_handles_annotations(self) -> None:
        """extension 必须接 MCP annotations（补名字黑名单漏掉的那部分工具）。"""
        source = EXTENSION.read_text(encoding="utf-8")
        assert "classifyByAnnotations" in source
        assert "getAllTools" in source

    def test_extension_handles_nested_tool_calls(self) -> None:
        """嵌套调用（聚合工具 / ctx.executeTool）父子上取大，否则成审批绕过通道。"""
        source = EXTENSION.read_text(encoding="utf-8")
        assert "parentToolCallId" in source
        assert "worse(" in source


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

        approved, _, _r = await request_approval(
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


class TestApproveActionIsGuarded:
    """approve_* 是「人工确认」动作本身——必须高危(2026-10-25 审计)。

    approve_workflow_step 是工作流 gate 的人类确认信号;若判低危,模型
    可自主批准自己发起的工作流,HUMAN-in-the-loop 被绕空。该断言防止
    DANGER_PATTERNS 未来重构时把 ``approve_`` 悄悄丢掉。
    """

    def test_approve_workflow_step_is_high_risk(self) -> None:
        from apps.agent.services.approval import is_high_risk

        assert is_high_risk("mcp__fachuan__approve_workflow_step")
        assert is_high_risk("approve_workflow_step")

    def test_approve_pattern_in_both_tables(self) -> None:
        assert "approve_" in DANGER_PATTERNS
        assert "approve_" in _ts_list("HIGH_RISK_PATTERNS")


class TestExternalActionTools:
    """外部副作用与批量写工具的审批覆盖（2026-10-25 审计）。

    410 工具全量过筛发现 9 个「世界可见效果」工具被判 LOW 直接执行：
    法院递交立案 / OA 立案 / 外部担保执行询价 / 批量建案建客户 / 批量导入执行。
    「递交法院」本是审批链的立项目标场景。此断言防止 DANGER_PATTERNS
    未来重构时把 ``execute_``/``trigger_``/``batch_`` 悄悄丢掉。
    """

    @pytest.mark.parametrize(
        "tool",
        [
            "mcp__fachuan__execute_court_filing",  # 向法院递交立案
            "mcp__fachuan__trigger_oa_filing",  # OA 立案提交
            "mcp__fachuan__execute_guarantee",  # 外部担保执行
            "mcp__fachuan__execute_preservation_quote",  # 外部保全询价
            "mcp__fachuan__execute_case_import",  # 批量导入执行（落库）
            "mcp__fachuan__batch_create_cases",  # 批量建案
            "mcp__fachuan__batch_create_clients",  # 批量建客户
            "mcp__fachuan__trigger_case_import",  # 上传解析（与 upload_ 同级）
            "mcp__fachuan__trigger_client_import",
        ],
    )
    def test_external_actions_are_high_risk(self, tool: str) -> None:
        assert is_high_risk(tool), tool

    @pytest.mark.parametrize(
        "tool",
        [
            "start_workflow",  # 可 cancel，但会真实跑步骤
            "sync_message_source",  # 拉取入库
            "sync_all_message_sources",
            "assign_lawyer",  # 改案件指派
            "save_archive_overrides",
            "move_archive_material",
            "retry_sms_processing",
            "learn_archive_rules",
            "generate_complaint",  # 文书生成落库
            "save_to_directory",  # 写盘到绑定目录
        ],
    )
    def test_write_actions_are_medium(self, tool: str) -> None:
        """新增写前缀 = 中级：静默放行但留痕，无审批摩擦。"""
        assert classify_risk(tool) is RiskLevel.MEDIUM, tool
        assert not is_high_risk(tool), tool

    @pytest.mark.parametrize(
        "tool",
        [
            "get_court_filing_case_info",
            "get_filing_status",
            "get_case_import_preview",
            "get_lpr_sync_status",
            "list_oa_configs",
        ],
    )
    def test_reads_stay_low(self, tool: str) -> None:
        """读类工具不受前缀扩充影响——execute_/sync_ 等前缀只匹配短名开头。"""
        assert classify_risk(tool) is RiskLevel.LOW, tool

    def test_new_patterns_in_both_tables(self) -> None:
        for pattern in ("execute_", "trigger_", "batch_"):
            assert pattern in DANGER_PATTERNS, pattern
            assert pattern in _ts_list("HIGH_RISK_PATTERNS"), pattern
        for prefix in ("generate_", "save_", "move_", "sync_", "start_", "retry_", "assign_", "learn_"):
            assert prefix in WRITE_PREFIXES, prefix
            assert prefix in _ts_list("WRITE_PREFIXES"), prefix

    def test_round2_write_prefixes_in_both_tables(self) -> None:
        """2026-10-25 二轮:18 个补漏前缀双表同步。"""
        added = (
            "ensure_",
            "bind_",
            "rename_",
            "reorder_",
            "toggle_",
            "merge_",
            "complete_",
            "cancel_",
            "export_",
            "extract_",
            "process_",
            "normalize_",
            "fill_",
            "scale_",
            "clear_",
            "reset_",
            "cleanup_",
            "unified_",
        )
        for prefix in added:
            assert prefix in WRITE_PREFIXES, prefix
            assert prefix in _ts_list("WRITE_PREFIXES"), prefix

    @pytest.mark.parametrize(
        "tool",
        [
            "rename_inbox_attachment",
            "rename_material_group",
            "reorder_archive_materials",
            "reorder_evidence_items",
            "toggle_compact_archive",
            "bind_materials",
            "ensure_guarantee_quote",
            "complete_reminders",
            "cancel_conversion_job",
            "unified_generate",
        ],
    )
    def test_zero_trace_write_tools_now_medium(self, tool: str) -> None:
        """此前 50 个发写请求的工具连中级留痕都没有——改名/重排/绑定/开关类
        现在至少 MEDIUM（静默放行 + 审计日志）。"""
        assert classify_risk(f"mcp__fachuan__{tool}") is RiskLevel.MEDIUM, tool

    @pytest.mark.parametrize("tool", ["clear_cache", "reset_performance_metrics"])
    def test_annotation_promotes_cleanup_tools_to_high(self, tool: str) -> None:
        """`clear_cache` / `reset_performance_metrics` 不含 delete/remove，
        名字黑名单永远盖不到；它们靠 MCP 注解（destructive）被抬到 HIGH。
        这条测试就是注解层的实际价值证据——删了注解层它就会红灯。"""
        assert classify_risk(f"mcp__fachuan__{tool}") is RiskLevel.HIGH, tool

    @pytest.mark.parametrize(
        "tool",
        [
            "calculate_interest",
            "calculate_litigation_fee",
            "mortgage_amortize",
            "check_law_references",
            "chat_with_context",
            "validate_folder_structure",
            "detect_orientation",
            "suggest_rename",
        ],
    )
    def test_stateless_compute_stays_low(self, tool: str) -> None:
        """纯计算/校验类刻意保持 LOW——中级是审计留痕,不是给计算器加摩擦。"""
        assert classify_risk(f"mcp__fachuan__{tool}") is RiskLevel.LOW, tool

    def test_retry_with_sensitive_arg_escalates(self) -> None:
        """中级写前缀 + 敏感参数 → 高危（参数级判定对新增前缀同样生效）。"""
        assert classify_risk("mcp__fachuan__start_workflow", {"deadline": "2026-01-01"}) is RiskLevel.HIGH
        assert classify_risk("save_archive_overrides", {"total": 3}) is RiskLevel.HIGH
