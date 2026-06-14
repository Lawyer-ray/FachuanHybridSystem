"""Tests for automation.services.document_delivery.api.document_delivery_api_service._query.

Covers: query_documents, _process_document_page, should_process_document.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from django.utils import timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_query_mixin():
    """Create a concrete instance of DocumentQueryMixin for testing."""
    from apps.automation.services.document_delivery.api.document_delivery_api_service._query import (
        DocumentQueryMixin,
    )

    mock_client = MagicMock()

    class Concrete(DocumentQueryMixin):
        @property
        def api_client(self):
            return mock_client

        def process_document(self, record, token, credential_id):
            return SimpleNamespace(success=True, case_log_id=1, error_message=None)

    instance = Concrete()
    instance._mock_client = mock_client
    return instance


def _make_record(ah="AH001", fssj="2099-01-01 00:00:00"):
    record = MagicMock()
    record.ah = ah
    record.fssj = fssj
    record.parse_fssj.return_value = datetime(2099, 1, 1)
    return record


# ---------------------------------------------------------------------------
# query_documents
# ---------------------------------------------------------------------------


class TestQueryDocuments:
    def test_zero_total(self):
        mixin = _make_query_mixin()
        mixin._mock_client.fetch_document_list.return_value = SimpleNamespace(total=0, documents=[])
        result = mixin.query_documents("tok", datetime.now(), 1)
        assert result.total_found == 0

    def test_single_page(self):
        mixin = _make_query_mixin()
        mixin._mock_client.fetch_document_list.return_value = SimpleNamespace(
            total=1, documents=[_make_record()]
        )
        with patch.object(mixin, "should_process_document", return_value=True):
            with patch.object(mixin, "process_document", return_value=SimpleNamespace(success=True, case_log_id=1, error_message=None)):
                result = mixin.query_documents("tok", datetime.now(), 1)
        assert result.total_found == 1
        assert result.processed_count >= 0

    def test_multi_page_with_page_error(self):
        mixin = _make_query_mixin()
        call_count = 0

        def side_effect(token, page_num, page_size):
            nonlocal call_count
            call_count += 1
            if page_num == 1:
                return SimpleNamespace(total=40, documents=[_make_record() for _ in range(20)])
            raise RuntimeError("page 2 fail")

        mixin._mock_client.fetch_document_list.side_effect = side_effect
        with patch.object(mixin, "should_process_document", return_value=True):
            with patch.object(mixin, "process_document", return_value=SimpleNamespace(success=True, case_log_id=None, error_message=None)):
                result = mixin.query_documents("tok", datetime.now(), 1)
        assert len(result.errors) >= 1
        assert "第 2 页失败" in result.errors[0]

    def test_api_error_raises(self):
        mixin = _make_query_mixin()
        mixin._mock_client.fetch_document_list.side_effect = RuntimeError("API down")
        with pytest.raises(RuntimeError):
            mixin.query_documents("tok", datetime.now(), 1)


# ---------------------------------------------------------------------------
# _process_document_page
# ---------------------------------------------------------------------------


class TestProcessDocumentPage:
    def test_skipped_document(self):
        mixin = _make_query_mixin()
        from apps.automation.services.document_delivery.data_classes import DocumentQueryResult

        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        with patch.object(mixin, "should_process_document", return_value=False):
            mixin._process_document_page([_make_record()], "tok", datetime.now(), 1, result)
        assert result.skipped_count == 1

    def test_successful_process(self):
        mixin = _make_query_mixin()
        from apps.automation.services.document_delivery.data_classes import DocumentQueryResult

        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        with patch.object(mixin, "should_process_document", return_value=True):
            with patch.object(mixin, "process_document", return_value=SimpleNamespace(success=True, case_log_id=42, error_message=None)):
                mixin._process_document_page([_make_record()], "tok", datetime.now(), 1, result)
        assert result.processed_count == 1
        assert 42 in result.case_log_ids

    def test_failed_process(self):
        mixin = _make_query_mixin()
        from apps.automation.services.document_delivery.data_classes import DocumentQueryResult

        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        with patch.object(mixin, "should_process_document", return_value=True):
            with patch.object(mixin, "process_document", return_value=SimpleNamespace(success=False, case_log_id=None, error_message="err msg")):
                mixin._process_document_page([_make_record()], "tok", datetime.now(), 1, result)
        assert result.failed_count == 1
        assert "err msg" in result.errors

    def test_exception_in_process(self):
        mixin = _make_query_mixin()
        from apps.automation.services.document_delivery.data_classes import DocumentQueryResult

        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        with patch.object(mixin, "should_process_document", return_value=True):
            with patch.object(mixin, "process_document", side_effect=RuntimeError("boom")):
                mixin._process_document_page([_make_record()], "tok", datetime.now(), 1, result)
        assert result.failed_count == 1


# ---------------------------------------------------------------------------
# should_process_document
# ---------------------------------------------------------------------------


class TestShouldProcessDocument:
    def test_unparseable_returns_true(self):
        mixin = _make_query_mixin()
        record = _make_record()
        record.parse_fssj.return_value = None
        assert mixin.should_process_document(record, datetime.now(), 1) is True

    def test_before_cutoff_returns_false(self):
        mixin = _make_query_mixin()
        record = _make_record()
        record.parse_fssj.return_value = datetime(2020, 1, 1)
        assert mixin.should_process_document(record, timezone.now(), 1) is False

    def test_after_cutoff_checks_processed(self):
        mixin = _make_query_mixin()
        record = _make_record()
        record.parse_fssj.return_value = datetime(2099, 1, 1)
        with patch.object(mixin, "_check_document_not_processed", return_value=True):
            assert mixin.should_process_document(record, datetime(2025, 1, 1), 1) is True


# ---------------------------------------------------------------------------
# process_document raises NotImplementedError
# ---------------------------------------------------------------------------


class TestProcessDocumentNotImplemented:
    def test_raises(self):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._query import (
            DocumentQueryMixin,
        )

        class Bare(DocumentQueryMixin):
            @property
            def api_client(self):
                return MagicMock()

        bare = Bare()
        with pytest.raises(NotImplementedError):
            bare.process_document(MagicMock(), "tok", 1)
