"""第四轮审查修复回归测试（workflow 域）。

覆盖：
- DynamicWorkflow on_fail 读取兼容步骤顶层与 config 内嵌两种表达
- list_workflows 有用户上下文时按案件访问权过滤（IDOR）
- approve 信号后置 RUNNING 改条件更新（不覆盖 worker 终态竞态）
- update_template slug 唯一化（撞车不再 500）
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.workflow.models import WorkflowRun, WorkflowTemplate
from apps.workflow.schemas.workflow_schemas import TemplateUpdateIn
from apps.workflow.services import get_workflow_template_service

# ── Item 8: on_fail 兼容顶层与 config 两处 ─────────────────────────────────────


class TestResolveOnFail:
    def _resolve(self, step: dict) -> str:
        from apps.workflow.temporal.workflows import _resolve_on_fail

        return _resolve_on_fail(step)

    def test_top_level_on_fail_skip(self):
        """写入端（StepConfigIn/MCP/种子模板）在步骤顶层——on_fail=skip 生效，失败步骤被跳过。"""
        assert self._resolve({"id": "s1", "on_fail": "skip"}) == "skip"

    def test_config_on_fail_skip(self):
        """存量模板的 config 内嵌表达同样生效。"""
        assert self._resolve({"id": "s1", "config": {"on_fail": "skip"}}) == "skip"

    def test_default_abort(self):
        assert self._resolve({"id": "s1"}) == "abort"
        assert self._resolve({"id": "s1", "config": {}}) == "abort"

    def test_empty_top_level_falls_back_to_config(self):
        assert self._resolve({"id": "s1", "on_fail": "", "config": {"on_fail": "skip"}}) == "skip"

    def test_top_level_takes_precedence(self):
        assert self._resolve({"id": "s1", "on_fail": "abort", "config": {"on_fail": "skip"}}) == "abort"


# ── Item 9: list_workflows 按案件访问权过滤 ────────────────────────────────────


def _mock_run() -> MagicMock:
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.temporal_workflow_id = "wf-1"
    mock_run.template.name = "Template A"
    mock_run.case.name = "Case A"
    mock_run.status = "running"
    mock_run.current_step_id = "step1"
    mock_run.started_at = datetime(2025, 1, 1, 12, 0, 0)
    return mock_run


def _mock_qs(runs, total):
    class _AsyncIter:
        async def _gen(self):
            for it in runs:
                yield it

        def __aiter__(self):
            return self._gen()

    qs = MagicMock()
    qs.filter.return_value = qs
    ordered = MagicMock()
    qs.order_by.return_value = ordered
    ordered.acount = AsyncMock(return_value=total)
    ordered.__getitem__ = MagicMock(return_value=_AsyncIter())
    return qs


@pytest.mark.asyncio
async def test_list_workflows_filters_by_case_access():
    """有用户上下文时按 CaseAccessPolicy 过滤出可访问案件，run queryset 加 case_id__in。"""
    from apps.workflow.mcp.workflow_tools import list_workflows

    user = MagicMock(name="lawyer")
    org_access = {"extra_cases": {7}}
    accessible = MagicMock(name="accessible_values_qs")

    qs = _mock_qs([_mock_run()], total=1)
    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.cases.services.case.case_access_policy.CaseAccessPolicy") as MockPolicy,
    ):
        MockObjs.select_related.return_value = qs
        MockPolicy.return_value.filter_queryset.return_value = accessible

        result = await list_workflows(user=user, org_access=org_access, perm_open_access=False)

    assert result["total"] == 1
    MockPolicy.return_value.filter_queryset.assert_called_once()
    filter_call = qs.filter.call_args
    assert filter_call is not None
    assert filter_call.kwargs.get("case_id__in") is accessible
    # 传给策略的用户上下文原样透传
    policy_call = MockPolicy.return_value.filter_queryset.call_args
    assert policy_call.kwargs.get("user") is user
    assert policy_call.kwargs.get("org_access") is org_access
    assert policy_call.kwargs.get("perm_open_access") is False


@pytest.mark.asyncio
async def test_list_workflows_without_user_keeps_mcp_semantics():
    """MCP 直连（无用户上下文）不过滤——与 start_workflow 口径一致。"""
    from apps.workflow.mcp.workflow_tools import list_workflows

    qs = _mock_qs([_mock_run()], total=1)
    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.cases.services.case.case_access_policy.CaseAccessPolicy") as MockPolicy,
    ):
        MockObjs.select_related.return_value = qs
        result = await list_workflows()

    assert result["total"] == 1
    MockPolicy.assert_not_called()
    qs.filter.assert_not_called()


# ── Item 10: approve 条件更新 RUNNING ─────────────────────────────────────────


def _mock_approve_run() -> MagicMock:
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.status = "waiting_human"
    mock_run.current_step_id = "gate_1"
    mock_run.temporal_workflow_id = "wf-1"
    mock_run.template.steps_schema = [{"id": "gate_1", "type": "gate"}]
    mock_run.template.temporal_workflow_name = "DynamicWorkflow"
    return mock_run


def _mock_signal_client() -> tuple[MagicMock, MagicMock]:
    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)
    return mock_client, mock_handle


@pytest.mark.asyncio
async def test_approve_conditionally_sets_running():
    """审批成功后仅当 run 仍为 WAITING_HUMAN 时置 RUNNING（不覆盖 worker 终态）。"""
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run()
    mock_client, mock_handle = _mock_signal_client()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)
        MockObjs.filter.return_value.aupdate = AsyncMock(return_value=1)

        result = await approve_workflow_step(1, approved=True, comment="ok")

    assert result["action"] == "approved"
    mock_handle.signal.assert_awaited_once()
    MockObjs.filter.assert_called_once_with(pk=1, status=WorkflowRun.Status.WAITING_HUMAN)
    MockObjs.filter.return_value.aupdate.assert_awaited_once_with(status=WorkflowRun.Status.RUNNING)


@pytest.mark.asyncio
async def test_court_reply_conditionally_sets_running():
    """法院回复事件恢复同样走条件更新（dispatcher 与 approve 同口径）。"""
    from apps.workflow.events.dispatcher import on_court_reply

    mock_run = _mock_approve_run()
    mock_run.status = "waiting_event"

    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)

    class _RunAsyncIter:
        async def _gen(self):
            yield mock_run

        def __aiter__(self):
            return self._gen()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.events.dispatcher._get_client", return_value=mock_client),
    ):
        MockObjs.filter.return_value = _RunAsyncIter()
        # 同一个 filter mock 也被条件更新复用：filter(pk=..., status=...).aupdate(...)
        MockObjs.filter.return_value.aupdate = AsyncMock(return_value=1)
        await on_court_reply(case_id=1, status="ok")

    mock_handle.signal.assert_awaited_once()
    MockObjs.filter.assert_any_call(pk=mock_run.pk, status=WorkflowRun.Status.WAITING_EVENT)
    MockObjs.filter.return_value.aupdate.assert_awaited_once_with(status=WorkflowRun.Status.RUNNING)


# ── Item 12: update_template slug 唯一化 ──────────────────────────────────────


@pytest.mark.django_db
class TestUpdateTemplateSlugUniqueness:
    def test_duplicate_slug_gets_suffix(self):
        svc = get_workflow_template_service()
        existing = WorkflowTemplate.objects.create(
            name="模板A", slug="taken-slug", category="litigation", temporal_workflow_name="DW", steps_schema=[]
        )
        target = WorkflowTemplate.objects.create(
            name="模板B", slug="other-slug", category="litigation", temporal_workflow_name="DW", steps_schema=[]
        )

        result = svc.update_template(target.pk, TemplateUpdateIn(slug="taken-slug"))

        target.refresh_from_db()
        assert target.slug == "taken-slug-1"
        assert result["id"] == target.pk
        existing.refresh_from_db()
        assert existing.slug == "taken-slug"

    def test_own_slug_unchanged_no_suffix(self):
        """更新时保留自身 slug 不加后缀（排除自身）。"""
        svc = get_workflow_template_service()
        target = WorkflowTemplate.objects.create(
            name="模板C", slug="keep-me", category="litigation", temporal_workflow_name="DW", steps_schema=[]
        )

        svc.update_template(target.pk, TemplateUpdateIn(slug="keep-me"))

        target.refresh_from_db()
        assert target.slug == "keep-me"


# ── Item 13: approve 审批留痕（acted_by/acted_at 落库） ────────────────────────


def _create_waiting_run_for_audit():
    """构造等待人工审批的 run + gate 步骤 StepExecution（真实 DB，同步）。"""
    from apps.cases.models import Case
    from apps.organization.models import Lawyer
    from apps.workflow.models import StepExecution

    user = Lawyer.objects.create(username="audit-approver")
    case = Case.objects.create(name="审批留痕测试案件")
    template = WorkflowTemplate.objects.create(
        name="留痕模板",
        slug="audit-trail-tpl",
        category="litigation",
        temporal_workflow_name="DynamicWorkflow",
        steps_schema=[{"id": "gate_1", "type": "gate"}],
    )
    run = WorkflowRun.objects.create(
        template=template,
        case=case,
        temporal_workflow_id="wf-audit-trail",
        temporal_run_id="tr-audit-trail",
        status=WorkflowRun.Status.WAITING_HUMAN,
        current_step_id="gate_1",
    )
    step_exec = StepExecution.objects.create(
        workflow_run=run,
        step_id="gate_1",
        step_name="人工审批",
        step_type="gate",
        status=StepExecution.Status.WAITING,
    )
    return user, run, step_exec


def _mock_signal_client_ok() -> MagicMock:
    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)
    return mock_client


@pytest.mark.django_db
def test_approve_records_acted_by_and_acted_at():
    """审批通过后 gate 步骤的 StepExecution 落库 acted_by/acted_at。

    经 async_to_sync 调用（与 social_auth 测试约定一致）：async 代码内的
    thread_sensitive sync_to_async 绑回本线程执行，连接/事务与测试数据同源，
    不会逃逸测试事务。
    """
    from asgiref.sync import async_to_sync

    from apps.workflow.mcp.workflow_tools import approve_workflow_step
    from apps.workflow.models import StepExecution

    user, run, step_exec = _create_waiting_run_for_audit()
    mock_client = _mock_signal_client_ok()

    with patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client):
        result = async_to_sync(approve_workflow_step)(run.pk, True, "ok", user=user)

    assert result["action"] == "approved"
    step_exec.refresh_from_db()
    assert step_exec.acted_by_id == user.pk
    assert step_exec.acted_at is not None
    # 仅写留痕字段，不覆盖等待状态（终态由 worker 的 record_step 回写）
    assert step_exec.status == StepExecution.Status.WAITING


@pytest.mark.django_db
def test_approve_rejection_also_recorded():
    """审批拒绝同样是人工动作，同样留痕。"""
    from asgiref.sync import async_to_sync

    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    user, run, step_exec = _create_waiting_run_for_audit()
    mock_client = _mock_signal_client_ok()

    with patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client):
        result = async_to_sync(approve_workflow_step)(run.pk, False, "not ready", user=user)

    assert result["action"] == "rejected"
    step_exec.refresh_from_db()
    assert step_exec.acted_by_id == user.pk
    assert step_exec.acted_at is not None


@pytest.mark.django_db
def test_approve_without_user_keeps_trace_empty():
    """MCP 直连（无用户上下文）不留痕——字段保持为空。"""
    from asgiref.sync import async_to_sync

    from apps.workflow.mcp.workflow_tools import approve_workflow_step
    from apps.workflow.models import StepExecution

    _, run, step_exec = _create_waiting_run_for_audit()
    mock_client = _mock_signal_client_ok()

    with patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client):
        result = async_to_sync(approve_workflow_step)(run.pk, True, "ok")

    assert result["action"] == "approved"
    step_exec.refresh_from_db()
    assert step_exec.acted_by_id is None
    assert step_exec.acted_at is None
    assert step_exec.status == StepExecution.Status.WAITING
