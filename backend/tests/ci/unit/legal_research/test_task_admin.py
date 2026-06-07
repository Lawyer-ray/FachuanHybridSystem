"""Unit tests for legal_research.admin.task_admin."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestLegalResearchTaskAdminHelpers:
    """测试 LegalResearchTaskAdmin 的辅助方法"""

    def _make_admin(self):
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
        from apps.legal_research.models import LegalResearchTask

        admin = LegalResearchTaskAdmin(LegalResearchTask, MagicMock())
        return admin

    def test_is_cancellable_status_pending(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
        from apps.legal_research.models.task import LegalResearchTaskStatus

        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.PENDING) is True

    def test_is_cancellable_status_queued(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
        from apps.legal_research.models.task import LegalResearchTaskStatus

        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.QUEUED) is True

    def test_is_cancellable_status_running(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
        from apps.legal_research.models.task import LegalResearchTaskStatus

        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.RUNNING) is True

    def test_is_cancellable_status_completed(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
        from apps.legal_research.models.task import LegalResearchTaskStatus

        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.COMPLETED) is False

    def test_is_cancellable_status_failed(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
        from apps.legal_research.models.task import LegalResearchTaskStatus

        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.FAILED) is False

    def test_build_error_distribution(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        events = [
            MagicMock(error_code="C_001"),
            MagicMock(error_code="C_001"),
            MagicMock(error_code="C_002"),
            MagicMock(error_code=""),
        ]
        result = LegalResearchTaskAdmin._build_error_distribution(events=events)
        assert result[0] == ("C_001", 2)
        assert result[1] == ("C_002", 1)

    def test_build_error_distribution_empty(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        assert LegalResearchTaskAdmin._build_error_distribution(events=[]) == []

    def test_render_json_preview(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        result = LegalResearchTaskAdmin._render_json_preview({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_render_json_preview_truncates(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        big_data = {"key": "x" * 3000}
        result = LegalResearchTaskAdmin._render_json_preview(big_data, max_chars=100)
        assert len(result) <= 103  # 100 + "..."

    def test_render_json_preview_none(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        result = LegalResearchTaskAdmin._render_json_preview(None)
        assert isinstance(result, str)

    def test_should_show_private_api_visuals_no_obj(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        result = LegalResearchTaskAdmin._should_show_private_api_visuals(obj=None)
        assert isinstance(result, bool)

    def test_filter_private_api_visual_fields(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        fields = ["id", "keyword", "private_api_metrics", "private_api_timeline"]
        # When not showing private API visuals, private_api_ fields should be filtered
        result = LegalResearchTaskAdmin._filter_private_api_visual_fields(fields, obj=None)
        # Result depends on _should_show_private_api_visuals
        assert isinstance(result, list)

    def test_is_feature_available(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        result = LegalResearchTaskAdmin._is_feature_available()
        assert isinstance(result, bool)

    def test_manual_switch_enabled(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        result = LegalResearchTaskAdmin._manual_switch_enabled()
        assert isinstance(result, bool)

    def test_render_json_preview_invalid_type(self) -> None:
        from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin

        # Passing non-serializable object
        result = LegalResearchTaskAdmin._render_json_preview(object())
        assert isinstance(result, str)
