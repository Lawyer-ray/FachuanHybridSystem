"""Tests for workflow/api/template_api.py — Round 4 deeper coverage.

Covers: list_templates with category/is_active filters, create_template with
slug collision, create_template with empty slug, update_template with partial
fields, duplicate_template first try success, step_registry endpoints.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# list_templates — with filters
# ---------------------------------------------------------------------------


class TestListTemplatesFilters:
    @pytest.mark.asyncio
    async def test_with_category_filter(self):
        from apps.workflow.api.template_api import list_templates

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "T"
        mock_t.slug = "t"
        mock_t.category = "litigation"
        mock_t.description = ""
        mock_t.is_active = True
        mock_t.steps_schema = []
        mock_t.temporal_workflow_name = "DW"
        mock_t.created_at = datetime(2025, 1, 1)
        mock_t.updated_at = datetime(2025, 1, 2)

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            qs = MagicMock()
            qs_filtered = MagicMock()

            async def mock_aiter_filtered(self_list):
                yield mock_t

            qs_filtered.__aiter__ = mock_aiter_filtered
            qs.filter.return_value = qs_filtered
            MockModel.objects.all.return_value = qs
            result = await list_templates(MagicMock(), category="litigation", is_active=None)
        qs.filter.assert_called_once_with(category="litigation")

    @pytest.mark.asyncio
    async def test_with_is_active_filter(self):
        from apps.workflow.api.template_api import list_templates

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "T"
        mock_t.slug = "t"
        mock_t.category = "litigation"
        mock_t.description = ""
        mock_t.is_active = True
        mock_t.steps_schema = []
        mock_t.temporal_workflow_name = "DW"
        mock_t.created_at = datetime(2025, 1, 1)
        mock_t.updated_at = datetime(2025, 1, 2)

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            qs = MagicMock()
            qs_filtered = MagicMock()

            async def mock_aiter_filtered(self_list):
                yield mock_t

            qs_filtered.__aiter__ = mock_aiter_filtered
            qs.filter.return_value = qs_filtered
            MockModel.objects.all.return_value = qs
            result = await list_templates(MagicMock(), category=None, is_active=True)
        qs.filter.assert_called_once_with(is_active=True)

    @pytest.mark.asyncio
    async def test_with_both_filters(self):
        from apps.workflow.api.template_api import list_templates

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            qs = MagicMock()
            qs2 = MagicMock()
            qs3 = MagicMock()

            async def mock_aiter_empty(self_list):
                return
                yield  # pragma: no cover

            qs3.__aiter__ = mock_aiter_empty
            qs.filter.return_value = qs2
            qs2.filter.return_value = qs3
            MockModel.objects.all.return_value = qs
            result = await list_templates(MagicMock(), category="litigation", is_active=False)
        assert result == []


# ---------------------------------------------------------------------------
# create_template — slug collision
# ---------------------------------------------------------------------------


class TestCreateTemplateSlugCollision:
    @pytest.mark.asyncio
    async def test_slug_collision_generates_unique(self):
        from apps.workflow.api.template_api import create_template

        payload = MagicMock()
        payload.name = "Test"
        payload.slug = "test-slug"
        payload.category = "litigation"
        payload.description = ""
        payload.temporal_workflow_name = "DW"
        payload.steps = []
        payload.is_active = True

        call_count = 0

        def mock_filter(**kw):
            nonlocal call_count
            call_count += 1
            mock_qs = MagicMock()
            mock_qs.aexists = AsyncMock(return_value=call_count <= 2)  # first 2 collide
            return mock_qs

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "Test"
        mock_t.slug = "test-slug-2"

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.filter.side_effect = mock_filter
            MockModel.objects.acreate = AsyncMock(return_value=mock_t)
            result = await create_template(MagicMock(), payload)

        assert result["slug"] == "test-slug-2"


# ---------------------------------------------------------------------------
# create_template — no slug provided
# ---------------------------------------------------------------------------


class TestCreateTemplateNoSlug:
    @pytest.mark.asyncio
    async def test_generates_slug_from_name(self):
        from apps.workflow.api.template_api import create_template

        payload = MagicMock()
        payload.name = "My Template"
        payload.slug = ""  # empty slug
        payload.category = "litigation"
        payload.description = ""
        payload.temporal_workflow_name = "DW"
        payload.steps = []
        payload.is_active = True

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "My Template"
        mock_t.slug = "my-template"

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.filter.return_value.aexists = AsyncMock(return_value=False)
            MockModel.objects.acreate = AsyncMock(return_value=mock_t)
            result = await create_template(MagicMock(), payload)

        assert result["slug"] == "my-template"


# ---------------------------------------------------------------------------
# create_template — is_active defaults
# ---------------------------------------------------------------------------


class TestCreateTemplateDefaults:
    @pytest.mark.asyncio
    async def test_is_active_none_defaults_true(self):
        from apps.workflow.api.template_api import create_template

        payload = MagicMock()
        payload.name = "Test"
        payload.slug = "test"
        payload.category = "litigation"
        payload.description = ""
        payload.temporal_workflow_name = ""
        payload.steps = []
        payload.is_active = None

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "Test"
        mock_t.slug = "test"

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.filter.return_value.aexists = AsyncMock(return_value=False)
            MockModel.objects.acreate = AsyncMock(return_value=mock_t)
            result = await create_template(MagicMock(), payload)

        # Verify create was called with is_active=True (default)
        create_call = MockModel.objects.acreate.call_args
        assert create_call[1]["is_active"] is True

    @pytest.mark.asyncio
    async def test_temporal_workflow_name_defaults(self):
        from apps.workflow.api.template_api import create_template

        payload = MagicMock()
        payload.name = "Test"
        payload.slug = "test"
        payload.category = "litigation"
        payload.description = ""
        payload.temporal_workflow_name = ""
        payload.steps = []
        payload.is_active = True

        mock_t = MagicMock()
        mock_t.id = 1
        mock_t.name = "Test"
        mock_t.slug = "test"

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.filter.return_value.aexists = AsyncMock(return_value=False)
            MockModel.objects.acreate = AsyncMock(return_value=mock_t)
            result = await create_template(MagicMock(), payload)

        create_call = MockModel.objects.acreate.call_args
        assert create_call[1]["temporal_workflow_name"] == "DynamicWorkflow"


# ---------------------------------------------------------------------------
# update_template — partial fields
# ---------------------------------------------------------------------------


class TestUpdateTemplatePartial:
    @pytest.mark.asyncio
    async def test_only_name_updated(self):
        from apps.workflow.api.template_api import update_template

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
        mock_t.slug = "old"
        mock_t.category = "old-cat"
        mock_t.asave = AsyncMock()

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.aget = AsyncMock(return_value=mock_t)
            result = await update_template(MagicMock(), template_id=1, payload=payload)

        assert mock_t.name == "New Name"
        # Other fields should be unchanged
        assert mock_t.slug == "old"
        mock_t.asave.assert_called_once()

    @pytest.mark.asyncio
    async def test_only_is_active_updated(self):
        from apps.workflow.api.template_api import update_template

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
        mock_t.asave = AsyncMock()

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.aget = AsyncMock(return_value=mock_t)
            result = await update_template(MagicMock(), template_id=1, payload=payload)

        assert mock_t.is_active is False


# ---------------------------------------------------------------------------
# duplicate_template — no collision
# ---------------------------------------------------------------------------


class TestDuplicateTemplateNoCollision:
    @pytest.mark.asyncio
    async def test_first_slug_works(self):
        from apps.workflow.api.template_api import duplicate_template

        source = MagicMock()
        source.name = "Original"
        source.slug = "original"
        source.category = "litigation"
        source.description = "desc"
        source.temporal_workflow_name = "DW"
        source.steps_schema = [{"id": "s1"}]

        new_t = MagicMock()
        new_t.id = 10
        new_t.name = "Original (副本)"
        new_t.slug = "original-copy"

        with patch("apps.workflow.api.template_api.WorkflowTemplate") as MockModel:
            MockModel.objects.aget = AsyncMock(return_value=source)
            MockModel.objects.filter.return_value.aexists = AsyncMock(return_value=False)
            MockModel.objects.acreate = AsyncMock(return_value=new_t)
            result = await duplicate_template(MagicMock(), template_id=1)

        assert result["slug"] == "original-copy"
        assert "副本" in result["name"]


# ---------------------------------------------------------------------------
# step_registry endpoints (still sync)
# ---------------------------------------------------------------------------


class TestStepRegistryEndpoints:
    def test_get_steps_registry(self):
        from apps.workflow.api.template_api import get_steps_registry
        result = get_steps_registry(MagicMock())
        assert isinstance(result, list)
        assert len(result) > 0
        # Each category has an id and steps
        for cat in result:
            assert "id" in cat
            assert "steps" in cat

    def test_get_steps_flat(self):
        from apps.workflow.api.template_api import get_steps_flat
        result = get_steps_flat(MagicMock())
        assert isinstance(result, list)
        assert len(result) > 0
        # Each step has category_id and category_name
        for step in result:
            assert "category_id" in step
            assert "category_name" in step
