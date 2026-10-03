"""WorkflowRunAccessService 单元测试。

覆盖 run 不存在（NotFoundError → 404）与命中后委托
CaseAccessPolicy.ensure_access_ctx（case_id 取自 run）两条路径。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.workflow.services.run_access_service import WorkflowRunAccessService


@pytest.mark.asyncio
async def test_missing_run_raises_not_found() -> None:
    ctx = MagicMock()
    with (
        patch("apps.workflow.models.WorkflowRun") as mock_run,
        patch("apps.cases.services.case.case_access_policy.CaseAccessPolicy") as mock_policy,
    ):
        mock_run.DoesNotExist = type("DoesNotExist", (Exception,), {})
        # sync_to_async 包装的 get 抛 DoesNotExist
        mock_run.objects.values_list.return_value.get.side_effect = mock_run.DoesNotExist
        with pytest.raises(NotFoundError, match="工作流运行 #404 不存在"):
            await WorkflowRunAccessService().ensure_run_case_access(run_id=404, ctx=ctx)
    mock_policy.assert_not_called()


@pytest.mark.asyncio
async def test_existing_run_delegates_case_access_policy() -> None:
    ctx = MagicMock()
    with (
        patch("apps.workflow.models.WorkflowRun") as mock_run,
        patch("apps.cases.services.case.case_access_policy.CaseAccessPolicy") as mock_policy,
    ):
        mock_run.objects.values_list.return_value.get.return_value = 42
        mock_policy.return_value.ensure_access_ctx = MagicMock()

        await WorkflowRunAccessService().ensure_run_case_access(run_id=7, ctx=ctx)

    mock_policy.return_value.ensure_access_ctx.assert_called_once_with(case_id=42, ctx=ctx)
