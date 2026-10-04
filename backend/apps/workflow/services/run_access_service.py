"""工作流运行访问校验服务。

承载 workflow_api 下沉的 IDOR 防护：按 run_id 定位所属案件并校验当前
用户的案件访问权。run 不存在抛 ``NotFoundError``（HTTP 404），无权访问
由 ``CaseAccessPolicy`` 的异常语义决定（HTTP 403）。
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async

from apps.core.exceptions import NotFoundError


class WorkflowRunAccessService:
    """工作流 run 与案件的访问校验。"""

    async def ensure_run_case_access(self, *, run_id: int, ctx: Any) -> None:
        """校验当前用户对工作流 run 所属案件的访问权（安全审计 IDOR）。

        Raises:
            NotFoundError: 工作流运行不存在（HTTP 404）。
        """
        from apps.cases.services.case.case_access_policy import CaseAccessPolicy
        from apps.workflow.models import WorkflowRun

        try:
            case_id = await sync_to_async(
                WorkflowRun.objects.values_list("case_id", flat=True).get, thread_sensitive=False
            )(pk=run_id)
        except WorkflowRun.DoesNotExist:
            raise NotFoundError(f"工作流运行 #{run_id} 不存在") from None
        await sync_to_async(CaseAccessPolicy().ensure_access_ctx, thread_sensitive=False)(case_id=case_id, ctx=ctx)
