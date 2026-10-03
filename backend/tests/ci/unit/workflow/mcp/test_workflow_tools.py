"""Tests for workflow/mcp/workflow_tools.py"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from apps.workflow.models import WorkflowRun, WorkflowTemplate


# Helper to mock the ORM on real model classes
def _mock_objects(model_cls):
    """Context manager that patches model_cls.objects with a MagicMock."""
    return patch.object(model_cls, "objects")


@pytest.mark.asyncio
async def test_start_workflow_success():
    from apps.workflow.mcp.workflow_tools import start_workflow

    mock_template = MagicMock()
    mock_template.id = 1
    mock_template.name = "Test Template"
    mock_template.temporal_workflow_name = "DynamicWorkflow"

    mock_run = MagicMock()
    mock_run.id = 10

    mock_handle = AsyncMock()
    mock_handle.result_run_id = "tr-123"

    mock_client = AsyncMock()
    mock_client.start_workflow = AsyncMock(return_value=mock_handle)

    with (
        patch.object(WorkflowTemplate, "objects") as MockTemplateObjs,
        patch.object(WorkflowRun, "objects") as MockRunObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockTemplateObjs.aget = AsyncMock(return_value=mock_template)
        MockRunObjs.acreate = AsyncMock(return_value=mock_run)
        mock_run.asave = AsyncMock()

        result = await start_workflow("test-slug", case_id=1)

    assert result["run_id"] == 10
    assert result["status"] == "running"
    assert "test-slug" in result["workflow_id"]


@pytest.mark.asyncio
async def test_start_workflow_template_not_found():
    from apps.workflow.mcp.workflow_tools import start_workflow

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(side_effect=Exception("DoesNotExist"))
        with pytest.raises(Exception):
            await start_workflow("nonexistent-slug", case_id=1)


# ── list_workflows ────────────────────────────────────────────────────────────


class _AsyncIter:
    """把同步 list 包装成 async 迭代器（模拟 queryset 切片的 async for 行为）。"""

    def __init__(self, items):
        self._items = items

    async def _gen(self):
        for it in self._items:
            yield it

    def __aiter__(self):
        return self._gen()


def _mock_qs(runs, total):
    qs = MagicMock()
    qs.filter.return_value = qs
    ordered = MagicMock()
    qs.order_by.return_value = ordered
    ordered.acount = AsyncMock(return_value=total)
    ordered.__getitem__ = MagicMock(return_value=_AsyncIter(runs))
    return qs


@pytest.mark.asyncio
async def test_list_workflows_basic():
    from apps.workflow.mcp.workflow_tools import list_workflows

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.temporal_workflow_id = "wf-1"
    mock_run.template.name = "Template A"
    mock_run.case.name = "Case A"
    mock_run.status = "running"
    mock_run.current_step_id = "step1"
    mock_run.started_at = datetime(2025, 1, 1, 12, 0, 0)

    with patch.object(WorkflowRun, "objects") as MockObjs:
        MockObjs.select_related.return_value = _mock_qs([mock_run], total=1)

        result = await list_workflows(case_id=1, status="running")

    assert isinstance(result["items"], list)
    assert len(result["items"]) == 1
    assert result["total"] == 1
    assert result["page"] == 1
    assert result["page_size"] == 20
    assert result["total_pages"] == 1


@pytest.mark.asyncio
async def test_list_workflows_limit_cap():
    """limit cap：>100 收敛到 100，total_pages 按收敛后的 page_size 计算。"""
    from apps.workflow.mcp.workflow_tools import list_workflows

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.temporal_workflow_id = "wf-1"
    mock_run.template.name = "Template A"
    mock_run.case.name = "Case A"
    mock_run.status = "running"
    mock_run.current_step_id = "step1"
    mock_run.started_at = datetime(2025, 1, 1, 12, 0, 0)

    with patch.object(WorkflowRun, "objects") as MockObjs:
        MockObjs.select_related.return_value = _mock_qs([mock_run], total=150)

        result = await list_workflows(limit=999)

    assert result["page_size"] == 100  # cap 生效
    assert result["total"] == 150
    assert result["total_pages"] == 2


# ── get_workflow_detail ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_workflow_detail_success():
    from apps.workflow.mcp.workflow_tools import get_workflow_detail

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.template.name = "Template"
    mock_run.case.name = "Case"
    mock_run.status = "running"
    mock_run.current_step_id = "step1"
    mock_run.result = None
    mock_run.started_at = datetime(2025, 1, 1)
    mock_run.finished_at = None

    mock_step = MagicMock()
    mock_step.step_id = "collect_facts"
    mock_step.step_name = "Collect Facts"
    mock_step.step_type = "activity"
    mock_step.status = "success"
    mock_step.output_data = {"result": "data"}
    mock_step.error_message = None
    mock_step.started_at = datetime(2025, 1, 1, 12, 0, 0)
    mock_step.finished_at = datetime(2025, 1, 1, 12, 1, 0)

    async def mock_step_iter():
        yield mock_step

    with patch.object(WorkflowRun, "objects") as MockObjs:
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)
        mock_run.step_executions.all.return_value = mock_step_iter()

        result = await get_workflow_detail(1)

    assert result["run_id"] == 1
    assert result["template"] == "Template"
    assert result["status"] == "running"
    assert len(result["steps"]) == 1


@pytest.mark.asyncio
async def test_get_workflow_detail_with_finished_at():
    from apps.workflow.mcp.workflow_tools import get_workflow_detail

    mock_run = MagicMock()
    mock_run.id = 2
    mock_run.template.name = "T"
    mock_run.case.name = "C"
    mock_run.status = "completed"
    mock_run.current_step_id = ""
    mock_run.result = {"status": "completed"}
    mock_run.started_at = datetime(2025, 1, 1)
    mock_run.finished_at = datetime(2025, 1, 2)

    async def empty_iter():
        for _ in []:
            yield

    with patch.object(WorkflowRun, "objects") as MockObjs:
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)
        mock_run.step_executions.all.return_value = empty_iter()

        result = await get_workflow_detail(2)

    assert result["finished_at"] is not None


# ── approve_workflow_step ─────────────────────────────────────────────────────


def _mock_approve_run(
    *,
    step_id: str = "gate_1",
    steps_schema: list | None = None,
    workflow_name: str = "DynamicWorkflow",
) -> MagicMock:
    """构造 approve_workflow_step 用的 mock run（含模板步骤定义）。"""
    if steps_schema is None:
        steps_schema = [{"id": step_id, "type": "gate"}]
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.status = "waiting_human"
    mock_run.current_step_id = step_id
    mock_run.temporal_workflow_id = "wf-1"
    mock_run.template.steps_schema = steps_schema
    mock_run.template.temporal_workflow_name = workflow_name
    mock_run.asave = AsyncMock()
    return mock_run


def _mock_signal_client() -> tuple[MagicMock, MagicMock]:
    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)
    return mock_client, mock_handle


@pytest.mark.asyncio
async def test_approve_workflow_step_success():
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run()
    mock_client, mock_handle = _mock_signal_client()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=True, comment="ok")

    assert result["action"] == "approved"
    assert result["step_id"] == "gate_1"
    # gate 步骤未配置 signal_key → 回退通用 gate_approved
    assert result["signal_key"] == "gate_approved"
    mock_handle.signal.assert_awaited_once_with(
        "gate_approved", {"approved": True, "step_id": "gate_1", "comment": "ok"}
    )
    mock_run.asave.assert_awaited_once()
    assert mock_run.status == "running"


@pytest.mark.asyncio
async def test_approve_workflow_step_not_found():
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    with patch.object(WorkflowRun, "objects") as MockObjs:
        MockObjs.select_related.return_value.aget = AsyncMock(side_effect=WorkflowRun.DoesNotExist("nope"))

        result = await approve_workflow_step(999, approved=True)

    assert "error" in result


@pytest.mark.asyncio
async def test_approve_workflow_step_wrong_status():
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run()
    mock_run.status = "completed"

    with patch.object(WorkflowRun, "objects") as MockObjs:
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=True)

    assert "error" in result


@pytest.mark.asyncio
async def test_approve_workflow_step_temporal_failure():
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run()

    mock_client = MagicMock()
    mock_client.get_workflow_handle.side_effect = Exception("connection refused")

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=True)

    assert "error" in result
    assert "Temporal" in result["error"]


@pytest.mark.asyncio
async def test_approve_workflow_step_rejected():
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run()
    mock_client, mock_handle = _mock_signal_client()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=False, comment="not ready")

    assert result["action"] == "rejected"
    mock_handle.signal.assert_awaited_once_with(
        "gate_approved", {"approved": False, "step_id": "gate_1", "comment": "not ready"}
    )


# ── approve_workflow_step 信号名解析与校验 ───────────────────────────────────


@pytest.mark.asyncio
async def test_approve_uses_step_level_signal_key():
    """种子模板 gate 步骤（顶层 signal_key）→ 发送命名信号而非 gate_approved"""
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run(
        step_id="confirm_facts",
        steps_schema=[
            {"id": "collect_facts", "type": "activity"},
            {"id": "confirm_facts", "type": "gate", "signal_key": "confirm_facts_approved"},
            {"id": "review_complaint", "type": "gate", "signal_key": "review_complaint_approved"},
        ],
        workflow_name="SalesContractDisputeWorkflow",
    )
    mock_client, mock_handle = _mock_signal_client()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=True)

    assert result["signal_key"] == "confirm_facts_approved"
    mock_handle.signal.assert_awaited_once_with(
        "confirm_facts_approved",
        {"approved": True, "step_id": "confirm_facts", "comment": ""},
    )


@pytest.mark.asyncio
async def test_approve_uses_config_level_signal_key():
    """config 内 signal_key（步骤注册表 config_schema 表达）同样生效"""
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run(
        steps_schema=[{"id": "gate_1", "type": "gate", "config": {"signal_key": "review_complaint_approved"}}],
    )
    mock_client, mock_handle = _mock_signal_client()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=True)

    assert result["signal_key"] == "review_complaint_approved"
    mock_handle.signal.assert_awaited_once_with(
        "review_complaint_approved",
        {"approved": True, "step_id": "gate_1", "comment": ""},
    )


@pytest.mark.asyncio
async def test_approve_rejects_unknown_signal_key():
    """未知信号名（workflow 未注册）→ 明确报错，不发信号、不置 RUNNING"""
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run(
        steps_schema=[{"id": "gate_1", "type": "gate", "signal_key": "my_custom_signal"}],
    )
    mock_client, mock_handle = _mock_signal_client()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=True)

    assert "error" in result
    assert "my_custom_signal" in result["error"]
    mock_handle.signal.assert_not_awaited()
    mock_run.asave.assert_not_awaited()
    assert mock_run.status == "waiting_human"


@pytest.mark.asyncio
async def test_approve_rejects_signal_unsupported_by_workflow():
    """回退 gate_approved 但目标 workflow 未注册该信号 → 报错，避免静默丢弃"""
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run(
        step_id="confirm_facts",
        steps_schema=[{"id": "confirm_facts", "type": "gate"}],
        workflow_name="SalesContractDisputeWorkflow",
    )
    mock_client, mock_handle = _mock_signal_client()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=True)

    assert "error" in result
    assert "gate_approved" in result["error"]
    mock_handle.signal.assert_not_awaited()
    mock_run.asave.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_rejects_step_not_in_template():
    """current_step_id 在模板 steps 中无对应 gate 定义 → 报错"""
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run(
        step_id="ghost_step",
        steps_schema=[{"id": "gate_1", "type": "gate"}],
    )
    mock_client, mock_handle = _mock_signal_client()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=True)

    assert "error" in result
    assert "ghost_step" in result["error"]
    mock_handle.signal.assert_not_awaited()
    mock_run.asave.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_rejects_empty_steps_schema():
    """模板 steps_schema 为空（无法确定信号）→ 报错"""
    from apps.workflow.mcp.workflow_tools import approve_workflow_step

    mock_run = _mock_approve_run(steps_schema=[])
    mock_client, mock_handle = _mock_signal_client()

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await approve_workflow_step(1, approved=True)

    assert "error" in result
    mock_handle.signal.assert_not_awaited()
    mock_run.asave.assert_not_awaited()


# ── cancel_workflow ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_workflow_success():
    from apps.workflow.mcp.workflow_tools import cancel_workflow

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.temporal_workflow_id = "wf-1"
    mock_run.asave = AsyncMock()

    mock_handle = MagicMock()
    mock_handle.cancel = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.aget = AsyncMock(return_value=mock_run)

        result = await cancel_workflow(1)

    assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_workflow_not_found():
    from apps.workflow.mcp.workflow_tools import cancel_workflow

    with patch.object(WorkflowRun, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(side_effect=WorkflowRun.DoesNotExist("nope"))

        result = await cancel_workflow(999)

    assert "error" in result


@pytest.mark.asyncio
async def test_cancel_workflow_temporal_failure():
    from apps.workflow.mcp.workflow_tools import cancel_workflow

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.temporal_workflow_id = "wf-1"

    mock_client = MagicMock()
    mock_client.get_workflow_handle.side_effect = Exception("timeout")

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.aget = AsyncMock(return_value=mock_run)

        result = await cancel_workflow(1)

    assert "error" in result


# ── delete_workflow_run ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_workflow_run_success():
    from apps.workflow.mcp.workflow_tools import delete_workflow_run

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.status = "running"
    mock_run.temporal_workflow_id = "wf-1"
    mock_run.template.name = "Test Template"
    mock_run.adelete = AsyncMock()

    mock_handle = MagicMock()
    mock_handle.cancel = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)

    with (
        patch.object(WorkflowRun, "objects") as MockObjs,
        patch("apps.workflow.mcp.workflow_tools._get_client", return_value=mock_client),
    ):
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await delete_workflow_run(1)

    assert "已删除" in result["message"]


@pytest.mark.asyncio
async def test_delete_workflow_run_not_found():
    from apps.workflow.mcp.workflow_tools import delete_workflow_run

    with patch.object(WorkflowRun, "objects") as MockObjs:
        MockObjs.select_related.return_value.aget = AsyncMock(side_effect=WorkflowRun.DoesNotExist("nope"))

        result = await delete_workflow_run(999)

    assert "error" in result


@pytest.mark.asyncio
async def test_delete_workflow_run_completed_no_cancel():
    from apps.workflow.mcp.workflow_tools import delete_workflow_run

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.status = "completed"
    mock_run.template.name = "Template"
    mock_run.adelete = AsyncMock()

    with patch.object(WorkflowRun, "objects") as MockObjs:
        MockObjs.select_related.return_value.aget = AsyncMock(return_value=mock_run)

        result = await delete_workflow_run(1)

    assert "已删除" in result["message"]


# ── get_step_registry / get_step_registry_flat ────────────────────────────────


@pytest.mark.asyncio
async def test_get_step_registry():
    from apps.workflow.mcp.workflow_tools import get_step_registry

    result = await get_step_registry()
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_step_registry_flat():
    from apps.workflow.mcp.workflow_tools import get_step_registry_flat

    result = await get_step_registry_flat()
    assert isinstance(result, list)


# ── create_workflow_template ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_workflow_template_success():
    from apps.workflow.mcp.workflow_tools import create_workflow_template

    mock_template = MagicMock()
    mock_template.id = 1
    mock_template.name = "Test"
    mock_template.slug = "test"
    mock_template.category = "litigation"

    with patch.object(WorkflowTemplate, "objects") as MockObjs, patch("django.utils.text.slugify", return_value="test"):
        MockObjs.filter.return_value.aexists = AsyncMock(return_value=False)
        MockObjs.acreate = AsyncMock(return_value=mock_template)

        result = await create_workflow_template(
            name="Test",
            steps=[{"id": "s1", "name": "Step 1", "type": "activity"}],
        )

    assert result["template_id"] == 1
    assert result["steps_count"] == 1


@pytest.mark.asyncio
async def test_create_workflow_template_slug_collision():
    from apps.workflow.mcp.workflow_tools import create_workflow_template

    mock_template = MagicMock()
    mock_template.id = 2
    mock_template.name = "Test"
    mock_template.slug = "test-1"
    mock_template.category = "litigation"

    call_count = 0

    async def mock_exists():
        nonlocal call_count
        call_count += 1
        return call_count == 1

    with patch.object(WorkflowTemplate, "objects") as MockObjs, patch("django.utils.text.slugify", return_value="test"):
        MockObjs.filter.return_value.aexists = mock_exists
        MockObjs.acreate = AsyncMock(return_value=mock_template)

        result = await create_workflow_template(name="Test", steps=[])

    assert result["slug"] == "test-1"


@pytest.mark.asyncio
async def test_create_workflow_template_with_explicit_slug():
    from apps.workflow.mcp.workflow_tools import create_workflow_template

    mock_template = MagicMock()
    mock_template.id = 3
    mock_template.name = "Test"
    mock_template.slug = "my-slug"
    mock_template.category = "preservation"

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.acreate = AsyncMock(return_value=mock_template)

        result = await create_workflow_template(
            name="Test",
            steps=[],
            slug="my-slug",
            category="preservation",
        )

    assert result["slug"] == "my-slug"
    assert result["category"] == "preservation"


# ── update_workflow_template ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_workflow_template_not_found():
    from apps.workflow.mcp.workflow_tools import update_workflow_template

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(side_effect=WorkflowTemplate.DoesNotExist("nope"))

        result = await update_workflow_template(999, name="New Name")

    assert "error" in result


@pytest.mark.asyncio
async def test_update_workflow_template_no_fields():
    from apps.workflow.mcp.workflow_tools import update_workflow_template

    mock_template = MagicMock()
    mock_template.id = 1

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(return_value=mock_template)

        result = await update_workflow_template(1)

    assert "error" in result


@pytest.mark.asyncio
async def test_update_workflow_template_update_name():
    from apps.workflow.mcp.workflow_tools import update_workflow_template

    mock_template = MagicMock()
    mock_template.id = 1
    mock_template.name = "Old Name"
    mock_template.slug = "old"
    mock_template.steps_schema = []
    mock_template.asave = AsyncMock()

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(return_value=mock_template)

        result = await update_workflow_template(1, name="New Name")

    assert result["name"] == "New Name"
    assert "name" in result["updated_fields"]


@pytest.mark.asyncio
async def test_update_workflow_template_update_steps():
    from apps.workflow.mcp.workflow_tools import update_workflow_template

    mock_template = MagicMock()
    mock_template.id = 1
    mock_template.name = "T"
    mock_template.slug = "t"
    mock_template.steps_schema = []
    mock_template.asave = AsyncMock()

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(return_value=mock_template)

        result = await update_workflow_template(
            1,
            steps=[{"id": "s1", "name": "Step 1", "type": "activity"}],
        )

    assert "steps_schema" in result["updated_fields"]
    assert result["steps_count"] == 1


@pytest.mark.asyncio
async def test_update_workflow_template_deactivate():
    from apps.workflow.mcp.workflow_tools import update_workflow_template

    mock_template = MagicMock()
    mock_template.id = 1
    mock_template.name = "T"
    mock_template.slug = "t"
    mock_template.steps_schema = []
    mock_template.asave = AsyncMock()

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(return_value=mock_template)

        result = await update_workflow_template(1, is_active=False)

    assert "is_active" in result["updated_fields"]


# ── list_workflow_templates ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_workflow_templates():
    from apps.workflow.mcp.workflow_tools import list_workflow_templates

    mock_t = MagicMock()
    mock_t.id = 1
    mock_t.name = "T"
    mock_t.slug = "t"
    mock_t.category = "litigation"
    mock_t.description = "desc"
    mock_t.is_active = True
    mock_t.steps_schema = [{"id": "s1"}]
    mock_t.temporal_workflow_name = "DW"
    mock_t.created_at = datetime(2025, 1, 1)

    async def mock_aiter():
        yield mock_t

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_aiter()
        MockObjs.all.return_value = mock_qs

        result = await list_workflow_templates(category="litigation", is_active=True)

    assert isinstance(result, list)


# ── get_workflow_template ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_workflow_template_not_found():
    from apps.workflow.mcp.workflow_tools import get_workflow_template

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(side_effect=WorkflowTemplate.DoesNotExist("nope"))

        result = await get_workflow_template(999)

    assert "error" in result


@pytest.mark.asyncio
async def test_get_workflow_template_success():
    from apps.workflow.mcp.workflow_tools import get_workflow_template

    mock_t = MagicMock()
    mock_t.id = 1
    mock_t.name = "T"
    mock_t.slug = "t"
    mock_t.category = "litigation"
    mock_t.description = "desc"
    mock_t.temporal_workflow_name = "DW"
    mock_t.steps_schema = []
    mock_t.is_active = True
    mock_t.created_at = datetime(2025, 1, 1)
    mock_t.updated_at = datetime(2025, 1, 2)

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(return_value=mock_t)

        result = await get_workflow_template(1)

    assert result["template_id"] == 1
    assert result["name"] == "T"


# ── delete_workflow_template ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_workflow_template_not_found():
    from apps.workflow.mcp.workflow_tools import delete_workflow_template

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(side_effect=WorkflowTemplate.DoesNotExist("nope"))

        result = await delete_workflow_template(999)

    assert "error" in result


@pytest.mark.asyncio
async def test_delete_workflow_template_success():
    from apps.workflow.mcp.workflow_tools import delete_workflow_template

    mock_t = MagicMock()
    mock_t.id = 1
    mock_t.name = "Template"
    mock_t.adelete = AsyncMock()

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(return_value=mock_t)

        result = await delete_workflow_template(1)

    assert "已删除" in result["message"]


# ── duplicate_workflow_template ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_workflow_template_not_found():
    from apps.workflow.mcp.workflow_tools import duplicate_workflow_template

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(side_effect=WorkflowTemplate.DoesNotExist("nope"))

        result = await duplicate_workflow_template(999)

    assert "error" in result


@pytest.mark.asyncio
async def test_duplicate_workflow_template_success():
    from apps.workflow.mcp.workflow_tools import duplicate_workflow_template

    mock_source = MagicMock()
    mock_source.id = 1
    mock_source.name = "Original"
    mock_source.slug = "original"
    mock_source.category = "litigation"
    mock_source.description = "desc"
    mock_source.temporal_workflow_name = "DW"
    mock_source.steps_schema = [{"id": "s1"}]

    mock_new = MagicMock()
    mock_new.id = 2
    mock_new.name = "Copy"
    mock_new.slug = "copy"

    with patch.object(WorkflowTemplate, "objects") as MockObjs, patch("django.utils.text.slugify", return_value="copy"):
        MockObjs.aget = AsyncMock(return_value=mock_source)
        MockObjs.filter.return_value.aexists = AsyncMock(return_value=False)
        MockObjs.acreate = AsyncMock(return_value=mock_new)

        result = await duplicate_workflow_template(1)

    assert result["source_template_id"] == 1


@pytest.mark.asyncio
async def test_duplicate_workflow_template_with_new_name():
    from apps.workflow.mcp.workflow_tools import duplicate_workflow_template

    mock_source = MagicMock()
    mock_source.id = 1
    mock_source.name = "Original"
    mock_source.slug = "original"
    mock_source.category = "litigation"
    mock_source.description = "desc"
    mock_source.temporal_workflow_name = "DW"
    mock_source.steps_schema = []

    mock_new = MagicMock()
    mock_new.id = 3
    mock_new.name = "Custom Name"
    mock_new.slug = "custom-name"

    with (
        patch.object(WorkflowTemplate, "objects") as MockObjs,
        patch("django.utils.text.slugify", return_value="custom-name"),
    ):
        MockObjs.aget = AsyncMock(return_value=mock_source)
        MockObjs.filter.return_value.aexists = AsyncMock(return_value=False)
        MockObjs.acreate = AsyncMock(return_value=mock_new)

        result = await duplicate_workflow_template(1, new_name="Custom Name")

    assert result["name"] == "Custom Name"
