"""安全审计 A-01 纵深防御：DynamicWorkflow 对 code 步骤类型直接拒绝。

A-01 已从 worker 注册表移除 generic_code_exec，并禁掉 HTTP API 的 code 步骤
创建。此处补第二道闸门：即使某个写入入口漏了校验（历史上 MCP 的
create_workflow_template 正是如此），存量/新增模板也无法触发执行。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from apps.workflow.temporal.workflows import DynamicWorkflow


def _run_step(step_type: str, step: dict[str, Any] | None = None) -> Any:
    """直接调 _execute_step 走到 code 分支（绕过 Temporal workflow sandbox 限制）。"""
    wf = DynamicWorkflow()
    return wf._execute_step(
        step=step or {"type": step_type, "config": {"code": "print(1)"}},
        step_id="s1",
        step_name="恶意步骤",
        step_type=step_type,
        mcp_tool=None,
        case_id=1,
        run_id=2,
        context={},
        timeout_hours=1.0,
    )


@pytest.mark.asyncio
async def test_code_step_raises_application_error() -> None:
    """code 步骤必须抛非重试的 ApplicationError，而不是调度 activity。"""
    with patch("apps.workflow.temporal.workflows.workflow") as mock_workflow:
        mock_workflow.execute_activity = AsyncMock()
        with pytest.raises(ApplicationError) as exc_info:
            await _run_step("code")

    assert exc_info.value.type == "StepTypeForbidden"
    assert exc_info.value.non_retryable is True
    # 绝不能调度任何 activity（尤其不能调 generic_code_exec）
    mock_workflow.execute_activity.assert_not_called()


@pytest.mark.asyncio
async def test_code_step_rejection_mentions_audit_id() -> None:
    """错误信息带安全审计编号，便于运维追溯。"""
    with patch("apps.workflow.temporal.workflows.workflow") as mock_workflow:
        mock_workflow.execute_activity = AsyncMock()
        with pytest.raises(ApplicationError) as exc_info:
            await _run_step("code")

    assert "A-01" in str(exc_info.value)
