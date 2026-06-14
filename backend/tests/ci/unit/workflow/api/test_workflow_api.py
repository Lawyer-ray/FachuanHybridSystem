"""Tests for workflow/api/workflow_api.py"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.workflow.api.workflow_api import (
    start_workflow_api,
    list_workflows_api,
    get_workflow_detail_api,
    approve_workflow_api,
    cancel_workflow_api,
    delete_workflow_api,
    get_steps_registry,
    get_steps_flat,
    list_templates,
    create_template,
    get_template,
    update_template,
    delete_template,
    duplicate_template,
)


# ── start_workflow_api ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_workflow_api():
    payload = MagicMock()
    payload.template_slug = "test-slug"
    payload.case_id = 1

    with patch("apps.workflow.api.workflow_api.start_workflow", new_callable=AsyncMock) as mock_start:
        mock_start.return_value = {"run_id": 1, "status": "running"}
        result = await start_workflow_api(MagicMock(), payload)

    assert result["status"] == "running"
    mock_start.assert_called_once_with("test-slug", 1)


# ── list_workflows_api ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_workflows_api():
    with patch("apps.workflow.api.workflow_api.list_workflows", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [{"run_id": 1}]
        result = await list_workflows_api(MagicMock(), case_id=1, status="running")

    assert len(result) == 1
    mock_list.assert_called_once_with(1, "running")


@pytest.mark.asyncio
async def test_list_workflows_api_no_filters():
    with patch("apps.workflow.api.workflow_api.list_workflows", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        result = await list_workflows_api(MagicMock(), case_id=None, status=None)

    assert result == []
    mock_list.assert_called_once_with(None, None)


# ── get_workflow_detail_api ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_workflow_detail_api():
    with patch("apps.workflow.api.workflow_api.get_workflow_detail", new_callable=AsyncMock) as mock_detail:
        mock_detail.return_value = {"run_id": 1, "status": "running"}
        result = await get_workflow_detail_api(MagicMock(), run_id=1)

    assert result["run_id"] == 1
    mock_detail.assert_called_once_with(1)


# ── approve_workflow_api ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_workflow_api_success():
    payload = MagicMock()
    payload.approved = True
    payload.comment = "ok"

    with patch("apps.workflow.api.workflow_api.approve_workflow_step", new_callable=AsyncMock) as mock_approve:
        mock_approve.return_value = {"run_id": 1, "action": "approved"}
        result = await approve_workflow_api(MagicMock(), run_id=1, payload=payload)

    assert result["action"] == "approved"


@pytest.mark.asyncio
async def test_approve_workflow_api_error():
    from ninja.errors import HttpError

    payload = MagicMock()
    payload.approved = True
    payload.comment = ""

    with patch("apps.workflow.api.workflow_api.approve_workflow_step", new_callable=AsyncMock) as mock_approve:
        mock_approve.return_value = {"error": "not found"}
        with pytest.raises(HttpError):
            await approve_workflow_api(MagicMock(), run_id=1, payload=payload)


# ── cancel_workflow_api ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_workflow_api_success():
    with patch("apps.workflow.api.workflow_api.cancel_workflow", new_callable=AsyncMock) as mock_cancel:
        mock_cancel.return_value = {"run_id": 1, "status": "cancelled"}
        result = await cancel_workflow_api(MagicMock(), run_id=1)

    assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_workflow_api_error():
    from ninja.errors import HttpError

    with patch("apps.workflow.api.workflow_api.cancel_workflow", new_callable=AsyncMock) as mock_cancel:
        mock_cancel.return_value = {"error": "not found"}
        with pytest.raises(HttpError):
            await cancel_workflow_api(MagicMock(), run_id=1)


# ── delete_workflow_api ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_workflow_api_success():
    with patch("apps.workflow.api.workflow_api.delete_workflow_run", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = {"run_id": 1, "message": "deleted"}
        result = await delete_workflow_api(MagicMock(), run_id=1)

    assert "deleted" in result["message"]


@pytest.mark.asyncio
async def test_delete_workflow_api_error():
    from ninja.errors import HttpError

    with patch("apps.workflow.api.workflow_api.delete_workflow_run", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = {"error": "not found"}
        with pytest.raises(HttpError):
            await delete_workflow_api(MagicMock(), run_id=1)


# ── get_steps_registry ────────────────────────────────────────────────────────

def test_get_steps_registry():
    with patch("apps.workflow.api.workflow_api.get_step_registry") as mock_registry:
        mock_registry.return_value = [{"id": "test"}]
        result = get_steps_registry(MagicMock())
    assert result == [{"id": "test"}]


# ── get_steps_flat ────────────────────────────────────────────────────────────

def test_get_steps_flat():
    with patch("apps.workflow.api.workflow_api.get_flat_step_list") as mock_flat:
        mock_flat.return_value = [{"id": "test"}]
        result = get_steps_flat(MagicMock())
    assert result == [{"id": "test"}]


# ── list_templates ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_list_templates_basic():
    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "Test"
        mock_t.slug = "test"
        mock_t.category = "litigation"
        mock_t.description = "desc"
        mock_t.is_active = True
        mock_t.steps_schema = [{"id": "s1"}]
        mock_t.temporal_workflow_name = "DW"
        mock_t.created_at = datetime(2025, 1, 1)
        mock_t.updated_at = datetime(2025, 1, 2)

        MockTemplate.objects.all.return_value = [mock_t]
        result = list_templates(MagicMock(), category=None, is_active=None)

    assert len(result) == 1
    assert result[0]["id"] == 1


@pytest.mark.django_db
def test_list_templates_with_filters():
    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.__iter__ = MagicMock(return_value=iter([]))
        MockTemplate.objects.all.return_value = mock_qs

        result = list_templates(MagicMock(), category="litigation", is_active=True)

    assert isinstance(result, list)


# ── create_template ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_create_template_basic():
    payload = MagicMock()
    payload.name = "Test Template"
    payload.slug = ""
    payload.category = "litigation"
    payload.description = "desc"
    payload.temporal_workflow_name = None
    payload.steps = None
    payload.is_active = None

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate, \
         patch("apps.workflow.api.workflow_api.slugify", return_value="test-template"):
        MockTemplate.objects.filter.return_value.exists.return_value = False
        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "Test Template"
        mock_t.slug = "test-template"
        MockTemplate.objects.create.return_value = mock_t

        result = create_template(MagicMock(), payload)

    assert result["id"] == 1
    assert "创建成功" in result["message"]


@pytest.mark.django_db
def test_create_template_with_slug():
    payload = MagicMock()
    payload.name = "Test"
    payload.slug = "my-slug"
    payload.category = "litigation"
    payload.description = ""
    payload.temporal_workflow_name = "DW"
    payload.steps = []
    payload.is_active = True

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        MockTemplate.objects.filter.return_value.exists.return_value = False
        mock_t = MagicMock()
        mock_t.id = 2
        mock_t.name = "Test"
        mock_t.slug = "my-slug"
        MockTemplate.objects.create.return_value = mock_t

        result = create_template(MagicMock(), payload)

    assert result["slug"] == "my-slug"


@pytest.mark.django_db
def test_create_template_slug_collision():
    payload = MagicMock()
    payload.name = "Test"
    payload.slug = ""
    payload.category = "litigation"
    payload.description = ""
    payload.temporal_workflow_name = None
    payload.steps = []
    payload.is_active = True

    call_count = 0

    def mock_exists():
        nonlocal call_count
        call_count += 1
        return call_count == 1

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate, \
         patch("apps.workflow.api.workflow_api.slugify", return_value="test"):
        MockTemplate.objects.filter.return_value.exists = mock_exists
        mock_t = MagicMock()
        mock_t.id = 3
        mock_t.name = "Test"
        mock_t.slug = "test-1"
        MockTemplate.objects.create.return_value = mock_t

        result = create_template(MagicMock(), payload)

    assert result["slug"] == "test-1"


# ── get_template ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_template_success():
    mock_t = MagicMock()
    mock_t.id = 1
    mock_t.name = "Test"
    mock_t.slug = "test"
    mock_t.category = "litigation"
    mock_t.description = "desc"
    mock_t.temporal_workflow_name = "DW"
    mock_t.steps_schema = []
    mock_t.is_active = True
    mock_t.created_at = datetime(2025, 1, 1)
    mock_t.updated_at = datetime(2025, 1, 2)

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        MockTemplate.objects.get.return_value = mock_t
        result = get_template(MagicMock(), template_id=1)

    assert result["id"] == 1
    assert result["name"] == "Test"


# ── update_template ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_update_template_name():
    payload = MagicMock()
    payload.name = "New Name"
    payload.slug = None
    payload.category = None
    payload.description = None
    payload.temporal_workflow_name = None
    payload.steps = None
    payload.is_active = None

    mock_t = MagicMock()
    mock_t.id = 1
    mock_t.name = "Old"
    mock_t.save = MagicMock()

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        MockTemplate.objects.get.return_value = mock_t
        result = update_template(MagicMock(), template_id=1, payload=payload)

    assert result["name"] == "New Name"
    mock_t.save.assert_called_once()


@pytest.mark.django_db
def test_update_template_steps():
    step_mock = MagicMock()
    step_mock.model_dump.return_value = {"id": "s1", "name": "Step 1"}

    payload = MagicMock()
    payload.name = None
    payload.slug = None
    payload.category = None
    payload.description = None
    payload.temporal_workflow_name = None
    payload.steps = [step_mock]
    payload.is_active = None

    mock_t = MagicMock()
    mock_t.id = 1
    mock_t.name = "Test"
    mock_t.save = MagicMock()

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        MockTemplate.objects.get.return_value = mock_t
        result = update_template(MagicMock(), template_id=1, payload=payload)

    assert "已更新" in result["message"]


@pytest.mark.django_db
def test_update_template_deactivate():
    payload = MagicMock()
    payload.name = None
    payload.slug = None
    payload.category = None
    payload.description = None
    payload.temporal_workflow_name = None
    payload.steps = None
    payload.is_active = False

    mock_t = MagicMock()
    mock_t.id = 1
    mock_t.name = "Test"
    mock_t.save = MagicMock()

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        MockTemplate.objects.get.return_value = mock_t
        result = update_template(MagicMock(), template_id=1, payload=payload)

    assert mock_t.is_active is False


# ── delete_template ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_delete_template():
    mock_t = MagicMock()
    mock_t.name = "Test"
    mock_t.delete = MagicMock()

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        MockTemplate.objects.get.return_value = mock_t
        result = delete_template(MagicMock(), template_id=1)

    assert "已删除" in result["message"]
    mock_t.delete.assert_called_once()


# ── duplicate_template ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_duplicate_template():
    source = MagicMock()
    source.name = "Original"
    source.slug = "original"
    source.category = "litigation"
    source.description = "desc"
    source.temporal_workflow_name = "DW"
    source.steps_schema = [{"id": "s1"}]

    new_t = MagicMock()
    new_t.id = 2
    new_t.name = "Original (副本)"
    new_t.slug = "original-copy"

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        MockTemplate.objects.get.return_value = source
        MockTemplate.objects.filter.return_value.exists.return_value = False
        MockTemplate.objects.create.return_value = new_t

        result = duplicate_template(MagicMock(), template_id=1)

    assert "已复制" in result["message"]
    assert result["id"] == 2


@pytest.mark.django_db
def test_duplicate_template_slug_collision():
    source = MagicMock()
    source.name = "Original"
    source.slug = "original"
    source.category = "litigation"
    source.description = ""
    source.temporal_workflow_name = "DW"
    source.steps_schema = []

    new_t = MagicMock()
    new_t.id = 3
    new_t.name = "Original (副本)"
    new_t.slug = "original-copy-1"

    call_count = 0

    def mock_exists():
        nonlocal call_count
        call_count += 1
        return call_count == 1

    with patch("apps.workflow.api.workflow_api.WorkflowTemplate") as MockTemplate:
        MockTemplate.objects.get.return_value = source
        MockTemplate.objects.filter.return_value.exists = mock_exists
        MockTemplate.objects.create.return_value = new_t

        result = duplicate_template(MagicMock(), template_id=1)

    assert result["slug"] == "original-copy-1"
