"""Temporal Workflow 定义。

Workflow 函数必须满足确定性约束：
  ✅ 可以做: 调 activity、if/else、for 循环、信号接收
  ❌ 不能做: datetime.now()、random、I/O、ORM 调用
所有"脏活"放 Activity，workflow 只做编排。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from apps.workflow.temporal import activities as act

logger = logging.getLogger(__name__)


@dataclass
class SimpleWorkflowInput:
    case_id: int
    run_id: int  # Django WorkflowRun ID


@dataclass
class GateResult:
    approved: bool = False
    comment: str = ""


# 通用选项
QUICK_TIMEOUT = timedelta(seconds=30)
QUICK_RETRY = RetryPolicy(maximum_attempts=3)
LLM_TIMEOUT = timedelta(minutes=5)
LLM_RETRY = RetryPolicy(maximum_attempts=2)
LONG_TIMEOUT = timedelta(hours=2)
LONG_RETRY = RetryPolicy(maximum_attempts=2)


# ── step_id → activity 映射（用于 DynamicWorkflow 动态分发）──────
# 对于有 mcp_tool 的步骤，DynamicWorkflow 会走 execute_mcp_tool；
# 对于纯 internal activity 的步骤，走这里对应的 activity 引用。
INTERNAL_ACTIVITY_MAP: dict[str, Any] = {
    "collect_case_facts": act.collect_case_facts,
    "list_case_materials": act.list_case_materials,
    "analyze_single_evidence": act.analyze_single_evidence,
    "summarize_evidence": act.summarize_evidence,
    "suggest_arrangement": act.suggest_arrangement,
    "apply_arrangement": act.apply_arrangement,
    "build_litigation_context": act.build_litigation_context,
    "generate_complaint_simple": act.generate_complaint_simple,
    "generate_complaint": act.generate_complaint,
    "review_complaint_quality": act.review_complaint_quality,
    "execute_court_filing": act.execute_court_filing,
    "download_litigation_document": act.download_litigation_document,
}

# 有 mcp_tool 的步骤 → MCP 工具名（DynamicWorkflow 走 execute_mcp_tool）
MCP_TOOL_MAP: dict[str, str] = {
    "collect_case_facts": "get_case",
    "list_case_materials": "list_bind_candidates",
    "create_case_log": "create_case_log",
    "generate_complaint": "generate_complaint",
    "generate_defense": "generate_defense",
    "download_litigation_document": "download_litigation_document",
    "download_authorization_package": "download_authorization_package",
    "download_preservation_docs": "download_full_preservation_package",
    "execute_court_filing": "execute_court_filing",
    "execute_guarantee": "execute_guarantee",
    "submit_court_sms": "submit_court_sms",
    "search_companies": "search_companies",
    "get_company_profile": "get_company_profile",
    "get_company_risks": "get_company_risks",
    "create_research_task": "create_research_task",
    "check_law_references": "check_law_references",
    "create_reminder": "create_new_reminder",
    "auto_namer": "auto_namer_process",
    "process_document": "process_document",
    "convert_document": "convert_document",
    "calculate_litigation_fee": "calculate_litigation_fee",
    "calculate_interest": "calculate_interest",
}


@workflow.defn
class SalesContractDisputeWorkflow:
    """买卖合同纠纷 —— 测试用简化流程

    流程: 收集事实 → 人工确认 → 生成起诉状 → 人工审批 → 完成
    """

    def __init__(self) -> None:
        self._gate: GateResult | None = None

    @workflow.run
    async def run(self, inp: dict) -> dict[str, Any]:
        case_id: int = inp["case_id"]
        run_id: int = inp["run_id"]

        # Step 1: 收集案件事实
        await workflow.execute_activity(
            act.record_step,
            args=(run_id, "collect_facts", "收集案件事实", "activity", "running"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        facts = await workflow.execute_activity(
            act.collect_case_facts,
            args=(case_id,),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        await workflow.execute_activity(
            act.record_step,
            args=(run_id, "collect_facts", "收集案件事实", "activity", "success", facts),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        # Step 2: 人工确认事实
        await workflow.execute_activity(
            act.update_run_status,
            args=(run_id, "waiting_human", "confirm_facts"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        await workflow.execute_activity(
            act.record_step,
            args=(run_id, "confirm_facts", "确认事实", "gate", "waiting"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        self._gate = None
        await workflow.wait_condition(lambda: self._gate is not None)
        assert self._gate is not None
        gate = self._gate

        await workflow.execute_activity(
            act.record_step,
            args=(
                run_id, "confirm_facts", "确认事实", "gate",
                "success" if gate.approved else "failed",
                {"comment": gate.comment},
            ),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        if not gate.approved:
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "failed", "confirm_facts"),
                start_to_close_timeout=QUICK_TIMEOUT,
                retry_policy=QUICK_RETRY,
            )
            return {"status": "rejected", "phase": "confirm_facts", "comment": gate.comment}

        # Step 3: 生成起诉状
        await workflow.execute_activity(
            act.update_run_status,
            args=(run_id, "running", "draft_complaint"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        await workflow.execute_activity(
            act.record_step,
            args=(run_id, "draft_complaint", "生成起诉状", "activity", "running"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        draft = await workflow.execute_activity(
            act.generate_complaint_simple,
            args=(case_id, facts),
            start_to_close_timeout=LLM_TIMEOUT,
            retry_policy=LLM_RETRY,
        )
        await workflow.execute_activity(
            act.record_step,
            args=(run_id, "draft_complaint", "生成起诉状", "activity", "success", draft),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        # Step 4: 人工审批起诉状
        await workflow.execute_activity(
            act.update_run_status,
            args=(run_id, "waiting_human", "review_complaint"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        await workflow.execute_activity(
            act.record_step,
            args=(run_id, "review_complaint", "审批起诉状", "gate", "waiting"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        self._gate = None
        await workflow.wait_condition(lambda: self._gate is not None)
        assert self._gate is not None
        gate = self._gate

        await workflow.execute_activity(
            act.record_step,
            args=(
                run_id, "review_complaint", "审批起诉状", "gate",
                "success" if gate.approved else "failed",
                {"comment": gate.comment},
            ),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        if not gate.approved:
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "failed", "review_complaint"),
                start_to_close_timeout=QUICK_TIMEOUT,
                retry_policy=QUICK_RETRY,
            )
            return {"status": "rejected", "phase": "review_complaint", "comment": gate.comment}

        # Step 5: 完成
        await workflow.execute_activity(
            act.update_run_status,
            args=(run_id, "completed", ""),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        return {"status": "completed", "complaint": draft}

    @workflow.signal
    async def confirm_facts_approved(self, data: dict) -> None:
        """确认事实审批信号"""
        self._gate = GateResult(
            approved=data.get("approved", False),
            comment=data.get("comment", ""),
        )

    @workflow.signal
    async def review_complaint_approved(self, data: dict) -> None:
        """审批起诉状信号"""
        self._gate = GateResult(
            approved=data.get("approved", False),
            comment=data.get("comment", ""),
        )

    @workflow.query
    def current_state(self) -> dict:
        return {
            "gate": self._gate.__dict__ if self._gate else None,
        }


# ════════════════════════════════════════════════════════════════
# DynamicWorkflow — 通用动态工作流引擎
# 读取 WorkflowTemplate.steps_schema，按顺序执行各步骤。
# ════════════════════════════════════════════════════════════════


def _resolve_dotted(obj: Any, path: str) -> Any:
    """按点号路径从 dict 中取值，如 'previous_step.result.need_complaint'"""
    for key in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return None
    return obj


def _eval_condition(step: dict, context: dict) -> bool:
    """求值 condition 步骤的条件表达式"""
    cfg = step.get("config", {})
    field_path = cfg.get("field", "")
    operator = cfg.get("operator", "eq")
    value = cfg.get("value", "")

    actual = _resolve_dotted(context, field_path)

    if operator == "eq":
        return str(actual) == str(value)
    if operator == "neq":
        return str(actual) != str(value)
    if operator == "gt":
        return float(actual or 0) > float(value)
    if operator == "lt":
        return float(actual or 0) < float(value)
    if operator == "contains":
        return value in str(actual or "")
    if operator == "exists":
        return actual is not None
    return False


def _build_step_args(step: dict, context: dict, case_id: int, run_id: int) -> list:
    """根据步骤定义和上下文，构建 activity 参数列表。

    约定:
    - config 中的 template 变量 {{xxx}} 会从 context 中解析
    - case_id / run_id 始终可从 workflow input 获取
    """
    import re

    cfg = step.get("config", {})
    step_type = step.get("type", "activity")

    def _resolve_template(val: str) -> str:
        """解析 {{variable.path}} 模板"""
        def _replace(m: re.Match) -> str:
            path = m.group(1).strip()
            result = _resolve_dotted(context, path)
            return str(result) if result is not None else ""
        return re.sub(r"\{\{(.+?)\}\}", _replace, val)

    if step_type == "llm":
        system_prompt = _resolve_template(cfg.get("system_prompt", ""))
        user_prompt = _resolve_template(cfg.get("user_prompt_template", ""))
        return [system_prompt, user_prompt]

    if step_type == "delay":
        return [float(cfg.get("duration_minutes", 5))]

    if step_type == "http":
        return [
            cfg.get("method", "GET"),
            cfg.get("url", ""),
            cfg.get("headers", ""),
            cfg.get("body", ""),
        ]

    if step_type == "code":
        # code 步骤: 传入 code + 当前 context
        return [cfg.get("code", ""), context]

    # activity / 默认: 传 case_id + context
    return [case_id]


@workflow.defn
class DynamicWorkflow:
    """通用动态工作流引擎。

    根据 WorkflowTemplate.steps_schema 逐步执行，支持 8 种步骤类型：
    activity, gate, wait, condition, delay, llm, http, code

    信号: 使用通用 gate_approved 信号，通过 data.step_id 路由到正确 gate。
    """

    def __init__(self) -> None:
        # {step_id: GateResult}
        self._pending_gates: dict[str, GateResult] = {}
        # 当前活跃的 gate step_id（用于 query）
        self._current_gate_step_id: str | None = None

    @workflow.run
    async def run(self, inp: dict) -> dict[str, Any]:
        case_id: int = inp["case_id"]
        run_id: int = inp["run_id"]
        template_id: int = inp["template_id"]

        # 1) 读取模板 schema
        schema_data = await workflow.execute_activity(
            act.fetch_template_schema,
            args=(template_id,),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        steps: list[dict] = schema_data.get("steps_schema", [])
        if isinstance(steps, dict):
            steps = steps.get("steps", [])
        if not steps:
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "completed", ""),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            return {"status": "completed", "message": "模板无步骤定义"}

        # 2) 逐步执行
        context: dict[str, Any] = {
            "case_id": case_id,
            "run_id": run_id,
            "step_outputs": {},  # step_id → output_data
        }

        for step in steps:
            step_id: str = step.get("id", "unknown")
            step_name: str = step.get("name", step_id)
            step_type: str = step.get("type", "activity")
            mcp_tool: str | None = step.get("mcp_tool")
            on_fail: str = step.get("config", {}).get("on_fail", "abort")
            timeout_hours: float = step.get("config", {}).get("timeout_hours", 1)

            try:
                result = await self._execute_step(
                    step=step,
                    step_id=step_id,
                    step_name=step_name,
                    step_type=step_type,
                    mcp_tool=mcp_tool,
                    case_id=case_id,
                    run_id=run_id,
                    context=context,
                    timeout_hours=timeout_hours,
                )
            except Exception as exc:
                logger.exception("步骤 %s 执行失败", step_id)
                await workflow.execute_activity(
                    act.record_step,
                    args=(run_id, step_id, step_name, step_type, "failed", None, str(exc)),
                    start_to_close_timeout=QUICK_TIMEOUT,
                    retry_policy=QUICK_RETRY,
                )
                if on_fail == "skip":
                    context["step_outputs"][step_id] = {"skipped": True, "error": str(exc)}
                    continue
                # abort（默认）
                await workflow.execute_activity(
                    act.update_run_status,
                    args=(run_id, "failed", step_id),
                    start_to_close_timeout=QUICK_TIMEOUT,
                )
                return {"status": "failed", "failed_step": step_id, "error": str(exc)}

            # gate 被拒绝
            if step_type == "gate" and result is not None and not result.get("approved", True):
                await workflow.execute_activity(
                    act.update_run_status,
                    args=(run_id, "failed", step_id),
                    start_to_close_timeout=QUICK_TIMEOUT,
                )
                return {"status": "rejected", "phase": step_id, "comment": result.get("comment", "")}

            # condition 结果为 False → 标记后续步骤 skip（简单实现: 跳过下一个步骤）
            if step_type == "condition" and result is not None and not result.get("met", True):
                context["step_outputs"][step_id] = {"skipped": True, "condition_met": False}

            # 累积输出
            if result is not None:
                context["step_outputs"][step_id] = result

        # 3) 完成
        await workflow.execute_activity(
            act.update_run_status,
            args=(run_id, "completed", ""),
            start_to_close_timeout=QUICK_TIMEOUT,
        )
        return {
            "status": "completed",
            "step_outputs": context["step_outputs"],
        }

    async def _execute_step(
        self,
        step: dict,
        step_id: str,
        step_name: str,
        step_type: str,
        mcp_tool: str | None,
        case_id: int,
        run_id: int,
        context: dict,
        timeout_hours: float,
    ) -> dict | None:
        """执行单个步骤，返回步骤输出（gate rejected 返回 {"approved": False}）"""

        # ── gate: 人工审批门 ──
        if step_type == "gate":
            return await self._execute_gate(step_id, step_name, run_id, context, timeout_hours)

        # ── wait: 等待外部事件 ──
        if step_type == "wait":
            return await self._execute_wait(step_id, step_name, run_id, context, timeout_hours)

        # ── condition: 条件分支 ──
        if step_type == "condition":
            met = _eval_condition(step, context)
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "running", step_id),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            await workflow.execute_activity(
                act.record_step,
                args=(run_id, step_id, step_name, "condition", "success", {"met": met}),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            return {"met": met}

        # ── delay: 延时等待 ──
        if step_type == "delay":
            cfg = step.get("config", {})
            duration = float(cfg.get("duration_minutes", 5))
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "running", step_id),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            await workflow.execute_activity(
                act.record_step,
                args=(run_id, step_id, step_name, "delay", "running"),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            await workflow.execute_activity(
                act.generic_delay,
                args=(duration,),
                start_to_close_timeout=timedelta(hours=max(timeout_hours, duration / 60 + 1)),
            )
            await workflow.execute_activity(
                act.record_step,
                args=(run_id, step_id, step_name, "delay", "success"),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            return {}

        # ── llm: LLM 调用 ──
        if step_type == "llm":
            args = _build_step_args(step, context, case_id, run_id)
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "running", step_id),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            await workflow.execute_activity(
                act.record_step,
                args=(run_id, step_id, step_name, "llm", "running"),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            result = await workflow.execute_activity(
                act.generic_llm_call,
                args=tuple(args),
                start_to_close_timeout=LLM_TIMEOUT,
                retry_policy=LLM_RETRY,
            )
            await workflow.execute_activity(
                act.record_step,
                args=(run_id, step_id, step_name, "llm", "success", result),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            return result

        # ── http: HTTP 请求 ──
        if step_type == "http":
            args = _build_step_args(step, context, case_id, run_id)
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "running", step_id),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            await workflow.execute_activity(
                act.record_step,
                args=(run_id, step_id, step_name, "http", "running"),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            result = await workflow.execute_activity(
                act.generic_http_request,
                args=tuple(args),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=QUICK_RETRY,
            )
            await workflow.execute_activity(
                act.record_step,
                args=(run_id, step_id, step_name, "http", "success", result),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            return result

        # ── code: 代码执行 ──
        if step_type == "code":
            args = _build_step_args(step, context, case_id, run_id)
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "running", step_id),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            await workflow.execute_activity(
                act.record_step,
                args=(run_id, step_id, step_name, "code", "running"),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            result = await workflow.execute_activity(
                act.generic_code_exec,
                args=tuple(args),
                start_to_close_timeout=timedelta(seconds=30),
            )
            await workflow.execute_activity(
                act.record_step,
                args=(run_id, step_id, step_name, "code", "success", result),
                start_to_close_timeout=QUICK_TIMEOUT,
            )
            return result

        # ── activity: 业务步骤 ──
        # 优先走 MCP 工具，其次走 internal activity
        await workflow.execute_activity(
            act.update_run_status,
            args=(run_id, "running", step_id),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        await workflow.execute_activity(
            act.record_step,
            args=(run_id, step_id, step_name, "activity", "running"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        if mcp_tool:
            # 走 MCP 工具调度
            kwargs = _build_mcp_kwargs(step, context, case_id, run_id)
            result = await workflow.execute_activity(
                act.execute_mcp_tool,
                args=(mcp_tool, kwargs),
                start_to_close_timeout=LLM_TIMEOUT,
                retry_policy=LLM_RETRY,
            )
        else:
            # 走 internal activity
            internal_act = INTERNAL_ACTIVITY_MAP.get(step_id)
            if internal_act is None:
                raise ValueError(f"步骤 {step_id} 无 mcp_tool 且无 internal activity 映射")
            args = _build_step_args(step, context, case_id, run_id)
            timeout = LLM_TIMEOUT if step_id in ("generate_complaint", "generate_defense", "review_complaint_quality") else QUICK_TIMEOUT
            result = await workflow.execute_activity(
                internal_act,
                args=tuple(args),
                start_to_close_timeout=timeout,
                retry_policy=LLM_RETRY if timeout == LLM_TIMEOUT else QUICK_RETRY,
            )

        await workflow.execute_activity(
            act.record_step,
            args=(run_id, step_id, step_name, "activity", "success", result),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        return result

    async def _execute_gate(
        self, step_id: str, step_name: str, run_id: int, context: dict, timeout_hours: float,
    ) -> dict:
        """执行 gate（人工审批门）步骤"""
        await workflow.execute_activity(
            act.update_run_status,
            args=(run_id, "waiting_human", step_id),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        await workflow.execute_activity(
            act.record_step,
            args=(run_id, step_id, step_name, "gate", "waiting"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        self._current_gate_step_id = step_id
        self._pending_gates.pop(step_id, None)

        # 等待 gate_approved 信号中包含匹配的 step_id
        await workflow.wait_condition(
            lambda: self._pending_gates.get(step_id) is not None,
        )
        gate = self._pending_gates.pop(step_id)
        self._current_gate_step_id = None

        await workflow.execute_activity(
            act.record_step,
            args=(
                run_id, step_id, step_name, "gate",
                "success" if gate.approved else "failed",
                {"comment": gate.comment},
            ),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        # 更新 run status 回 running（审批后继续）
        if gate.approved:
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "running", step_id),
                start_to_close_timeout=QUICK_TIMEOUT,
            )

        return {"approved": gate.approved, "comment": gate.comment}

    async def _execute_wait(
        self, step_id: str, step_name: str, run_id: int, context: dict, timeout_hours: float,
    ) -> dict:
        """执行 wait（等待外部事件）步骤"""
        cfg = {}
        for s in context.get("_steps_schema", []):
            if s.get("id") == step_id:
                cfg = s.get("config", {})
                break

        await workflow.execute_activity(
            act.update_run_status,
            args=(run_id, "waiting_event", step_id),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        await workflow.execute_activity(
            act.record_step,
            args=(run_id, step_id, step_name, "wait", "waiting"),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        self._current_gate_step_id = step_id
        self._pending_gates.pop(step_id, None)

        # 复用 gate_approved 信号机制（wait 也通过审批 API 触发）
        await workflow.wait_condition(
            lambda: self._pending_gates.get(step_id) is not None,
        )
        event_data = self._pending_gates.pop(step_id)
        self._current_gate_step_id = None

        await workflow.execute_activity(
            act.record_step,
            args=(run_id, step_id, step_name, "wait", "success", {"comment": event_data.comment}),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )
        await workflow.execute_activity(
            act.update_run_status,
            args=(run_id, "running", step_id),
            start_to_close_timeout=QUICK_TIMEOUT,
        )

        return {"received": True, "comment": event_data.comment}

    # ── 通用信号 ──

    @workflow.signal
    async def gate_approved(self, data: dict) -> None:
        """通用 gate/wait 审批信号

        data 必须包含:
          - step_id: 目标步骤 ID
          - approved: bool
          - comment: str (可选)
        """
        step_id = data.get("step_id", "")
        self._pending_gates[step_id] = GateResult(
            approved=data.get("approved", False),
            comment=data.get("comment", ""),
        )

    @workflow.query
    def current_state(self) -> dict:
        return {
            "current_gate_step_id": self._current_gate_step_id,
            "pending_gates": {k: v.__dict__ for k, v in self._pending_gates.items()},
        }


def _build_mcp_kwargs(step: dict, context: dict, case_id: int, run_id: int) -> dict:
    """根据步骤 config 和上下文构建 MCP 工具的 kwargs

    约定:
    - case_id 自动注入
    - config 中的 template 变量 {{xxx}} 会从 context 中解析
    - 上一个步骤的输出可通过 previous_step 引用
    """
    import re

    cfg = step.get("config", {})
    kwargs: dict[str, Any] = {"case_id": case_id}

    # 将上一个步骤的输出放入上下文方便引用
    prev_output = context.get("_last_output", {})

    def _resolve_template(val: str) -> str:
        def _replace(m: re.Match) -> str:
            path = m.group(1).strip()
            if path.startswith("previous_step."):
                sub_path = path[len("previous_step."):]
                result = _resolve_dotted(prev_output, sub_path)
            else:
                result = _resolve_dotted(context, path)
            return str(result) if result is not None else ""
        return re.sub(r"\{\{(.+?)\}\}", _replace, val)

    for key, val in cfg.items():
        if isinstance(val, str):
            kwargs[key] = _resolve_template(val)
        elif isinstance(val, (int, float, bool)):
            kwargs[key] = val

    return kwargs
