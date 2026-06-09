"""Tests for executor_components: cache_mixin, result_persistence, policy_mixin, source_gateway, task_lifecycle."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── cache_mixin ────────────────────────────────────────────────────────────


class TestCacheMixin:
    def _make_item(self, doc_id: str = "doc1") -> SimpleNamespace:
        return SimpleNamespace(doc_id_unquoted=doc_id, doc_id_raw=f"raw_{doc_id}")

    def _make_detail(self, doc_id: str = "doc1") -> SimpleNamespace:
        return SimpleNamespace(
            doc_id_raw=f"raw_{doc_id}",
            doc_id_unquoted=doc_id,
            detail_url="https://example.com/doc1",
            search_id="s1",
            module="module1",
            title="Test Title",
            court_text="Test Court",
            document_number="(2024)test123",
            judgment_date="2024-01-01",
            case_digest="Test digest",
            content_text="Full content",
            raw_meta={"key": "value"},
        )

    def test_reserve_new_items_no_dups(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        items = [self._make_item("a"), self._make_item("b")]
        seen: set[str] = set()
        unique, dups = ExecutorCacheMixin._reserve_new_items(items=items, seen_doc_ids=seen)
        assert len(unique) == 2
        assert dups == 0

    def test_reserve_new_items_with_dups(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        items = [self._make_item("a"), self._make_item("a"), self._make_item("b")]
        seen: set[str] = set()
        unique, dups = ExecutorCacheMixin._reserve_new_items(items=items, seen_doc_ids=seen)
        assert len(unique) == 2
        assert dups == 1

    def test_reserve_new_items_already_seen(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        items = [self._make_item("a")]
        seen = {"a"}
        unique, dups = ExecutorCacheMixin._reserve_new_items(items=items, seen_doc_ids=seen)
        assert len(unique) == 0
        assert dups == 1

    def test_build_case_detail_cache_key(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        key = ExecutorCacheMixin._build_case_detail_cache_key(source="weike", doc_id="doc123")
        assert key == "legal_research:detail:weike:doc123"

    def test_build_case_detail_cache_key_empty(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        assert ExecutorCacheMixin._build_case_detail_cache_key(source="", doc_id="doc123") == ""
        assert ExecutorCacheMixin._build_case_detail_cache_key(source="weike", doc_id="") == ""

    def test_extract_item_doc_id(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        item = self._make_item("test_doc")
        assert ExecutorCacheMixin._extract_item_doc_id(item) == "test_doc"

    def test_extract_item_doc_id_fallback_to_raw(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        item = SimpleNamespace(doc_id_unquoted="", doc_id_raw="raw_id")
        assert ExecutorCacheMixin._extract_item_doc_id(item) == "raw_id"

    def test_serialize_case_detail(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        detail = self._make_detail()
        payload = ExecutorCacheMixin._serialize_case_detail(detail)
        assert payload["title"] == "Test Title"
        assert payload["doc_id_unquoted"] == "doc1"
        assert payload["raw_meta"] == {"key": "value"}

    def test_serialize_case_detail_no_raw_meta(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        detail = SimpleNamespace(
            doc_id_raw="r", doc_id_unquoted="u", detail_url="", search_id="",
            module="", title="", court_text="", document_number="",
            judgment_date="", case_digest="", content_text="",
        )
        payload = ExecutorCacheMixin._serialize_case_detail(detail)
        assert "raw_meta" not in payload

    def test_deserialize_case_detail_payload(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        payload = {"doc_id_raw": "r1", "doc_id_unquoted": "u1", "title": "Test", "raw_meta": {"k": "v"}}
        detail = ExecutorCacheMixin._deserialize_case_detail_payload(payload)
        assert detail is not None
        assert detail.title == "Test"
        assert detail.doc_id_unquoted == "u1"

    def test_deserialize_no_doc_id(self) -> None:
        from apps.legal_research.services.executor_components.cache_mixin import ExecutorCacheMixin

        assert ExecutorCacheMixin._deserialize_case_detail_payload({"title": "x"}) is None


# ── result_persistence ─────────────────────────────────────────────────────


class TestResultPersistence:
    def test_build_content_excerpt_empty(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        assert ExecutorResultPersistenceMixin._build_content_excerpt("") == ""
        assert ExecutorResultPersistenceMixin._build_content_excerpt(None) == ""  # type: ignore[arg-type]

    def test_build_content_excerpt_normalizes(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        text = "line1\r\nline2\rline3\n\n\n\nline4"
        result = ExecutorResultPersistenceMixin._build_content_excerpt(text)
        assert "\r" not in result
        assert "\n\n\n" not in result

    def test_build_content_excerpt_truncates(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        text = "x" * 20000
        result = ExecutorResultPersistenceMixin._build_content_excerpt(text)
        assert len(result) == ExecutorResultPersistenceMixin.CONTENT_EXCERPT_MAX_CHARS

    def test_sanitize_pdf_filename_basic(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        assert ExecutorResultPersistenceMixin._sanitize_pdf_filename("test.pdf", fallback="fb") == "test.pdf"

    def test_sanitize_pdf_filename_adds_extension(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        result = ExecutorResultPersistenceMixin._sanitize_pdf_filename("test", fallback="fb")
        assert result.endswith(".pdf")

    def test_sanitize_pdf_filename_strips_path(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        result = ExecutorResultPersistenceMixin._sanitize_pdf_filename("/path/to/file.pdf", fallback="fb")
        assert result == "file.pdf"

    def test_sanitize_pdf_filename_sanitizes_special_chars(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        result = ExecutorResultPersistenceMixin._sanitize_pdf_filename("file name@#.pdf", fallback="fb")
        assert "@" not in result
        assert "#" not in result
        assert result.endswith(".pdf")

    def test_sanitize_pdf_filename_empty_uses_fallback(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        result = ExecutorResultPersistenceMixin._sanitize_pdf_filename("", fallback="fallback_id")
        assert "fallback" in result.lower()

    def test_extract_similarity_metadata_dict(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        sim = MagicMock()
        sim.metadata = {"keyword_score": 0.8, "vector_score": 0.7}
        result = ExecutorResultPersistenceMixin._extract_similarity_metadata(similarity=sim)
        assert "similarity_structured" in result
        assert result["similarity_structured"]["keyword_score"] == 0.8

    def test_extract_similarity_metadata_empty(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        sim = MagicMock()
        sim.metadata = {}
        result = ExecutorResultPersistenceMixin._extract_similarity_metadata(similarity=sim)
        assert result == {}

    def test_extract_similarity_metadata_none(self) -> None:
        from apps.legal_research.services.executor_components.result_persistence import (
            ExecutorResultPersistenceMixin,
        )

        sim = MagicMock()
        sim.metadata = None
        result = ExecutorResultPersistenceMixin._extract_similarity_metadata(similarity=sim)
        assert result == {}


# ── policy_mixin ───────────────────────────────────────────────────────────


class TestPolicyMixin:
    def test_resolve_effective_min_similarity_no_tuning(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import ExecutorPolicyMixin
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        tuning = LegalResearchTuningConfig(online_tuning_enabled=False)
        result = ExecutorPolicyMixin._resolve_effective_min_similarity(
            requested_min_similarity=0.7, tuning=tuning
        )
        assert result == 0.7

    def test_resolve_effective_min_similarity_with_delta(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import ExecutorPolicyMixin
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        tuning = LegalResearchTuningConfig(online_tuning_enabled=True, online_min_similarity_delta=0.05)
        result = ExecutorPolicyMixin._resolve_effective_min_similarity(
            requested_min_similarity=0.7, tuning=tuning
        )
        assert result == pytest.approx(0.75)

    def test_resolve_effective_min_similarity_clamped(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import ExecutorPolicyMixin
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        tuning = LegalResearchTuningConfig(online_tuning_enabled=True, online_min_similarity_delta=1.0)
        result = ExecutorPolicyMixin._resolve_effective_min_similarity(
            requested_min_similarity=0.9, tuning=tuning
        )
        assert result == pytest.approx(0.99)

    def test_build_dual_review_policy_defaults(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import ExecutorPolicyMixin
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        tuning = LegalResearchTuningConfig()
        policy = ExecutorPolicyMixin._build_dual_review_policy(tuning=tuning)
        # Default has dual_review_model="Qwen/Qwen2.5-14B-Instruct" so enabled=True
        assert policy.enabled is True
        assert policy.review_model == "Qwen/Qwen2.5-14B-Instruct"

    def test_build_dual_review_policy_with_model(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import ExecutorPolicyMixin
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        tuning = LegalResearchTuningConfig(dual_review_enabled=True, dual_review_model="gpt-4")
        policy = ExecutorPolicyMixin._build_dual_review_policy(tuning=tuning)
        assert policy.enabled is True
        assert policy.review_model == "gpt-4"

    def test_build_adaptive_threshold_policy_disabled(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import ExecutorPolicyMixin
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        tuning = LegalResearchTuningConfig(adaptive_threshold_enabled=False)
        policy = ExecutorPolicyMixin._build_adaptive_threshold_policy(
            baseline_min_similarity=0.7, tuning=tuning
        )
        assert policy.enabled is False

    def test_build_adaptive_threshold_policy_enabled(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import ExecutorPolicyMixin
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        tuning = LegalResearchTuningConfig(adaptive_threshold_enabled=True, adaptive_threshold_floor=0.5)
        policy = ExecutorPolicyMixin._build_adaptive_threshold_policy(
            baseline_min_similarity=0.7, tuning=tuning
        )
        assert policy.enabled is True
        assert policy.floor < 0.7

    def test_maybe_decay_disabled(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import (
            AdaptiveThresholdPolicy,
            ExecutorPolicyMixin,
        )

        policy = AdaptiveThresholdPolicy(enabled=False, floor=0.5, step=0.01, scan_interval=100)
        result = ExecutorPolicyMixin._maybe_decay_min_similarity_threshold(
            current_threshold=0.7,
            scanned=100,
            matched=10,
            checkpoint_scanned=0,
            checkpoint_matched=0,
            policy=policy,
        )
        assert result[3] is False  # changed flag

    def test_maybe_decay_below_floor(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import (
            AdaptiveThresholdPolicy,
            ExecutorPolicyMixin,
        )

        policy = AdaptiveThresholdPolicy(enabled=True, floor=0.6, step=0.01, scan_interval=10)
        result = ExecutorPolicyMixin._maybe_decay_min_similarity_threshold(
            current_threshold=0.6,  # at floor
            scanned=100,
            matched=10,
            checkpoint_scanned=0,
            checkpoint_matched=0,
            policy=policy,
        )
        assert result[3] is False

    def test_maybe_decay_new_matches(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import (
            AdaptiveThresholdPolicy,
            ExecutorPolicyMixin,
        )

        policy = AdaptiveThresholdPolicy(enabled=True, floor=0.5, step=0.01, scan_interval=10)
        result = ExecutorPolicyMixin._maybe_decay_min_similarity_threshold(
            current_threshold=0.7,
            scanned=100,
            matched=10,
            checkpoint_scanned=0,
            checkpoint_matched=5,  # new matches found
            policy=policy,
        )
        assert result[3] is False

    def test_maybe_decay_not_enough_scans(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import (
            AdaptiveThresholdPolicy,
            ExecutorPolicyMixin,
        )

        policy = AdaptiveThresholdPolicy(enabled=True, floor=0.5, step=0.01, scan_interval=100)
        result = ExecutorPolicyMixin._maybe_decay_min_similarity_threshold(
            current_threshold=0.7,
            scanned=50,
            matched=5,
            checkpoint_scanned=0,
            checkpoint_matched=5,
            policy=policy,
        )
        assert result[3] is False

    def test_maybe_decay_lowers_threshold(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import (
            AdaptiveThresholdPolicy,
            ExecutorPolicyMixin,
        )

        policy = AdaptiveThresholdPolicy(enabled=True, floor=0.5, step=0.05, scan_interval=10)
        result = ExecutorPolicyMixin._maybe_decay_min_similarity_threshold(
            current_threshold=0.7,
            scanned=100,
            matched=5,
            checkpoint_scanned=0,
            checkpoint_matched=5,  # no new matches
            policy=policy,
        )
        assert result[3] is True  # changed
        assert result[0] < 0.7  # lowered

    def test_build_adaptive_threshold_suffix_no_change(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import ExecutorPolicyMixin

        assert ExecutorPolicyMixin._build_adaptive_threshold_suffix(baseline=0.7, lowered_to=0.7) == ""

    def test_build_adaptive_threshold_suffix_with_change(self) -> None:
        from apps.legal_research.services.executor_components.policy_mixin import ExecutorPolicyMixin

        result = ExecutorPolicyMixin._build_adaptive_threshold_suffix(baseline=0.7, lowered_to=0.65)
        assert "0.70" in result
        assert "0.65" in result


# ── task_lifecycle ─────────────────────────────────────────────────────────


class TestTaskLifecycle:
    def test_update_progress_calculation(self) -> None:
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        task = MagicMock()
        task.max_candidates = 100
        task.target_count = 10
        task.candidate_count = 5

        with patch.object(ExecutorTaskLifecycleMixin, "_save_task_safely"):
            ExecutorTaskLifecycleMixin._update_progress(task=task, scanned=50, matched=3)
        assert task.scanned_count == 50
        assert task.matched_count == 3
        assert task.progress <= 95

    def test_update_progress_with_skipped(self) -> None:
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        task = MagicMock()
        task.max_candidates = 100
        task.target_count = 10
        task.candidate_count = 5

        with patch.object(ExecutorTaskLifecycleMixin, "_save_task_safely"):
            ExecutorTaskLifecycleMixin._update_progress(task=task, scanned=50, matched=3, skipped=10)
        assert "跳过 10" in task.message

    def test_mark_completed(self) -> None:
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        task = MagicMock()
        with patch.object(ExecutorTaskLifecycleMixin, "_save_task_safely"):
            ExecutorTaskLifecycleMixin._mark_completed(task, message="完成")
        assert task.status == "completed"
        assert task.progress == 100

    def test_mark_failed(self) -> None:
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        task = MagicMock()
        with patch.object(ExecutorTaskLifecycleMixin, "_save_task_safely"):
            ExecutorTaskLifecycleMixin._mark_failed(task, "错误信息")
        assert task.status == "failed"
        assert task.error == "错误信息"

    def test_mark_cancelled(self) -> None:
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        task = MagicMock()
        task.max_candidates = 100
        task.target_count = 10
        with patch.object(ExecutorTaskLifecycleMixin, "_save_task_safely"):
            ExecutorTaskLifecycleMixin._mark_cancelled(task=task, scanned=50, matched=3, skipped=5)
        assert task.status == "cancelled"
        assert "跳过 5" in task.message

    def test_is_cancel_requested(self) -> None:
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin

        with patch.object(
            ExecutorTaskLifecycleMixin, "_run_orm_safely", return_value=LegalResearchTaskStatus.CANCELLED
        ):
            assert ExecutorTaskLifecycleMixin._is_cancel_requested("1") is True

        with patch.object(
            ExecutorTaskLifecycleMixin, "_run_orm_safely", return_value=LegalResearchTaskStatus.RUNNING
        ):
            assert ExecutorTaskLifecycleMixin._is_cancel_requested("1") is False


# ── source_gateway ─────────────────────────────────────────────────────────


class TestSourceGateway:
    """Tests require a concrete subclass since source_gateway uses class-level annotations."""

    def _make_concrete(self):
        from apps.legal_research.services.executor_components.source_gateway import ExecutorSourceGatewayMixin

        class Concrete(ExecutorSourceGatewayMixin):
            SEARCH_RETRY_ATTEMPTS = 3
            DETAIL_RETRY_ATTEMPTS = 3
            DOWNLOAD_RETRY_ATTEMPTS = 3
            RETRY_BACKOFF_SECONDS = 0.01
            RETRY_BACKOFF_MAX_SECONDS = 0.05
            PAGE_SIZE_HINT = 20
            MAX_PAGE_WINDOW = 2000

        return Concrete

    def test_estimate_max_pages(self) -> None:
        Concrete = self._make_concrete()
        result = Concrete._estimate_max_pages(offset=0, batch_size=10)
        assert result >= 10

    def test_estimate_max_pages_large(self) -> None:
        Concrete = self._make_concrete()
        result = Concrete._estimate_max_pages(offset=5000, batch_size=100)
        assert result <= Concrete.MAX_PAGE_WINDOW

    def test_sleep_for_retry_zero_backoff(self) -> None:
        from apps.legal_research.services.executor_components.source_gateway import ExecutorSourceGatewayMixin

        class ZeroBackoffMixin(ExecutorSourceGatewayMixin):
            RETRY_BACKOFF_SECONDS = 0
            PAGE_SIZE_HINT = 20
            MAX_PAGE_WINDOW = 2000

        # Should not sleep
        ZeroBackoffMixin._sleep_for_retry(attempt=1)

    @patch("apps.legal_research.services.executor_components.source_gateway.time.sleep")
    def test_sleep_for_retry_positive_backoff(self, mock_sleep) -> None:
        Concrete = self._make_concrete()
        Concrete._sleep_for_retry(attempt=1)
        mock_sleep.assert_called_once()

    def test_fetch_case_detail_with_retry_success(self) -> None:
        Concrete = self._make_concrete()
        client = MagicMock()
        client.fetch_case_detail.return_value = MagicMock()
        item = MagicMock()
        item.doc_id_unquoted = "doc1"
        item.doc_id_raw = "raw1"

        with patch.object(Concrete, "_sleep_for_retry"):
            result = Concrete._fetch_case_detail_with_retry(
                source_client=client, session=MagicMock(), item=item, task_id="1"
            )
        assert result is not None

    def test_fetch_case_detail_with_retry_all_fail(self) -> None:
        Concrete = self._make_concrete()
        client = MagicMock()
        client.fetch_case_detail.side_effect = RuntimeError("fail")
        item = MagicMock()
        item.doc_id_unquoted = "doc1"
        item.doc_id_raw = "raw1"

        with patch.object(Concrete, "_sleep_for_retry"):
            result = Concrete._fetch_case_detail_with_retry(
                source_client=client, session=MagicMock(), item=item, task_id="1"
            )
        assert result is None

    def test_download_pdf_with_retry_success(self) -> None:
        Concrete = self._make_concrete()
        client = MagicMock()
        client.download_pdf.return_value = (b"pdf_data", "test.pdf")
        detail = MagicMock()
        detail.doc_id_unquoted = "doc1"
        detail.doc_id_raw = "raw1"

        with patch.object(Concrete, "_sleep_for_retry"):
            result = Concrete._download_pdf_with_retry(
                source_client=client, session=MagicMock(), detail=detail, task_id="1"
            )
        assert result == (b"pdf_data", "test.pdf")

    def test_download_pdf_raises_on_c001_009(self) -> None:
        Concrete = self._make_concrete()
        client = MagicMock()
        client.download_pdf.side_effect = RuntimeError("C_001_009 error")
        detail = MagicMock()
        detail.doc_id_unquoted = "doc1"
        detail.doc_id_raw = "raw1"

        with patch.object(Concrete, "_sleep_for_retry"):
            with pytest.raises(RuntimeError, match="C_001_009"):
                Concrete._download_pdf_with_retry(
                    source_client=client, session=MagicMock(), detail=detail, task_id="1"
                )

    def test_fetch_candidate_batch_with_retry_success(self) -> None:
        Concrete = self._make_concrete()
        client = MagicMock()
        client.search_cases.return_value = ["item1", "item2"]

        with patch.object(Concrete, "_sleep_for_retry"):
            result = Concrete._fetch_candidate_batch_with_retry(
                source_client=client,
                session=MagicMock(),
                keyword="test",
                offset=0,
                batch_size=10,
                task_id="1",
            )
        assert len(result) == 2
