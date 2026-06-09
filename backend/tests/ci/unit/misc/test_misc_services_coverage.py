"""story_viz + document_delivery 补充覆盖测试。"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest


# ── StoryAnimationJobService ──────────────────────────────────────

class TestStoryAnimationJobServiceCreateFromAdmin:
    @pytest.mark.django_db
    def test_empty_title_raises(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        from apps.core.exceptions import ValidationException

        svc = StoryAnimationJobService()
        with pytest.raises(ValidationException, match="标题"):
            svc.create_from_admin(source_title="", source_text="正文", viz_type="timeline")

    @pytest.mark.django_db
    def test_empty_text_raises(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        from apps.core.exceptions import ValidationException

        svc = StoryAnimationJobService()
        with pytest.raises(ValidationException, match="正文"):
            svc.create_from_admin(source_title="标题", source_text="", viz_type="timeline")


class TestStoryAnimationConstants:
    def test_pipeline_stages(self):
        from apps.story_viz.services.job_service import _PIPELINE_STAGES
        assert len(_PIPELINE_STAGES) == 5
        assert _PIPELINE_STAGES[0][0] == "extracting_facts"

    def test_max_items(self):
        from apps.story_viz.services.job_service import _MAX_ITEMS
        assert _MAX_ITEMS == 20


# ── DocumentDelivery matching ─────────────────────────────────────

class TestDocumentDeliveryMatching:
    def test_import(self):
        """Verify the matching module is importable."""
        from apps.automation.services.document_delivery.api.document_delivery_api_service import _matching
        assert _matching is not None


# ── DocumentDelivery process ──────────────────────────────────────

class TestDocumentDeliveryProcess:
    def test_import(self):
        """Verify the process module is importable."""
        from apps.automation.services.document_delivery.api.document_delivery_api_service import _process
        assert _process is not None


# ── DocumentDelivery query ────────────────────────────────────────

class TestDocumentDeliveryQuery:
    def test_import(self):
        """Verify the query module is importable."""
        from apps.automation.services.document_delivery.api.document_delivery_api_service import _query
        assert _query is not None
