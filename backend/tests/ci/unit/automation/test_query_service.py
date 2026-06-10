"""Tests for apps.automation.services.document_delivery.query_service."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.document_delivery.data_classes import DocumentQueryResult, DocumentRecord
from apps.automation.services.document_delivery.query_service import DocumentQueryService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(**kwargs: object) -> DocumentRecord:
    defaults = {
        "ah": "（2025）粤0604民初123号",
        "sdbh": "SD001",
        "ajzybh": "AJ001",
        "fssj": "2025-06-10 10:00:00",
        "fymc": "佛山市顺德区人民法院",
    }
    defaults.update(kwargs)
    return DocumentRecord(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Property tests (lazy-loaded dependencies)
# ---------------------------------------------------------------------------


class TestDocumentQueryServiceProperties:
    def test_api_client_raises_when_not_injected(self) -> None:
        svc = DocumentQueryService()
        with pytest.raises(RuntimeError, match="api_client 未注入"):
            _ = svc.api_client

    def test_token_service_raises_when_not_injected(self) -> None:
        svc = DocumentQueryService()
        with pytest.raises(RuntimeError, match="token_service 未注入"):
            _ = svc.token_service

    def test_case_number_service_raises_when_not_injected(self) -> None:
        svc = DocumentQueryService()
        with pytest.raises(RuntimeError, match="case_number_service 未注入"):
            _ = svc.case_number_service

    def test_history_repo_raises_when_not_injected(self) -> None:
        svc = DocumentQueryService()
        with pytest.raises(RuntimeError, match="history_repo 未注入"):
            _ = svc.history_repo

    def test_injected_dependencies_are_returned(self) -> None:
        mock_api = MagicMock()
        mock_token = MagicMock()
        svc = DocumentQueryService(api_client=mock_api, token_service=mock_token)
        assert svc.api_client is mock_api
        assert svc.token_service is mock_token


# ---------------------------------------------------------------------------
# acquire_token / refresh_token_if_expired delegation
# ---------------------------------------------------------------------------


class TestTokenDelegation:
    def test_acquire_token_delegates(self) -> None:
        mock_token_svc = MagicMock()
        mock_token_svc.acquire_token.return_value = "tok123"
        svc = DocumentQueryService(token_service=mock_token_svc)
        assert svc.acquire_token(42) == "tok123"
        mock_token_svc.acquire_token.assert_called_once_with(42)

    def test_refresh_token_delegates(self) -> None:
        mock_token_svc = MagicMock()
        mock_token_svc.refresh_token_if_expired.return_value = "new_tok"
        svc = DocumentQueryService(token_service=mock_token_svc)
        assert svc.refresh_token_if_expired(1, "old") == "new_tok"
        mock_token_svc.refresh_token_if_expired.assert_called_once_with(1, "old")


# ---------------------------------------------------------------------------
# try_api_approach
# ---------------------------------------------------------------------------


class TestTryApiApproach:
    def test_returns_none_when_token_unavailable(self) -> None:
        mock_token_svc = MagicMock()
        mock_token_svc.acquire_token.return_value = None
        svc = DocumentQueryService(token_service=mock_token_svc)
        result = svc.try_api_approach(1, datetime(2025, 1, 1))
        assert result is None

    def test_returns_result_on_success(self) -> None:
        mock_token_svc = MagicMock()
        mock_token_svc.acquire_token.return_value = "tok"
        mock_api = MagicMock()
        expected = DocumentQueryResult(total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[])
        mock_api.fetch_document_list.return_value = SimpleNamespace(total=0)
        svc = DocumentQueryService(api_client=mock_api, token_service=mock_token_svc)
        result = svc.try_api_approach(1, datetime(2025, 1, 1))
        assert result is not None
        assert result.total_found == 0

    def test_returns_none_on_exception(self) -> None:
        mock_token_svc = MagicMock()
        mock_token_svc.acquire_token.return_value = "tok"
        mock_api = MagicMock()
        mock_api.fetch_document_list.side_effect = RuntimeError("network error")
        svc = DocumentQueryService(api_client=mock_api, token_service=mock_token_svc)
        result = svc.try_api_approach(1, datetime(2025, 1, 1))
        assert result is None


# ---------------------------------------------------------------------------
# should_process_api_document
# ---------------------------------------------------------------------------


class TestShouldProcessApiDocument:
    def test_returns_true_when_parse_fails(self) -> None:
        record = _make_record(fssj="")
        svc = DocumentQueryService()
        assert svc.should_process_api_document(record, datetime(2025, 6, 1), 1) is True

    def test_returns_false_when_send_time_before_cutoff(self) -> None:
        record = _make_record(fssj="2025-01-01 00:00:00")
        svc = DocumentQueryService()
        # cutoff is an aware datetime; send_time will be made aware too
        from django.utils import timezone
        cutoff = timezone.make_aware(datetime(2025, 6, 1))
        assert svc.should_process_api_document(record, cutoff, 1) is False


# ---------------------------------------------------------------------------
# check_api_document_not_processed
# ---------------------------------------------------------------------------


class TestCheckApiDocumentNotProcessed:
    def test_returns_true_when_parse_fails(self) -> None:
        record = _make_record(fssj="")
        svc = DocumentQueryService()
        assert svc.check_api_document_not_processed(1, record) is True


# ---------------------------------------------------------------------------
# DocumentRecord.parse_fssj
# ---------------------------------------------------------------------------


class TestDocumentRecordParseFssj:
    def test_standard_format(self) -> None:
        rec = _make_record(fssj="2025-06-10 10:30:00")
        dt = rec.parse_fssj()
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 6
        assert dt.minute == 30

    def test_empty_fssj(self) -> None:
        rec = _make_record(fssj="")
        assert rec.parse_fssj() is None

    def test_unparseable_fssj(self) -> None:
        rec = _make_record(fssj="not-a-date")
        assert rec.parse_fssj() is None
