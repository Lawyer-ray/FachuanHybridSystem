"""Temporal Workflow 定义。

Workflow 函数必须满足确定性约束：
  ✅ 可以做: 调 activity、if/else、for 循环、信号接收
  ❌ 不能做: datetime.now()、random、I/O、ORM 调用
所有"脏活"放 Activity，workflow 只做编排。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from apps.workflow.temporal import activities as act


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

        await workflow.execute_activity(
            act.record_step,
            args=(
                run_id, "confirm_facts", "确认事实", "gate",
                "success" if self._gate.approved else "failed",
                {"comment": self._gate.comment},
            ),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        if not self._gate.approved:
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "failed", "confirm_facts"),
                start_to_close_timeout=QUICK_TIMEOUT,
                retry_policy=QUICK_RETRY,
            )
            return {"status": "rejected", "phase": "confirm_facts", "comment": self._gate.comment}

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

        await workflow.execute_activity(
            act.record_step,
            args=(
                run_id, "review_complaint", "审批起诉状", "gate",
                "success" if self._gate.approved else "failed",
                {"comment": self._gate.comment},
            ),
            start_to_close_timeout=QUICK_TIMEOUT,
            retry_policy=QUICK_RETRY,
        )

        if not self._gate.approved:
            await workflow.execute_activity(
                act.update_run_status,
                args=(run_id, "failed", "review_complaint"),
                start_to_close_timeout=QUICK_TIMEOUT,
                retry_policy=QUICK_RETRY,
            )
            return {"status": "rejected", "phase": "review_complaint", "comment": self._gate.comment}

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
