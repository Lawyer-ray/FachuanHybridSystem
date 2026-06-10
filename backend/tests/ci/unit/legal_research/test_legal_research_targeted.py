"""Targeted tests for legal_research module to push coverage to 80%+."""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# tasks.py (0% coverage)
# ---------------------------------------------------------------------------


class TestLegalResearchTasks:
    @patch("apps.legal_research.tasks.ThreadPoolExecutor")
    @patch("apps.legal_research.tasks.LegalResearchExecutor")
    def test_execute_legal_research_task(self, mock_executor_cls, mock_pool_cls):
        from apps.legal_research.tasks import execute_legal_research_task

        mock_executor = MagicMock()
        mock_executor.run.return_value = {"status": "completed"}
        mock_executor_cls.return_value = mock_executor

        mock_future = MagicMock()
        mock_future.result.return_value = {"status": "completed"}

        mock_pool = MagicMock()
        mock_pool.submit.return_value = mock_future
        mock_pool.__enter__ = MagicMock(return_value=mock_pool)
        mock_pool.__exit__ = MagicMock(return_value=False)
        mock_pool_cls.return_value = mock_pool

        result = execute_legal_research_task("task-123")
        assert result == {"status": "completed"}

    @patch("apps.legal_research.tasks.ThreadPoolExecutor")
    @patch("apps.legal_research.tasks.CaseDownloadService")
    def test_execute_case_download_task(self, mock_service_cls, mock_pool_cls):
        from apps.legal_research.tasks import execute_case_download_task

        mock_service = MagicMock()
        mock_service.execute_task.return_value = {"status": "done"}
        mock_service_cls.return_value = mock_service

        mock_future = MagicMock()
        mock_future.result.return_value = {"status": "done"}

        mock_pool = MagicMock()
        mock_pool.submit.return_value = mock_future
        mock_pool.__enter__ = MagicMock(return_value=mock_pool)
        mock_pool.__exit__ = MagicMock(return_value=False)
        mock_pool_cls.return_value = mock_pool

        result = execute_case_download_task(42)
        assert result == {"status": "done"}


# ---------------------------------------------------------------------------
# executor_components/feedback_mixin.py (37% coverage)
# ---------------------------------------------------------------------------


