"""Legal Research Task Admin 测试 - 覆盖 LegalResearchTaskAdmin 未覆盖代码路径"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
from apps.legal_research.models import LegalResearchTask, LegalResearchTaskEvent
from apps.legal_research.models.task import LegalResearchTaskStatus, LegalResearchSearchMode

User = get_user_model()


def _make_admin():
    return LegalResearchTaskAdmin(LegalResearchTask, AdminSite())


def _make_request(method="GET", path="/admin/", data=None):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path, data or {})
    else:
        request = factory.post(path, data or {})
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestLegalResearchTaskAdminAttributes:
    """验证 Admin 配置属性"""

    def test_list_display(self):
        admin = _make_admin()
        assert "id" in admin.list_display
        assert "keyword" in admin.list_display
        assert "search_mode" in admin.list_display
        assert "status" in admin.list_display
        assert "progress" in admin.list_display
        assert "created_at" in admin.list_display

    def test_list_filter(self):
        admin = _make_admin()
        assert "status" in admin.list_filter
        assert "llm_backend" in admin.list_filter
        assert "created_at" in admin.list_filter

    def test_search_fields(self):
        admin = _make_admin()
        assert "id" in admin.search_fields
        assert "keyword" in admin.search_fields

    def test_readonly_fields(self):
        admin = _make_admin()
        assert "id" in admin.readonly_fields
        assert "created_by" in admin.readonly_fields
        assert "status" in admin.readonly_fields
        assert "private_api_stage_metrics" in admin.readonly_fields
        assert "private_api_event_timeline" in admin.readonly_fields
        assert "private_api_event_panel" in admin.readonly_fields
        assert "candidate_pool_hint" in admin.readonly_fields
        assert "cancel_task_button" in admin.readonly_fields

    def test_ordering(self):
        admin = _make_admin()
        assert "-created_at" in admin.ordering

    def test_actions(self):
        admin = _make_admin()
        assert "mark_as_missed_case_feedback" in admin.actions


@pytest.mark.django_db
class TestLegalResearchTaskAdminFields:
    """测试 get_fields / get_readonly_fields"""

    def test_get_fields_add_mode(self):
        admin = _make_admin()
        request = _make_request()
        with patch.object(admin, "_get_weike_credential_queryset") as mock_qs:
            mock_qs.return_value.count.return_value = 0
            fields = admin.get_fields(request, obj=None)
            assert "keyword" in fields
            assert "search_url" in fields

    def test_get_readonly_fields_edit_mode(self):
        admin = _make_admin()
        request = _make_request()
        obj = MagicMock(spec=LegalResearchTask)
        obj.status = LegalResearchTaskStatus.COMPLETED
        fields = admin.get_readonly_fields(request, obj=obj)
        assert isinstance(fields, list)
        assert len(fields) > 0

    def test_get_readonly_fields_add_mode(self):
        admin = _make_admin()
        request = _make_request()
        fields = admin.get_readonly_fields(request, obj=None)
        assert fields == []


@pytest.mark.django_db
class TestLegalResearchTaskAdminStaticMethods:
    """测试静态方法"""

    def test_is_cancellable_status_pending(self):
        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.PENDING) is True

    def test_is_cancellable_status_queued(self):
        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.QUEUED) is True

    def test_is_cancellable_status_running(self):
        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.RUNNING) is True

    def test_is_cancellable_status_completed(self):
        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.COMPLETED) is False

    def test_is_cancellable_status_failed(self):
        assert LegalResearchTaskAdmin._is_cancellable_status(LegalResearchTaskStatus.FAILED) is False

    def test_render_json_preview(self):
        result = LegalResearchTaskAdmin._render_json_preview({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_render_json_preview_none(self):
        result = LegalResearchTaskAdmin._render_json_preview(None)
        assert isinstance(result, str)

    def test_render_json_preview_long_content(self):
        long_data = {"data": "x" * 5000}
        result = LegalResearchTaskAdmin._render_json_preview(long_data, max_chars=100)
        assert len(result) <= 103  # 100 + "..."

    def test_render_json_preview_type_error(self):
        result = LegalResearchTaskAdmin._render_json_preview(set())
        assert isinstance(result, str)

    def test_build_error_distribution_empty(self):
        result = LegalResearchTaskAdmin._build_error_distribution(events=[])
        assert result == []

    def test_build_error_distribution_with_errors(self):
        event1 = MagicMock(error_code="ERR_001")
        event2 = MagicMock(error_code="ERR_001")
        event3 = MagicMock(error_code="ERR_002")
        event4 = MagicMock(error_code="")
        result = LegalResearchTaskAdmin._build_error_distribution(events=[event1, event2, event3, event4])
        assert len(result) == 2
        assert result[0] == ("ERR_001", 2)

    def test_get_private_api_events_empty(self):
        # Mock the queryset to avoid ORM issues with MagicMock
        with patch("apps.legal_research.admin.task_admin.LegalResearchTaskEvent") as MockEvent:
            MockEvent.objects.filter.return_value.order_by.return_value = []
            result = LegalResearchTaskAdmin._get_private_api_events(obj=MagicMock(pk=999999))
            assert isinstance(result, list)


@pytest.mark.django_db
class TestLegalResearchTaskAdminDisplayMethods:
    """测试 display 方法"""

    def test_cancel_task_button_cancellable(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.status = LegalResearchTaskStatus.RUNNING
        obj.pk = 1
        with patch("apps.legal_research.admin.task_admin.reverse", return_value="/admin/cancel/1/"):
            result = admin.cancel_task_button(obj)
            assert "取消任务" in result

    def test_cancel_task_button_not_cancellable(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.status = LegalResearchTaskStatus.COMPLETED
        result = admin.cancel_task_button(obj)
        assert result == "—"

    def test_candidate_pool_hint_not_completed(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.status = LegalResearchTaskStatus.RUNNING
        result = admin.candidate_pool_hint(obj)
        assert result == "—"

    def test_candidate_pool_hint_met_target(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.status = LegalResearchTaskStatus.COMPLETED
        obj.matched_count = 10
        obj.target_count = 10
        result = admin.candidate_pool_hint(obj)
        assert "已达到" in result

    def test_candidate_pool_hint_no_candidates(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.status = LegalResearchTaskStatus.COMPLETED
        obj.matched_count = 0
        obj.target_count = 5
        obj.candidate_count = 0
        result = admin.candidate_pool_hint(obj)
        assert "未检索到" in result

    def test_candidate_pool_hint_all_scanned(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.status = LegalResearchTaskStatus.COMPLETED
        obj.matched_count = 3
        obj.target_count = 10
        obj.candidate_count = 8
        obj.scanned_count = 8
        obj.max_candidates = 100
        result = admin.candidate_pool_hint(obj)
        assert "全部扫描" in result

    def test_candidate_pool_hint_max_scanned(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.status = LegalResearchTaskStatus.COMPLETED
        obj.matched_count = 3
        obj.target_count = 10
        obj.candidate_count = 50
        obj.scanned_count = 50
        obj.max_candidates = 50
        result = admin.candidate_pool_hint(obj)
        assert "最大上限" in result

    def test_result_attachments_empty(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.pk = 999999
        with patch("apps.legal_research.admin.task_admin.LegalResearchResult") as MockResult:
            MockResult.objects.filter.return_value.exclude.return_value.order_by.return_value = []
            result = admin.result_attachments(obj)
            assert result == "—"

    def test_private_api_stage_metrics_no_events(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.pk = 999999
        with patch("apps.legal_research.admin.task_admin.LegalResearchTaskEvent") as MockEvent:
            MockEvent.objects.filter.return_value.order_by.return_value = []
            result = admin.private_api_stage_metrics(obj)
            assert result == "—"

    def test_private_api_event_timeline_no_events(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.pk = 999999
        with patch("apps.legal_research.admin.task_admin.LegalResearchTaskEvent") as MockEvent:
            MockEvent.objects.filter.return_value.order_by.return_value = []
            result = admin.private_api_event_timeline(obj)
            assert result == "—"

    def test_private_api_event_panel_no_events(self):
        admin = _make_admin()
        obj = MagicMock(spec=LegalResearchTask)
        obj.pk = 999999
        with patch("apps.legal_research.admin.task_admin.LegalResearchTaskEvent") as MockEvent:
            MockEvent.objects.filter.return_value.order_by.return_value = []
            result = admin.private_api_event_panel(obj)
            assert result == "—"


@pytest.mark.django_db
class TestLegalResearchTaskAdminFeatureFlag:
    """测试功能开关"""

    def test_manual_switch_enabled_default(self):
        assert LegalResearchTaskAdmin._manual_switch_enabled() is False

    def test_is_feature_available(self):
        result = LegalResearchTaskAdmin._is_feature_available()
        assert isinstance(result, bool)

    def test_build_llm_model_choices(self):
        choices, is_fallback, error_msg = LegalResearchTaskAdmin._build_llm_model_choices()
        assert isinstance(choices, list)
        assert len(choices) > 0

    def test_should_show_private_api_visuals_no_obj(self):
        result = LegalResearchTaskAdmin._should_show_private_api_visuals(obj=None)
        assert isinstance(result, bool)

    def test_should_show_private_api_visuals_non_weike(self):
        obj = MagicMock(spec=LegalResearchTask)
        obj.source = "manual"
        result = LegalResearchTaskAdmin._should_show_private_api_visuals(obj=obj)
        assert result is False

    def test_filter_private_api_visual_fields(self):
        fields = ["id", "keyword", "private_api_stage_metrics", "private_api_event_timeline"]
        result = LegalResearchTaskAdmin._filter_private_api_visual_fields(fields, obj=None)
        assert isinstance(result, list)


@pytest.mark.django_db
class TestLegalResearchTaskAdminFormConfig:
    """测试表单配置方法"""

    def test_configure_search_field_field(self):
        # Deprecated method, should not raise
        LegalResearchTaskAdmin._configure_search_field_field(form=MagicMock())

    def test_configure_search_url_field(self):
        from types import SimpleNamespace

        form = SimpleNamespace()
        field = SimpleNamespace(help_text="old", required=True)
        field.widget = SimpleNamespace(attrs={})
        form.base_fields = {"search_url": field}
        LegalResearchTaskAdmin._configure_search_url_field(form=form)
        assert form.base_fields["search_url"].help_text == ""

    def test_configure_keyword_field(self):
        from types import SimpleNamespace

        form = SimpleNamespace()
        field = SimpleNamespace(help_text=None)
        field.widget = SimpleNamespace(attrs={})
        form.base_fields = {"keyword": field}
        LegalResearchTaskAdmin._configure_keyword_field(form=form)
        assert form.base_fields["keyword"].help_text is not None

    def test_configure_advanced_query_field(self):
        from types import SimpleNamespace

        form = SimpleNamespace()
        field = SimpleNamespace(required=True, help_text="")
        field.widget = SimpleNamespace(attrs={})
        form.base_fields = {"advanced_query": field}
        LegalResearchTaskAdmin._configure_advanced_query_field(form=form)
        assert form.base_fields["advanced_query"].required is False

    def test_configure_filter_fields(self):
        from types import SimpleNamespace

        form = SimpleNamespace()
        form.base_fields = {}
        for fname in ("court_filter", "cause_of_action_filter", "date_from", "date_to"):
            field = SimpleNamespace(required=True)
            field.widget = SimpleNamespace(attrs={})
            form.base_fields[fname] = field
        LegalResearchTaskAdmin._configure_filter_fields(form=form)
        assert form.base_fields["court_filter"].required is False
        assert form.base_fields["cause_of_action_filter"].required is False

    def test_configure_scan_threshold_fields(self):
        from types import SimpleNamespace

        form = SimpleNamespace()
        form.base_fields = {}
        for fname in ("max_candidates", "min_similarity_score"):
            field = SimpleNamespace(help_text="")
            field.widget = SimpleNamespace(attrs={})
            form.base_fields[fname] = field
        LegalResearchTaskAdmin._configure_scan_threshold_fields(form=form)
        assert "候选" in form.base_fields["max_candidates"].help_text or "扫描" in form.base_fields["max_candidates"].help_text

    def test_configure_concurrency_field(self):
        from types import SimpleNamespace

        form = SimpleNamespace()
        field = SimpleNamespace(required=True, initial=None, help_text="")
        field.widget = SimpleNamespace(attrs={})
        form.base_fields = {"llm_scoring_concurrency": field}
        LegalResearchTaskAdmin._configure_concurrency_field(form=form)
        assert field.required is False
        assert field.initial == 5

    def test_configure_search_mode_field(self):
        from types import SimpleNamespace

        form = SimpleNamespace()
        field = SimpleNamespace(required=True, initial=None, help_text="")
        form.base_fields = {"search_mode": field}
        LegalResearchTaskAdmin._configure_search_mode_field(form=form)
        assert field.required is False

    def test_attach_keyword_cleaner(self):
        form = MagicMock()
        LegalResearchTaskAdmin._attach_keyword_cleaner(form)
        assert hasattr(form, "clean_keyword")

    def test_attach_search_mode_cleaner(self):
        form = MagicMock()
        LegalResearchTaskAdmin._attach_search_mode_cleaner(form)
        assert hasattr(form, "clean_search_mode")
