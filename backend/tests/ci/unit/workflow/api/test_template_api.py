"""Tests for workflow/api/template_api.py — additional branch coverage.

Covers: list_templates with steps_schema as dict, create_template with steps,
get_template, update_template all fields, duplicate_template slug collision.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# list_templates — steps_schema edge cases
# ---------------------------------------------------------------------------


class TestListTemplatesBranches:
    @pytest.mark.asyncio
    async def test_steps_schema_as_dict(self):
        """steps_schema that's not a list should give steps_count=0."""
        from apps.workflow.api.template_api import list_templates

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "Test"
        mock_t.slug = "test"
        mock_t.category = "litigation"
        mock_t.description = "desc"
        mock_t.is_active = True
        mock_t.steps_schema = {"steps": ["a", "b"]}  # dict, not list
        mock_t.temporal_workflow_name = "DW"
        mock_t.created_at = datetime(2025, 1, 1)
        mock_t.updated_at = datetime(2025, 1, 2)

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            async def mock_aiter(self_list):
                yield mock_t
            MockModel.objects.all.return_value.__aiter__ = mock_aiter
            result = await list_templates(MagicMock(), category=None, is_active=None)
        assert result[0]["steps_count"] == 0

    @pytest.mark.asyncio
    async def test_steps_schema_as_list(self):
        from apps.workflow.api.template_api import list_templates

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "Test"
        mock_t.slug = "test"
        mock_t.category = "litigation"
        mock_t.description = "desc"
        mock_t.is_active = True
        mock_t.steps_schema = [{"id": "s1"}, {"id": "s2"}]
        mock_t.temporal_workflow_name = "DW"
        mock_t.created_at = datetime(2025, 1, 1)
        mock_t.updated_at = datetime(2025, 1, 2)

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            async def mock_aiter(self_list):
                yield mock_t
            MockModel.objects.all.return_value.__aiter__ = mock_aiter
            result = await list_templates(MagicMock(), category=None, is_active=None)
        assert result[0]["steps_count"] == 2


# ---------------------------------------------------------------------------
# create_template with steps
# ---------------------------------------------------------------------------


class TestCreateTemplateWithSteps:
    @pytest.mark.asyncio
    async def test_with_steps(self):
        from apps.workflow.api.template_api import create_template

        step = MagicMock()
        step.model_dump.return_value = {"id": "s1", "name": "Step 1", "type": "activity"}

        payload = MagicMock()
        payload.name = "With Steps"
        payload.slug = "with-steps"
        payload.category = "litigation"
        payload.description = "desc"
        payload.temporal_workflow_name = "DW"
        payload.steps = [step]
        payload.is_active = True

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.filter.return_value.aexists = AsyncMock(return_value=False)
            mock_t = MagicMock()
            mock_t.id = 1
            mock_t.name = "With Steps"
            mock_t.slug = "with-steps"
            MockModel.objects.acreate = AsyncMock(return_value=mock_t)
            result = await create_template(MagicMock(), payload)

        assert result["id"] == 1


# ---------------------------------------------------------------------------
# get_template
# ---------------------------------------------------------------------------


class TestGetTemplateBranches:
    @pytest.mark.asyncio
    async def test_all_fields_present(self):
        from apps.workflow.api.template_api import get_template

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "Test"
        mock_t.slug = "test"
        mock_t.category = "litigation"
        mock_t.description = "desc"
        mock_t.temporal_workflow_name = "DW"
        mock_t.steps_schema = [{"id": "s1"}]
        mock_t.is_active = True
        mock_t.created_at = datetime(2025, 1, 1)
        mock_t.updated_at = datetime(2025, 1, 2)

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.aget = AsyncMock(return_value=mock_t)
            result = await get_template(MagicMock(), template_id=1)

        assert result["temporal_workflow_name"] == "DW"
        assert result["steps_schema"] == [{"id": "s1"}]
        assert result["is_active"] is True


# ---------------------------------------------------------------------------
# update_template — all fields
# ---------------------------------------------------------------------------


class TestUpdateTemplateAllFields:
    @pytest.mark.asyncio
    async def test_update_all_fields(self):
        from apps.workflow.api.template_api import update_template

        step = MagicMock()
        step.model_dump.return_value = {"id": "new_step"}

        payload = MagicMock()
        payload.name = "New Name"
        payload.slug = "new-slug"
        payload.category = "new-cat"
        payload.description = "new desc"
        payload.temporal_workflow_name = "NewDW"
        payload.steps = [step]
        payload.is_active = False

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "Old"
        mock_t.asave = AsyncMock()

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.aget = AsyncMock(return_value=mock_t)
            result = await update_template(MagicMock(), template_id=1, payload=payload)

        assert mock_t.name == "New Name"
        assert mock_t.slug == "new-slug"
        assert mock_t.category == "new-cat"
        assert mock_t.description == "new desc"
        assert mock_t.temporal_workflow_name == "NewDW"
        assert mock_t.steps_schema == [{"id": "new_step"}]
        assert mock_t.is_active is False
        mock_t.asave.assert_called_once()


# ---------------------------------------------------------------------------
# delete_template
# ---------------------------------------------------------------------------


class TestDeleteTemplate:
    @pytest.mark.asyncio
    async def test_returns_message_with_name(self):
        from apps.workflow.api.template_api import delete_template

        mock_t = MagicMock()
        mock_t.name = "My Template"
        mock_t.adelete = AsyncMock()

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.aget = AsyncMock(return_value=mock_t)
            result = await delete_template(MagicMock(), template_id=1)

        assert "My Template" in result["message"]


# ---------------------------------------------------------------------------
# duplicate_template — slug collision edge cases
# ---------------------------------------------------------------------------


class TestDuplicateTemplateEdgeCases:
    @pytest.mark.asyncio
    async def test_multiple_collisions(self):
        from apps.workflow.api.template_api import duplicate_template

        source = MagicMock()
        source.name = "Original"
        source.slug = "original"
        source.category = "litigation"
        source.description = ""
        source.temporal_workflow_name = "DW"
        source.steps_schema = []

        new_t = MagicMock()
        new_t.id = 10
        new_t.name = "Original (副本)"
        new_t.slug = "original-copy-5"

        call_count = 0

        async def mock_aexists():
            nonlocal call_count
            call_count += 1
            return call_count <= 5  # first 5 collisions

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.aget = AsyncMock(return_value=source)
            MockModel.objects.filter.return_value.aexists = mock_aexists
            MockModel.objects.acreate = AsyncMock(return_value=new_t)
            result = await duplicate_template(MagicMock(), template_id=1)

        assert result["slug"] == "original-copy-5"
        assert call_count == 6  # original + 5 collisions + final success
