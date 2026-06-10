"""Tests for apps.automation.services.document_delivery.query_service - additional edge cases."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.automation.services.document_delivery.data_classes import DocumentQueryResult, DocumentRecord
from apps.automation.services.document_delivery.query_service import DocumentQueryService


class TestQueryViaApi:
    def test_empty_result(self) -> None:
        mock_api = MagicMock()
        mock_api.fetch_document_list.return_value = SimpleNamespace(total=0)

        svc = DocumentQueryService(api_client=mock_api)
        result = svc.query_via_api(token="tok", cutoff_time=datetime(2025, 1, 1), credential_id=1)
        assert result.total_found == 0
        assert result.processed_count == 0

    def test_api_failure_raises(self) -> None:
        mock_api = MagicMock()
        mock_api.fetch_document_list.side_effect = RuntimeError("timeout")

        svc = DocumentQueryService(api_client=mock_api)
        with pytest.raises(RuntimeError, match="timeout"):
            svc.query_via_api(token="tok", cutoff_time=datetime(2025, 1, 1), credential_id=1)

    def test_with_results(self) -> None:
        mock_api = MagicMock()
        mock_api.fetch_document_list.return_value = SimpleNamespace(total=5)

        svc = DocumentQueryService(api_client=mock_api)
        result = svc.query_via_api(token="tok", cutoff_time=datetime(2025, 1, 1), credential_id=1)
        assert result.total_found == 5


class TestTryApiAfterLogin:
    def test_success(self) -> None:
        mock_api = MagicMock()
        mock_api.fetch_document_list.return_value = SimpleNamespace(total=2)

        svc = DocumentQueryService(api_client=mock_api)
        result = svc.try_api_after_login(token="tok", cutoff_time=datetime(2025, 1, 1), credential_id=1)
        assert result is not None
        assert result.total_found == 2

    def test_failure_returns_none(self) -> None:
        mock_api = MagicMock()
        mock_api.fetch_document_list.side_effect = RuntimeError("fail")

        svc = DocumentQueryService(api_client=mock_api)
        result = svc.try_api_after_login(token="tok", cutoff_time=datetime(2025, 1, 1), credential_id=1)
        assert result is None


class TestCheckApiDocumentNotProcessed:
    def test_valid_send_time_delegates_to_repo(self) -> None:
        mock_repo = MagicMock()
        mock_repo.should_process.return_value = True

        svc = DocumentQueryService(history_repo=mock_repo)
        record = DocumentRecord(
            ah="（2025）粤01民初1号", sdbh="S1", ajzybh="A1",
            fssj="2025-06-10 10:00:00", fymc="广州法院",
        )
        result = svc.check_api_document_not_processed(1, record)
        assert result is True
        mock_repo.should_process.assert_called_once()

    def test_unparseable_returns_true(self) -> None:
        svc = DocumentQueryService()
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="", fymc="")
        assert svc.check_api_document_not_processed(1, record) is True


class TestShouldProcessWithRepo:
    def test_delegates_when_time_after_cutoff(self) -> None:
        mock_repo = MagicMock()
        mock_repo.should_process.return_value = False

        svc = DocumentQueryService(history_repo=mock_repo)
        record = DocumentRecord(
            ah="（2025）粤01民初1号", sdbh="S1", ajzybh="A1",
            fssj="2025-12-31 23:59:59", fymc="广州法院",
        )
        from django.utils import timezone
        cutoff = timezone.make_aware(datetime(2025, 1, 1))
        result = svc.should_process_api_document(record, cutoff, 1)
        assert result is False
        mock_repo.should_process.assert_called_once()