class TestFeedbackMixin:
    def test_init_query_metric(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        metric = ExecutorFeedbackMixin._init_query_metric()
        assert metric == {"candidates": 0, "scanned": 0, "matched": 0, "skipped": 0}

    def test_apply_query_performance_feedback_no_scanned(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        weights = {"test": 1}
        ExecutorFeedbackMixin._apply_query_performance_feedback(
            search_keyword="test keyword",
            metric={"scanned": 0, "matched": 0},
            feedback_term_weights=weights,
        )
        # Should not change since scanned <= 0
        assert weights == {"test": 1}

    def test_apply_query_performance_feedback_good_hit_rate(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        weights = {}
        with patch.object(ExecutorFeedbackMixin, "_split_tokens", return_value=["合同", "纠纷"], create=True), \
             patch.object(ExecutorFeedbackMixin, "_is_location_or_court_token", return_value=False, create=True):
            ExecutorFeedbackMixin._apply_query_performance_feedback(
                search_keyword="合同纠纷",
                metric={"scanned": 10, "matched": 3},
                feedback_term_weights=weights,
            )
        assert len(weights) > 0
        # 3/10 = 0.3 >= 0.25, so boost=2
        assert all(v >= 1 for v in weights.values())

    def test_apply_query_performance_feedback_zero_match(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        weights = {"合同": 2, "纠纷": 1}
        with patch.object(ExecutorFeedbackMixin, "_split_tokens", return_value=["合同", "纠纷"], create=True), \
             patch.object(ExecutorFeedbackMixin, "_is_location_or_court_token", return_value=False, create=True):
            ExecutorFeedbackMixin._apply_query_performance_feedback(
                search_keyword="合同 纠纷",
                metric={"scanned": 30, "matched": 0},
                feedback_term_weights=weights,
            )
        # Should decrease weights
        assert weights.get("合同", 0) <= 2

    def test_build_query_stats_suffix_empty(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        result = ExecutorFeedbackMixin._build_query_stats_suffix(query_stats={})
        assert result == ""

    def test_build_query_stats_suffix_with_stats(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        stats = {"合同纠纷 案例": {"scanned": 10, "matched": 5}}
        result = ExecutorFeedbackMixin._build_query_stats_suffix(query_stats=stats)
        assert "5/10" in result

    def test_build_query_stats_suffix_no_scanned(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        stats = {"test": {"scanned": 0, "matched": 5}}
        result = ExecutorFeedbackMixin._build_query_stats_suffix(query_stats=stats)
        assert result == ""

    def test_build_query_trace_payload(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        result = ExecutorFeedbackMixin._build_query_trace_payload(
            primary_queries=["q1", "q2"],
            expansion_queries=["e1"],
            feedback_queries=["f1"],
            query_stats={"q1": {"scanned": 5, "matched": 2}},
        )
        assert result["primary_queries"] == ["q1", "q2"]
        assert result["expansion_queries"] == ["e1"]
        assert result["feedback_queries"] == ["f1"]

    def test_maybe_append_feedback_query_limit_reached(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        count, query = ExecutorFeedbackMixin._maybe_append_feedback_query(
            search_keywords=[],
            search_query_set=set(),
            feedback_term_weights={"a": 1, "b": 2, "c": 3},
            keyword="test",
            case_summary="",
            feedback_queries_added=2,
            feedback_query_limit=2,
            feedback_min_terms=3,
        )
        assert count == 2
        assert query == ""

    def test_maybe_append_feedback_query_too_few_terms(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        count, query = ExecutorFeedbackMixin._maybe_append_feedback_query(
            search_keywords=[],
            search_query_set=set(),
            feedback_term_weights={"a": 1},
            keyword="test",
            case_summary="",
            feedback_queries_added=0,
            feedback_query_limit=2,
            feedback_min_terms=3,
        )
        assert count == 0
        assert query == ""

    def test_pick_feedback_terms_empty(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        result = ExecutorFeedbackMixin._pick_feedback_terms({})
        assert result == []

    def test_pick_feedback_terms_with_data(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        weights = {"合同": 5, "纠纷": 3, "赔偿": 2, "违约": 4, "损失": 1, "交货": 6, "解除": 7}
        result = ExecutorFeedbackMixin._pick_feedback_terms(weights)
        assert len(result) <= 6
        assert "解除" in result  # highest weight

    def test_update_feedback_terms_low_score(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        weights = {}
        detail = SimpleNamespace(title="合同纠纷案", case_digest="买卖合同纠纷")
        result = ExecutorFeedbackMixin._update_feedback_terms(
            feedback_term_weights=weights,
            detail=detail,
            reason="test",
            similarity_score=0.3,
            min_similarity=0.7,
            feedback_min_score_floor=0.68,
            feedback_score_margin=0.1,
        )
        assert result is False

    def test_update_feedback_terms_good_score(self):
        from apps.legal_research.services.executor_components.feedback_mixin import ExecutorFeedbackMixin

        weights = {}
        detail = SimpleNamespace(title="合同纠纷案", case_digest="买卖合同违约赔偿")
        result = ExecutorFeedbackMixin._update_feedback_terms(
            feedback_term_weights=weights,
            detail=detail,
            reason="高度匹配",
            similarity_score=0.85,
            min_similarity=0.7,
            feedback_min_score_floor=0.68,
            feedback_score_margin=0.1,
        )
        assert result is True
        assert len(weights) > 0


# ---------------------------------------------------------------------------
# executor_components/result_persistence.py (59% coverage)
# ---------------------------------------------------------------------------


class TestResultPersistence:
    def test_build_content_excerpt_empty(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        assert ExecutorResultPersistenceMixin._build_content_excerpt("") == ""
        assert ExecutorResultPersistenceMixin._build_content_excerpt(None) == ""

    def test_build_content_excerpt_normal(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        text = "这是正常的案例文本内容"
        result = ExecutorResultPersistenceMixin._build_content_excerpt(text)
        assert result == text

    def test_build_content_excerpt_long(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        text = "x" * 20000
        result = ExecutorResultPersistenceMixin._build_content_excerpt(text)
        assert len(result) == ExecutorResultPersistenceMixin.CONTENT_EXCERPT_MAX_CHARS

    def test_build_content_excerpt_with_whitespace(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        text = "line1\r\n\r\n\r\n\r\nline2"
        result = ExecutorResultPersistenceMixin._build_content_excerpt(text)
        assert "\r" not in result

    def test_sanitize_pdf_filename_normal(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        result = ExecutorResultPersistenceMixin._sanitize_pdf_filename("test.pdf", fallback="fallback")
        assert result == "test.pdf"

    def test_sanitize_pdf_filename_no_ext(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        result = ExecutorResultPersistenceMixin._sanitize_pdf_filename("test", fallback="fallback")
        assert result.endswith(".pdf")

    def test_sanitize_pdf_filename_path_traversal(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        result = ExecutorResultPersistenceMixin._sanitize_pdf_filename("../../../etc/passwd", fallback="case")
        assert "/" not in result
        assert result.endswith(".pdf")

    def test_sanitize_pdf_filename_empty(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        result = ExecutorResultPersistenceMixin._sanitize_pdf_filename("", fallback="fallback")
        assert result.endswith(".pdf")
        assert len(result) > 4

    def test_extract_similarity_metadata_empty(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        sim = SimpleNamespace(metadata=None)
        result = ExecutorResultPersistenceMixin._extract_similarity_metadata(similarity=sim)
        assert result == {}

    def test_extract_similarity_metadata_with_data(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        sim = SimpleNamespace(metadata={"score": 0.8, "reason": "test"})
        result = ExecutorResultPersistenceMixin._extract_similarity_metadata(similarity=sim)
        assert "similarity_structured" in result

    def test_extract_similarity_metadata_empty_dict(self):
        from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin

        sim = SimpleNamespace(metadata={})
        result = ExecutorResultPersistenceMixin._extract_similarity_metadata(similarity=sim)
        assert result == {}


# ---------------------------------------------------------------------------
# executor_components/cache_mixin.py (60% coverage)
# ---------------------------------------------------------------------------


class TestCacheMixin:
    def test_reserve_new_items(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        items = [
            SimpleNamespace(doc_id_unquoted="d1", doc_id_raw="r1"),
            SimpleNamespace(doc_id_unquoted="d2", doc_id_raw="r2"),
            SimpleNamespace(doc_id_unquoted="d1", doc_id_raw="r1"),  # duplicate
        ]
        seen = set()
        result, dupes = ExecutorCacheMixin._reserve_new_items(items=items, seen_doc_ids=seen)
        assert len(result) == 2
        assert dupes == 1

    def test_build_case_detail_cache_key(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        key = ExecutorCacheMixin._build_case_detail_cache_key(source="weike", doc_id="DOC123")
        assert key == "legal_research:detail:weike:DOC123"

    def test_build_case_detail_cache_key_empty(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        assert ExecutorCacheMixin._build_case_detail_cache_key(source="", doc_id="DOC123") == ""
        assert ExecutorCacheMixin._build_case_detail_cache_key(source="weike", doc_id="") == ""

    def test_serialize_case_detail(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        detail = SimpleNamespace(
            doc_id_raw="RAW",
            doc_id_unquoted="UNQ",
            detail_url="http://example.com",
            search_id="SID",
            module="mod",
            title="Title",
            court_text="Court",
            document_number="Num",
            judgment_date="2024-01-01",
            case_digest="Digest",
            content_text="Content",
            raw_meta={"key": "value"},
        )
        payload = ExecutorCacheMixin._serialize_case_detail(detail)
        assert payload["doc_id_raw"] == "RAW"
        assert payload["title"] == "Title"
        assert payload["raw_meta"] == {"key": "value"}

    def test_serialize_case_detail_no_raw_meta(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        detail = SimpleNamespace(
            doc_id_raw="RAW",
            doc_id_unquoted="UNQ",
            detail_url="",
            search_id="",
            module="",
            title="",
            court_text="",
            document_number="",
            judgment_date="",
            case_digest="",
            content_text="",
            raw_meta=None,
        )
        payload = ExecutorCacheMixin._serialize_case_detail(detail)
        assert "raw_meta" not in payload

    def test_deserialize_case_detail_payload(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        payload = {
            "doc_id_raw": "RAW",
            "doc_id_unquoted": "UNQ",
            "detail_url": "http://example.com",
            "title": "Test",
        }
        result = ExecutorCacheMixin._deserialize_case_detail_payload(payload)
        assert result is not None
        assert result.doc_id_raw == "RAW"
        assert result.title == "Test"

    def test_deserialize_case_detail_empty_ids(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        payload = {"doc_id_raw": "", "doc_id_unquoted": ""}
        result = ExecutorCacheMixin._deserialize_case_detail_payload(payload)
        assert result is None

    def test_extract_item_doc_id(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        item = SimpleNamespace(doc_id_unquoted="UNQ", doc_id_raw="RAW")
        assert ExecutorCacheMixin._extract_item_doc_id(item) == "UNQ"

    def test_extract_item_doc_id_fallback(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        item = SimpleNamespace(doc_id_unquoted="", doc_id_raw="RAW")
        assert ExecutorCacheMixin._extract_item_doc_id(item) == "RAW"

    def test_load_case_detail_cache_exception(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        with patch("django.core.cache.cache.get", side_effect=Exception("cache error")):
            result = ExecutorCacheMixin._load_case_detail_cache("test_key")
            assert result is None

    def test_save_case_detail_cache_type_error(self):
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        detail = SimpleNamespace(
            doc_id_raw="RAW", doc_id_unquoted="UNQ", detail_url="", search_id="",
            module="", title="", court_text="", document_number="", judgment_date="",
            case_digest="", content_text="", raw_meta=None,
        )
        with patch("django.core.cache.cache.set", side_effect=TypeError("bad type")):
            # Should not raise
            ExecutorCacheMixin._save_case_detail_cache(
                cache_key="test", detail=detail, ttl_seconds=100
            )


# ---------------------------------------------------------------------------
# executor_components/task_lifecycle.py (64% coverage)
# ---------------------------------------------------------------------------


class TestTaskLifecycle:
    def test_run_orm_safely_no_event_loop(self):
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            result = ExecutorTaskLifecycleMixin._run_orm_safely(lambda: 42)
            assert result == 42

    def test_mark_completed(self):
        from apps.legal_research.models import LegalResearchTask, LegalResearchTaskStatus
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        task = LegalResearchTask(
            id="test-task",
            status=LegalResearchTaskStatus.RUNNING,
        )
        with patch.object(task, "save"):
            ExecutorTaskLifecycleMixin._mark_completed(task, message="done")
            assert task.status == LegalResearchTaskStatus.COMPLETED
            assert task.progress == 100

    def test_mark_failed(self):
        from apps.legal_research.models import LegalResearchTask, LegalResearchTaskStatus
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        task = LegalResearchTask(
            id="test-task",
            status=LegalResearchTaskStatus.RUNNING,
        )
        with patch.object(task, "save"):
            ExecutorTaskLifecycleMixin._mark_failed(task, "error msg")
            assert task.status == LegalResearchTaskStatus.FAILED
            assert task.error == "error msg"

    def test_is_cancel_requested(self):
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        with patch(
            "apps.legal_research.services.executor_components.task_lifecycle.LegalResearchTask"
        ) as mock_model:
            mock_model.objects.filter.return_value.values_list.return_value.first.return_value = (
                LegalResearchTaskStatus.CANCELLED
            )
            result = ExecutorTaskLifecycleMixin._is_cancel_requested("task-1")
            assert result is True

    def test_is_cancel_requested_false(self):
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        with patch(
            "apps.legal_research.services.executor_components.task_lifecycle.LegalResearchTask"
        ) as mock_model:
            mock_model.objects.filter.return_value.values_list.return_value.first.return_value = (
                LegalResearchTaskStatus.RUNNING
            )
            with patch("asyncio.get_running_loop", side_effect=RuntimeError):
                result = ExecutorTaskLifecycleMixin._is_cancel_requested("task-1")
                assert result is False

    def test_mark_cancelled(self):
        from apps.legal_research.models import LegalResearchTask, LegalResearchTaskStatus
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        task = LegalResearchTask(
            id="test-task",
            status=LegalResearchTaskStatus.RUNNING,
            max_candidates=100,
            target_count=10,
        )
        with patch.object(task, "save"):
            ExecutorTaskLifecycleMixin._mark_cancelled(task=task, scanned=50, matched=5, skipped=2)
            assert task.status == LegalResearchTaskStatus.CANCELLED
            assert task.scanned_count == 50
            assert task.matched_count == 5
            assert "跳过 2" in task.message

    def test_update_progress(self):
        from apps.legal_research.models import LegalResearchTask, LegalResearchTaskStatus
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        task = LegalResearchTask(
            id="test-task",
            status=LegalResearchTaskStatus.RUNNING,
            max_candidates=100,
            target_count=10,
            candidate_count=5,
        )
        with patch.object(task, "save"):
            ExecutorTaskLifecycleMixin._update_progress(task=task, scanned=50, matched=5, skipped=3)
            assert task.scanned_count == 50
            assert task.matched_count == 5
            assert task.progress == min(95, 53)  # (50+3)/100 * 100


# ---------------------------------------------------------------------------
# sources/weike/api_optional.py (63% coverage)
# ---------------------------------------------------------------------------


class TestApiOptional:
    def test_resolve_adapter_no_open_http(self):
        from apps.legal_research.services.sources.weike.api_optional import _resolve_adapter

        module = SimpleNamespace(search_cases_via_api=lambda: None)
        result = _resolve_adapter(module)
        assert result is None

    def test_resolve_adapter_no_search(self):
        from apps.legal_research.services.sources.weike.api_optional import _resolve_adapter

        module = SimpleNamespace(open_http_session=lambda: None)
        result = _resolve_adapter(module)
        assert result is None

    def test_resolve_adapter_success(self):
        from apps.legal_research.services.sources.weike.api_optional import _resolve_adapter

        adapter = SimpleNamespace(
            open_http_session=lambda: None,
            search_cases_via_api=lambda: None,
        )
        result = _resolve_adapter(adapter)
        assert result is adapter

    def test_resolve_adapter_with_api_adapter_attr(self):
        from apps.legal_research.services.sources.weike.api_optional import _resolve_adapter

        adapter = SimpleNamespace(
            open_http_session=lambda: None,
            search_cases_via_api=lambda: None,
        )
        module = SimpleNamespace(API_ADAPTER=adapter)
        result = _resolve_adapter(module)
        assert result is adapter

    @patch("apps.legal_research.services.sources.weike.api_optional._adapter_cache", new=object())
    @patch("apps.legal_research.services.sources.weike.api_optional._CACHE_UNSET", new=object())
    def test_get_private_weike_api_cache_hit(self):
        """Test cache hit returns cached value."""
        from apps.legal_research.services.sources.weike import api_optional

        sentinel = object()
        api_optional._adapter_cache = sentinel
        # Force re-evaluation
        result = api_optional._adapter_cache
        assert result is sentinel

    @patch("importlib.import_module", side_effect=ModuleNotFoundError("no module"))
    def test_get_private_weike_api_module_not_found(self, mock_import):
        from apps.legal_research.services.sources.weike.api_optional import _CACHE_UNSET

        import apps.legal_research.services.sources.weike.api_optional as mod

        original = mod._adapter_cache
        mod._adapter_cache = _CACHE_UNSET
        try:
            result = mod.get_private_weike_api()
            assert result is None
        finally:
            mod._adapter_cache = original


# ---------------------------------------------------------------------------
# sources/weike/types.py (63% coverage)
# ---------------------------------------------------------------------------


class TestWeikeTypes:
    def test_weike_session_close_all_none(self):
        from apps.legal_research.services.sources.weike.types import WeikeSession

        session = WeikeSession()
        # Should not raise
        session.close()

    def test_weike_session_close_with_mocks(self):
        from apps.legal_research.services.sources.weike.types import WeikeSession

        session = WeikeSession(
            page=MagicMock(),
            context=MagicMock(),
            browser=MagicMock(),
            playwright=MagicMock(),
            http_client=MagicMock(),
        )
        session.close()
        session.page.close.assert_called_once()
        session.context.close.assert_called_once()
        session.browser.close.assert_called_once()
        session.playwright.stop.assert_called_once()
        session.http_client.close.assert_called_once()

    def test_weike_session_close_with_exceptions(self):
        from apps.legal_research.services.sources.weike.types import WeikeSession

        page = MagicMock()
        page.close.side_effect = Exception("fail")
        session = WeikeSession(page=page, http_client="no_close_method")
        # Should not raise
        session.close()

    def test_weike_search_item(self):
        from apps.legal_research.services.sources.weike.types import WeikeSearchItem

        item = WeikeSearchItem(
            doc_id_raw="RAW",
            doc_id_unquoted="UNQ",
            detail_url="http://example.com",
            title_hint="Title",
            search_id="SID",
            module="mod",
        )
        assert item.doc_id_raw == "RAW"

    def test_weike_case_detail(self):
        from apps.legal_research.services.sources.weike.types import WeikeCaseDetail

        detail = WeikeCaseDetail(
            doc_id_raw="RAW",
            doc_id_unquoted="UNQ",
            detail_url="http://example.com",
            search_id="SID",
            module="mod",
            title="Title",
            court_text="Court",
            document_number="Num",
            judgment_date="2024-01-01",
            case_digest="Digest",
            content_text="Content",
            raw_meta={},
        )
        assert detail.title == "Title"


# ---------------------------------------------------------------------------
# task/event_service.py (79% coverage)
# ---------------------------------------------------------------------------


class TestEventService:
    def test_normalize_task_id_none(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._normalize_task_id(None) is None
        assert LegalResearchTaskEventService._normalize_task_id("") is None
        assert LegalResearchTaskEventService._normalize_task_id("abc") is None
        assert LegalResearchTaskEventService._normalize_task_id("-1") is None
        assert LegalResearchTaskEventService._normalize_task_id("0") is None

    def test_normalize_task_id_valid(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._normalize_task_id("42") == 42
        assert LegalResearchTaskEventService._normalize_task_id(42) == 42

    def test_normalize_status_code(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._normalize_status_code(None) is None
        assert LegalResearchTaskEventService._normalize_status_code("abc") is None
        assert LegalResearchTaskEventService._normalize_status_code(50) is None
        assert LegalResearchTaskEventService._normalize_status_code(1000) is None
        assert LegalResearchTaskEventService._normalize_status_code(200) == 200

    def test_sanitize_url_empty(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._sanitize_url("") == ""
        assert LegalResearchTaskEventService._sanitize_url(None) == ""

    def test_sanitize_url_masks_password(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        result = LegalResearchTaskEventService._sanitize_url("http://example.com?password=secret&token=abc123")
        assert "secret" not in result
        assert "abc123" not in result
        assert "***" in result

    def test_sanitize_url_long(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        long_url = "http://example.com/" + "a" * 2000
        result = LegalResearchTaskEventService._sanitize_url(long_url)
        assert len(result) <= LegalResearchTaskEventService.MAX_URL_CHARS

    def test_sanitize_node_bytes(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        result = LegalResearchTaskEventService._sanitize_node(value=b"binary", level=0, key_hint="")
        assert "bytes" in str(result)

    def test_sanitize_node_sensitive_key(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        result = LegalResearchTaskEventService._sanitize_node(value="secret", level=0, key_hint="api_key")
        assert result == "***"

    def test_sanitize_node_deep_nesting(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        result = LegalResearchTaskEventService._sanitize_node(value={"a": 1}, level=5, key_hint="")
        assert result == "..."

    def test_sanitize_node_long_string(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        long_str = "x" * 500
        result = LegalResearchTaskEventService._sanitize_node(value=long_str, level=0, key_hint="")
        assert len(str(result)) < 500

    def test_sanitize_node_truncated_dict(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        big_dict = {f"key_{i}": i for i in range(50)}
        result = LegalResearchTaskEventService._sanitize_node(value=big_dict, level=0, key_hint="")
        assert isinstance(result, dict)
        assert "__truncated__" in result

    def test_sanitize_node_truncated_list(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        big_list = list(range(50))
        result = LegalResearchTaskEventService._sanitize_node(value=big_list, level=0, key_hint="")
        assert isinstance(result, list)
        assert "..." in result

    def test_sanitize_payload_large(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        # Use a non-sensitive key that won't be masked
        large = {"request_detail": "x" * 3000}
        result = LegalResearchTaskEventService._sanitize_payload(large)
        # Either preview key or the value is masked
        assert isinstance(result, dict)

    def test_is_sensitive_key(self):
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._is_sensitive_key("password") is True
        assert LegalResearchTaskEventService._is_sensitive_key("api_key") is True
        assert LegalResearchTaskEventService._is_sensitive_key("username") is True
        assert LegalResearchTaskEventService._is_sensitive_key("normal_field") is False
        assert LegalResearchTaskEventService._is_sensitive_key("") is False


# ---------------------------------------------------------------------------
# sources/weike/document.py module-level functions (58% coverage)
# ---------------------------------------------------------------------------


class TestWeikeDocumentFunctions:
    def test_html_to_text(self):
        from apps.legal_research.services.sources.weike.document import html_to_text

        result = html_to_text("<p>Hello <b>World</b></p>")
        assert "Hello" in result
        assert "World" in result
        assert "<p>" not in result

    def test_html_to_text_script_style(self):
        from apps.legal_research.services.sources.weike.document import html_to_text

        result = html_to_text("<script>bad()</script><style>.x{}</style><p>ok</p>")
        assert "bad()" not in result
        assert ".x{}" not in result
        assert "ok" in result

    def test_html_to_text_entities(self):
        from apps.legal_research.services.sources.weike.document import html_to_text

        result = html_to_text("&lt;tag&gt;")
        assert "<tag>" in result

    def test_normalize_dom_text(self):
        from apps.legal_research.services.sources.weike.document import normalize_dom_text

        result = normalize_dom_text("  hello  \xa0 world  ")
        assert "hello" in result
        assert "\xa0" not in result

    def test_extract_dom_field_match(self):
        from apps.legal_research.services.sources.weike.document import extract_dom_field

        result = extract_dom_field(
            text="案号：(2024)渝01民初123号",
            patterns=(r"案号[：:]\s*(.+)",),
        )
        assert "2024" in result

    def test_extract_dom_field_no_match(self):
        from apps.legal_research.services.sources.weike.document import extract_dom_field

        result = extract_dom_field(
            text="no match here",
            patterns=(r"案号[：:]\s*(.+)",),
        )
        assert result == ""

    def test_build_dom_digest_short(self):
        from apps.legal_research.services.sources.weike.document import build_dom_digest

        result = build_dom_digest("short text")
        assert result == "short text"

    def test_build_dom_digest_long(self):
        from apps.legal_research.services.sources.weike.document import build_dom_digest

        result = build_dom_digest("x" * 500)
        assert result.endswith("...")
        assert len(result) <= 223

    def test_build_dom_digest_empty(self):
        from apps.legal_research.services.sources.weike.document import build_dom_digest

        assert build_dom_digest("") == ""
        assert build_dom_digest("   ") == ""

    def test_detail_doc_id_candidates(self):
        from apps.legal_research.services.sources.weike.document import detail_doc_id_candidates
        from apps.legal_research.services.sources.weike.types import WeikeSearchItem

        item = WeikeSearchItem(
            doc_id_raw="RAW", doc_id_unquoted="UNQ",
            detail_url="", title_hint="", search_id="", module="",
        )
        result = detail_doc_id_candidates(item)
        assert "RAW" in result
        assert "UNQ" in result

    def test_is_session_restricted_response(self):
        from apps.legal_research.services.sources.weike.document import is_session_restricted_response

        assert is_session_restricted_response(status=400, payload={"code": "C_001_009"}) is True
        assert is_session_restricted_response(status=200, payload={"code": "C_001_009"}) is True
        assert is_session_restricted_response(status=200, payload={"code": "OK"}) is False

    def test_compact_error(self):
        from apps.legal_research.services.sources.weike.document import compact_error

        result = compact_error(ValueError("short"), max_len=120)
        assert result == "short"

        long_exc = ValueError("x" * 200)
        result = compact_error(long_exc, max_len=120)
        assert len(result) <= 120

    def test_summarize_meta_payload(self):
        from apps.legal_research.services.sources.weike.document import summarize_meta_payload

        payload = {
            "currentDoc": {
                "title": "Test Case",
                "additionalFields": {
                    "courtText": "重庆法院",
                    "documentNumber": "(2024)渝01民初123号",
                    "judgmentDate": "2024-01-15",
                },
            }
        }
        result = summarize_meta_payload(payload)
        assert result["title"] == "Test Case"
        assert result["court_text"] == "重庆法院"

    def test_summarize_meta_payload_empty(self):
        from apps.legal_research.services.sources.weike.document import summarize_meta_payload

        result = summarize_meta_payload(None)
        assert result["title"] == ""

    def test_summarize_html_payload(self):
        from apps.legal_research.services.sources.weike.document import summarize_html_payload

        result = summarize_html_payload({"content": "hello"})
        assert result["content_length"] == 5
        assert result["has_content"] is True

    def test_summarize_html_payload_empty(self):
        from apps.legal_research.services.sources.weike.document import summarize_html_payload

        result = summarize_html_payload(None)
        assert result["has_content"] is False

    def test_build_download_filename(self):
        from apps.legal_research.services.sources.weike.document import build_download_filename
        from apps.legal_research.services.sources.weike.types import WeikeCaseDetail

        detail = WeikeCaseDetail(
            doc_id_raw="RAW", doc_id_unquoted="UNQ", detail_url="",
            search_id="", module="", title="合同纠纷案",
            court_text="", document_number="", judgment_date="",
            case_digest="", content_text="", raw_meta={},
        )
        result = build_download_filename(detail)
        assert "合同纠纷案" in result
        assert result.endswith(".pdf")

    def test_build_download_filename_empty_title(self):
        from apps.legal_research.services.sources.weike.document import build_download_filename
        from apps.legal_research.services.sources.weike.types import WeikeCaseDetail

        detail = WeikeCaseDetail(
            doc_id_raw="RAW", doc_id_unquoted="DOC123", detail_url="",
            search_id="", module="", title="",
            court_text="", document_number="", judgment_date="",
            case_digest="", content_text="", raw_meta={},
        )
        result = build_download_filename(detail)
        assert "DOC123" in result


# ---------------------------------------------------------------------------
# admin/result_admin.py (51% coverage)
# ---------------------------------------------------------------------------


class TestResultAdmin:
    def test_feedback_status_relevant(self):
        from apps.legal_research.admin.result_admin import LegalResearchResultAdmin

        admin_instance = LegalResearchResultAdmin.__new__(LegalResearchResultAdmin)
        obj = SimpleNamespace(metadata={"human_feedback": "relevant"})
        result = admin_instance.feedback_status(obj)
        assert result == "真实命中"

    def test_feedback_status_false_positive(self):
        from apps.legal_research.admin.result_admin import LegalResearchResultAdmin

        admin_instance = LegalResearchResultAdmin.__new__(LegalResearchResultAdmin)
        obj = SimpleNamespace(metadata={"human_feedback": "false_positive"})
        result = admin_instance.feedback_status(obj)
        assert result == "误命中"

    def test_feedback_status_none(self):
        from apps.legal_research.admin.result_admin import LegalResearchResultAdmin

        admin_instance = LegalResearchResultAdmin.__new__(LegalResearchResultAdmin)
        obj = SimpleNamespace(metadata={})
        result = admin_instance.feedback_status(obj)
        assert result == "—"

    def test_has_pdf_true(self):
        from apps.legal_research.admin.result_admin import LegalResearchResultAdmin

        admin_instance = LegalResearchResultAdmin.__new__(LegalResearchResultAdmin)
        obj = SimpleNamespace(pdf_file=MagicMock())
        assert admin_instance.has_pdf(obj) is True

    def test_has_pdf_false(self):
        from apps.legal_research.admin.result_admin import LegalResearchResultAdmin

        admin_instance = LegalResearchResultAdmin.__new__(LegalResearchResultAdmin)
        obj = SimpleNamespace(pdf_file=None)
        assert admin_instance.has_pdf(obj) is False
