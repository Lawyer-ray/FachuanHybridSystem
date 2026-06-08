"""
Unit tests for DocumentDeliveryService.

Covers:
  - __init__, lazy properties (case_matcher, document_renamer, etc.)
  - _query_via_api (total==0, single page, multi-page, page error)
  - _process_document_page (skip, success, failure, exception)
  - _process_document_via_api (no details, download failure, success, exception)
  - _should_process_api_document (no parse, before cutoff, after cutoff)
  - _try_api_approach (token success, token fail, exception)
  - _acquire_token / _acquire_token_via_service / _refresh_token_if_expired
  - _try_api_after_login (success, exception)
  - _should_process (send_time None, before cutoff, after cutoff)
  - _process_single_entry (skip, success, failure)
  - _process_playwright_page (no entries, single page, multi-page)
  - _process_document_entry (download fail, success)
  - _sync_login_with_page (success first try, success retry, all fail)
  - query_and_download (API success, API fail -> Playwright)
  - _check_api_document_not_processed (timeout, found, not found)
"""

from __future__ import annotations

import math
import queue
import threading
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentDetail,
    DocumentListResponse,
    DocumentProcessResult,
    DocumentQueryResult,
    DocumentRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(**kwargs: Any) -> Any:
    """Create DocumentDeliveryService with all deps mocked."""
    from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

    defaults = {
        "case_matcher": MagicMock(),
        "document_renamer": MagicMock(),
        "notification_service": MagicMock(),
        "auto_login_service": MagicMock(),
        "api_client": MagicMock(),
        "token_service": MagicMock(),
    }
    defaults.update(kwargs)
    return DocumentDeliveryService(**defaults)


def _make_record(
    ah: str = "(2025)粤0604民初1号",
    sdbh: str = "SD001",
    fssj: str = "2025-12-10 16:25:37",
    fymc: str = "测试法院",
    wsmc: str = "民事判决书",
    **extra: Any,
) -> DocumentRecord:
    return DocumentRecord(
        ah=ah, sdbh=sdbh, ajzybh="AJ001", fssj=fssj, fymc=fymc, wsmc=wsmc, **extra
    )


def _make_delivery_record(
    case_number: str = "(2025)粤0604民初1号",
    send_time: datetime | None = datetime(2025, 12, 10, 16, 25, 37),
    element_index: int = 0,
) -> DocumentDeliveryRecord:
    return DocumentDeliveryRecord(
        case_number=case_number,
        send_time=send_time,
        element_index=element_index,
    )


def _make_query_result(**kwargs: Any) -> DocumentQueryResult:
    defaults = {
        "total_found": 0, "processed_count": 0, "skipped_count": 0, "failed_count": 0,
        "case_log_ids": [], "errors": [],
    }
    defaults.update(kwargs)
    return DocumentQueryResult(**defaults)


# ===========================================================================
# Tests
# ===========================================================================


class TestInit:
    """Test __init__ sets attributes correctly."""

    def test_init_stores_all_deps(self) -> None:
        svc = _make_service()
        assert svc._case_matcher is not None
        assert svc._api_client is not None
        assert svc._token_service is not None

    def test_init_with_none_deps(self) -> None:
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

        svc = DocumentDeliveryService()
        assert svc._case_matcher is None
        assert svc._auto_login_service is None


class TestProperties:
    """Test lazy property access."""

    @patch("apps.automation.services.sms.case_matcher.CaseMatcher", autospec=True)
    def test_case_matcher_lazy(self, mock_cls: MagicMock) -> None:
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

        svc = DocumentDeliveryService()
        assert svc._case_matcher is None
        result = svc.case_matcher
        mock_cls.assert_called_once()
        assert result is mock_cls.return_value

    def test_case_matcher_injected(self) -> None:
        svc = _make_service()
        assert svc.case_matcher is svc._case_matcher

    @patch("apps.automation.services.sms.document_renamer.DocumentRenamer", autospec=True)
    def test_document_renamer_lazy(self, mock_cls: MagicMock) -> None:
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

        svc = DocumentDeliveryService()
        _ = svc.document_renamer
        mock_cls.assert_called_once()

    def test_document_renamer_injected(self) -> None:
        svc = _make_service()
        assert svc.document_renamer is svc._document_renamer

    @patch("apps.automation.services.sms.sms_notification_service.SMSNotificationService", autospec=True)
    def test_notification_service_lazy(self, mock_cls: MagicMock) -> None:
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

        svc = DocumentDeliveryService()
        _ = svc.notification_service
        mock_cls.assert_called_once()

    def test_notification_service_injected(self) -> None:
        svc = _make_service()
        assert svc.notification_service is svc._notification_service

    @patch("apps.automation.services.document_delivery.document_delivery_service.ServiceLocator")
    def test_auto_login_service_lazy(self, mock_locator: MagicMock) -> None:
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

        svc = DocumentDeliveryService()
        result = svc.auto_login_service
        mock_locator.get_auto_login_service.assert_called_once()
        assert result is mock_locator.get_auto_login_service.return_value

    def test_auto_login_service_injected(self) -> None:
        svc = _make_service()
        assert svc.auto_login_service is svc._auto_login_service

    @patch("apps.automation.services.document_delivery.court_document_api_client.CourtDocumentApiClient", autospec=True)
    def test_api_client_lazy(self, mock_cls: MagicMock) -> None:
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

        svc = DocumentDeliveryService()
        result = svc.api_client
        mock_cls.assert_called_once()
        assert result is mock_cls.return_value

    def test_api_client_injected(self) -> None:
        svc = _make_service()
        assert svc.api_client is svc._api_client

    @patch(
        "apps.automation.services.document_delivery.token.document_delivery_token_service.DocumentDeliveryTokenService",
        autospec=True,
    )
    def test_token_service_lazy(self, mock_cls: MagicMock) -> None:
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

        svc = DocumentDeliveryService()
        _ = svc.token_service
        mock_cls.assert_called_once()

    def test_token_service_injected(self) -> None:
        svc = _make_service()
        assert svc.token_service is svc._token_service


class TestAcquireToken:
    """Test _acquire_token and _acquire_token_via_service."""

    def test_acquire_token_returns_str(self) -> None:
        svc = _make_service()
        svc._token_service.acquire_token.return_value = "tok123"
        assert svc._acquire_token(1) == "tok123"

    def test_acquire_token_none(self) -> None:
        svc = _make_service()
        svc._token_service.acquire_token.return_value = None
        assert svc._acquire_token(1) is None

    def test_acquire_token_via_service(self) -> None:
        svc = _make_service()
        svc._token_service.acquire_token.return_value = "tok456"
        assert svc._acquire_token_via_service("site", 1) == "tok456"

    def test_acquire_token_via_service_none(self) -> None:
        svc = _make_service()
        svc._token_service.acquire_token.return_value = None
        assert svc._acquire_token_via_service("site", 1) is None

    def test_refresh_token_if_expired(self) -> None:
        svc = _make_service()
        svc._token_service.refresh_token_if_expired.return_value = "newtok"
        assert svc._refresh_token_if_expired(1, "oldtok") == "newtok"

    def test_refresh_token_if_expired_none(self) -> None:
        svc = _make_service()
        svc._token_service.refresh_token_if_expired.return_value = None
        assert svc._refresh_token_if_expired(1, "oldtok") is None


class TestQueryViaApi:
    """Test _query_via_api method."""

    def test_zero_total(self) -> None:
        svc = _make_service()
        resp = MagicMock()
        resp.total = 0
        svc._api_client.fetch_document_list.return_value = resp

        result = svc._query_via_api("tok", datetime(2025, 1, 1), 1)
        assert result.total_found == 0
        assert result.processed_count == 0

    def test_single_page_success(self) -> None:
        svc = _make_service()
        rec = _make_record()
        resp = MagicMock()
        resp.total = 1
        resp.documents = [rec]
        svc._api_client.fetch_document_list.return_value = resp

        with patch.object(svc, "_should_process_api_document", return_value=True), \
             patch.object(svc, "_process_document_via_api") as mock_process:
            mock_process.return_value = DocumentProcessResult(
                success=True, case_id=1, case_log_id=10, renamed_path="/x", notification_sent=True, error_message=None,
            )
            result = svc._query_via_api("tok", datetime(2025, 1, 1), 1)

        assert result.total_found == 1
        assert result.processed_count == 1
        assert result.case_log_ids == [10]

    def test_single_page_skip(self) -> None:
        svc = _make_service()
        rec = _make_record()
        resp = MagicMock()
        resp.total = 1
        resp.documents = [rec]
        svc._api_client.fetch_document_list.return_value = resp

        with patch.object(svc, "_should_process_api_document", return_value=False):
            result = svc._query_via_api("tok", datetime(2025, 1, 1), 1)

        assert result.skipped_count == 1

    def test_multi_page(self) -> None:
        svc = _make_service()
        rec = _make_record()
        # total=45, page_size=20 -> 3 pages
        resp1 = MagicMock()
        resp1.total = 45
        resp1.documents = [rec]
        resp2 = MagicMock()
        resp2.documents = [rec]
        resp3 = MagicMock()
        resp3.documents = [rec]

        svc._api_client.fetch_document_list.side_effect = [resp1, resp2, resp3]

        with patch.object(svc, "_should_process_api_document", return_value=True), \
             patch.object(svc, "_process_document_via_api") as mock_process:
            mock_process.return_value = DocumentProcessResult(
                success=True, case_id=1, case_log_id=10, renamed_path=None,
                notification_sent=False, error_message=None,
            )
            result = svc._query_via_api("tok", datetime(2025, 1, 1), 1)

        assert result.total_found == 45
        assert result.processed_count == 3

    def test_page_error_continues(self) -> None:
        svc = _make_service()
        rec = _make_record()
        resp1 = MagicMock()
        resp1.total = 40
        resp1.documents = [rec]

        svc._api_client.fetch_document_list.side_effect = [
            resp1,
            Exception("network"),
            MagicMock(documents=[rec]),
        ]

        with patch.object(svc, "_should_process_api_document", return_value=True), \
             patch.object(svc, "_process_document_via_api") as mock_process:
            mock_process.return_value = DocumentProcessResult(
                success=True, case_id=None, case_log_id=None, renamed_path=None,
                notification_sent=False, error_message=None,
            )
            result = svc._query_via_api("tok", datetime(2025, 1, 1), 1)

        assert any("处理第 2 页失败" in e for e in result.errors)

    def test_first_page_exception_propagates(self) -> None:
        svc = _make_service()
        svc._api_client.fetch_document_list.side_effect = Exception("fatal")

        with pytest.raises(Exception, match="fatal"):
            svc._query_via_api("tok", datetime(2025, 1, 1), 1)


class TestProcessDocumentPage:
    """Test _process_document_page."""

    def test_skip_then_success(self) -> None:
        svc = _make_service()
        rec1 = _make_record(ah="A1")
        rec2 = _make_record(ah="A2")
        result = _make_query_result()

        call_count = 0

        def side_effect(record, cutoff, cid):
            nonlocal call_count
            call_count += 1
            return call_count == 1  # skip first, process second

        with patch.object(svc, "_should_process_api_document", side_effect=side_effect), \
             patch.object(svc, "_process_document_via_api") as mock_process:
            mock_process.return_value = DocumentProcessResult(
                success=True, case_id=1, case_log_id=5, renamed_path=None,
                notification_sent=False, error_message=None,
            )
            svc._process_document_page([rec1, rec2], "tok", datetime(2025, 1, 1), 1, result)

        assert result.skipped_count == 1
        assert result.processed_count == 1

    def test_failure_increments_failed(self) -> None:
        svc = _make_service()
        rec = _make_record()
        result = _make_query_result()

        with patch.object(svc, "_should_process_api_document", return_value=True), \
             patch.object(svc, "_process_document_via_api") as mock_process:
            mock_process.return_value = DocumentProcessResult(
                success=False, case_id=None, case_log_id=None, renamed_path=None,
                notification_sent=False, error_message="download failed",
            )
            svc._process_document_page([rec], "tok", datetime(2025, 1, 1), 1, result)

        assert result.failed_count == 1
        assert "download failed" in result.errors

    def test_exception_increments_failed(self) -> None:
        svc = _make_service()
        rec = _make_record()
        result = _make_query_result()

        with patch.object(svc, "_should_process_api_document", return_value=True), \
             patch.object(svc, "_process_document_via_api", side_effect=RuntimeError("boom")):
            svc._process_document_page([rec], "tok", datetime(2025, 1, 1), 1, result)

        assert result.failed_count == 1
        assert any("处理文书" in e and "boom" in e for e in result.errors)


class TestShouldProcessApiDocument:
    """Test _should_process_api_document."""

    def test_unparseable_time_returns_true(self) -> None:
        svc = _make_service()
        rec = _make_record(fssj="not-a-date")
        cutoff = datetime(2025, 1, 1)

        # When fssj is unparseable, parse_fssj() returns None -> treat as unprocessed
        with patch.object(svc, "_check_api_document_not_processed", return_value=True):
            result = svc._should_process_api_document(rec, cutoff, 1)
        assert result is True

    def test_before_cutoff(self) -> None:
        svc = _make_service()
        rec = _make_record(fssj="2024-01-01 00:00:00")
        cutoff = datetime(2025, 1, 1)

        with patch("django.utils.timezone.is_aware", return_value=True), \
             patch("django.utils.timezone.make_aware", side_effect=lambda dt: dt):
            result = svc._should_process_api_document(rec, cutoff, 1)
        assert result is False

    def test_after_cutoff_delegates(self) -> None:
        svc = _make_service()
        rec = _make_record(fssj="2026-01-01 00:00:00")
        cutoff = datetime(2025, 1, 1)

        with patch("django.utils.timezone.is_aware", return_value=True), \
             patch("django.utils.timezone.make_aware", side_effect=lambda dt: dt), \
             patch.object(svc, "_check_api_document_not_processed", return_value=True):
            result = svc._should_process_api_document(rec, cutoff, 1)
        assert result is True


class TestProcessDocumentViaApi:
    """Test _process_document_via_api."""

    def test_no_details_returns_error(self) -> None:
        svc = _make_service()
        svc._api_client.fetch_document_details.return_value = []
        rec = _make_record()

        result = svc._process_document_via_api(rec, "tok", 1)
        assert result.success is False
        assert "未获取到文书详情" in (result.error_message or "")

    def test_all_downloads_fail(self) -> None:
        svc = _make_service()
        detail = MagicMock(wjlj="http://x", c_wsmc="doc", c_wjgs="pdf")
        svc._api_client.fetch_document_details.return_value = [detail]
        svc._api_client.download_document.return_value = False
        rec = _make_record()

        result = svc._process_document_via_api(rec, "tok", 1)
        assert result.success is False
        assert result.error_message == "所有文书下载失败"

    def test_success_flow(self) -> None:
        svc = _make_service()
        detail = MagicMock(wjlj="http://x", c_wsmc="doc", c_wjgs="pdf")
        svc._api_client.fetch_document_details.return_value = [detail]
        svc._api_client.download_document.return_value = True

        rec = _make_record(fssj="2025-12-10 16:25:37")

        sms_result = {"success": True, "case_id": 1, "case_log_id": 10, "renamed_path": "/p", "notification_sent": True, "error_message": None}

        with patch("tempfile.mkdtemp", return_value="/tmp/testdir"), \
             patch("shutil.rmtree"), \
             patch("django.utils.timezone.make_aware", side_effect=lambda dt: dt), \
             patch.object(svc, "_process_sms_in_thread", return_value=sms_result), \
             patch.object(svc, "_record_query_history_in_thread"):
            result = svc._process_document_via_api(rec, "tok", 1)

        assert result.success is True
        assert result.case_id == 1
        assert result.notification_sent is True

    def test_exception_returns_error(self) -> None:
        svc = _make_service()
        svc._api_client.fetch_document_details.side_effect = Exception("api error")
        rec = _make_record()

        result = svc._process_document_via_api(rec, "tok", 1)
        assert result.success is False
        assert "api error" in (result.error_message or "")

    def test_no_send_time_uses_now(self) -> None:
        svc = _make_service()
        detail = MagicMock(wjlj="http://x", c_wsmc="doc", c_wjgs="pdf")
        svc._api_client.fetch_document_details.return_value = [detail]
        svc._api_client.download_document.return_value = True
        rec = _make_record(fssj="bad-time-format")

        sms_result = {"success": True, "case_id": 1, "case_log_id": None, "renamed_path": None, "notification_sent": False, "error_message": None}

        with patch("tempfile.mkdtemp", return_value="/tmp/testdir"), \
             patch("shutil.rmtree"), \
             patch("django.utils.timezone.now", return_value=datetime(2025, 6, 1)), \
             patch.object(svc, "_process_sms_in_thread", return_value=sms_result), \
             patch.object(svc, "_record_query_history_in_thread"):
            result = svc._process_document_via_api(rec, "tok", 1)

        assert result.success is True


class TestTryApiApproach:
    """Test _try_api_approach."""

    def test_token_success(self) -> None:
        svc = _make_service()
        expected = _make_query_result(total_found=5)

        with patch.object(svc, "_acquire_token", return_value="tok"), \
             patch.object(svc, "_query_via_api", return_value=expected):
            result = svc._try_api_approach(1, datetime(2025, 1, 1))

        assert result is expected

    def test_token_fail_returns_none(self) -> None:
        svc = _make_service()
        with patch.object(svc, "_acquire_token", return_value=None):
            result = svc._try_api_approach(1, datetime(2025, 1, 1))
        assert result is None

    def test_api_exception_returns_none(self) -> None:
        svc = _make_service()
        with patch.object(svc, "_acquire_token", return_value="tok"), \
             patch.object(svc, "_query_via_api", side_effect=Exception("fail")):
            result = svc._try_api_approach(1, datetime(2025, 1, 1))
        assert result is None


class TestTryApiAfterLogin:
    """Test _try_api_after_login."""

    def test_success(self) -> None:
        svc = _make_service()
        expected = _make_query_result(total_found=3)
        with patch.object(svc, "_query_via_api", return_value=expected):
            result = svc._try_api_after_login("tok", datetime(2025, 1, 1), 1)
        assert result is expected

    def test_exception_returns_none(self) -> None:
        svc = _make_service()
        with patch.object(svc, "_query_via_api", side_effect=Exception("err")):
            result = svc._try_api_after_login("tok", datetime(2025, 1, 1), 1)
        assert result is None


class TestShouldProcess:
    """Test _should_process (Playwright context)."""

    def test_send_time_none(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record(send_time=None)
        assert svc._should_process(entry, datetime(2025, 1, 1), 1) is False

    def test_send_time_before_cutoff(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record(send_time=datetime(2024, 1, 1))
        assert svc._should_process(entry, datetime(2025, 1, 1), 1) is False

    def test_send_time_after_cutoff(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record(send_time=datetime(2026, 1, 1))
        with patch.object(svc, "_check_not_processed_in_thread", return_value=True):
            assert svc._should_process(entry, datetime(2025, 1, 1), 1) is True

    def test_send_time_equal_cutoff(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record(send_time=datetime(2025, 1, 1))
        assert svc._should_process(entry, datetime(2025, 1, 1), 1) is False


class TestProcessSingleEntry:
    """Test _process_single_entry."""

    def test_skip(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record(send_time=None)
        result = _make_query_result()
        with patch.object(svc, "_should_process", return_value=False):
            should_continue = svc._process_single_entry(MagicMock(), entry, datetime(2025, 1, 1), 1, result)
        assert should_continue is False
        assert result.skipped_count == 1

    def test_success(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record(send_time=datetime(2026, 1, 1))
        result = _make_query_result()

        proc = DocumentProcessResult(
            success=True, case_id=1, case_log_id=5, renamed_path=None,
            notification_sent=False, error_message=None,
        )
        with patch.object(svc, "_should_process", return_value=True), \
             patch.object(svc, "_process_document_entry", return_value=proc):
            should_continue = svc._process_single_entry(MagicMock(), entry, datetime(2025, 1, 1), 1, result)
        assert result.processed_count == 1
        assert result.case_log_ids == [5]

    def test_failure(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record(send_time=datetime(2026, 1, 1))
        result = _make_query_result()

        proc = DocumentProcessResult(
            success=False, case_id=None, case_log_id=None, renamed_path=None,
            notification_sent=False, error_message="err",
        )
        with patch.object(svc, "_should_process", return_value=True), \
             patch.object(svc, "_process_document_entry", return_value=proc):
            svc._process_single_entry(MagicMock(), entry, datetime(2025, 1, 1), 1, result)
        assert result.failed_count == 1
        assert "err" in result.errors


class TestProcessPlaywrightPage:
    """Test _process_playwright_page."""

    def test_no_entries(self) -> None:
        svc = _make_service()
        result = _make_query_result()
        with patch.object(svc, "_extract_document_entries", return_value=[]):
            svc._process_playwright_page(MagicMock(), datetime(2025, 1, 1), 1, result)
        assert result.total_found == 0

    def test_single_page_entries_all_skipped(self) -> None:
        svc = _make_service()
        result = _make_query_result()
        entry = _make_delivery_record(send_time=datetime(2024, 1, 1))

        with patch.object(svc, "_extract_document_entries", return_value=[entry]), \
             patch.object(svc, "_should_process", return_value=False), \
             patch.object(svc, "_has_next_page", return_value=False):
            svc._process_playwright_page(MagicMock(), datetime(2025, 1, 1), 1, result)

        assert result.skipped_count == 1

    def test_multi_page(self) -> None:
        svc = _make_service()
        result = _make_query_result()
        entry1 = _make_delivery_record(send_time=datetime(2026, 1, 1), case_number="A1")
        entry2 = _make_delivery_record(send_time=datetime(2024, 1, 1), case_number="A2")

        page = MagicMock()
        call_count = 0

        def extract_side_effect(p):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [entry1]
            return [entry2]

        proc = DocumentProcessResult(
            success=True, case_id=1, case_log_id=5, renamed_path=None,
            notification_sent=False, error_message=None,
        )

        with patch.object(svc, "_extract_document_entries", side_effect=extract_side_effect), \
             patch.object(svc, "_should_process", side_effect=[True, False]), \
             patch.object(svc, "_process_single_entry", return_value=True), \
             patch.object(svc, "_has_next_page", side_effect=[True, False]):
            svc._process_playwright_page(page, datetime(2025, 1, 1), 1, result)

        assert result.total_found == 2


class TestProcessDocumentEntry:
    """Test _process_document_entry (Playwright context)."""

    def test_download_fail(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record()
        with patch.object(svc, "_download_document", return_value=None):
            result = svc._process_document_entry(MagicMock(), entry, 1)
        assert result.success is False
        assert result.error_message == "文书下载失败"

    def test_success(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record()
        proc_result = MagicMock()
        proc_result.success = True
        proc_result.case_id = 1
        proc_result.case_log_id = 5
        proc_result.renamed_path = "/x"
        proc_result.notification_sent = True
        proc_result.error_message = None

        with patch.object(svc, "_download_document", return_value="/tmp/doc.pdf"), \
             patch.object(svc, "_process_downloaded_document", return_value=proc_result), \
             patch.object(svc, "_record_query_history_in_thread"):
            result = svc._process_document_entry(MagicMock(), entry, 1)
        assert result.success is True
        assert result.case_log_id == 5

    def test_exception(self) -> None:
        svc = _make_service()
        entry = _make_delivery_record()
        with patch.object(svc, "_download_document", side_effect=RuntimeError("oops")):
            result = svc._process_document_entry(MagicMock(), entry, 1)
        assert result.success is False
        assert "oops" in (result.error_message or "")


class TestSyncLoginWithPage:
    """Test _sync_login_with_page."""

    def test_success_first_try(self) -> None:
        svc = _make_service()
        credential = MagicMock()
        credential.site_name = "test"
        page = MagicMock()

        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService"
        ) as mock_court:
            mock_court.return_value.login.return_value = {"success": True, "token": "tok123"}
            token = svc._sync_login_with_page(MagicMock(), credential, page)
        assert token == "tok123"

    def test_success_after_retry(self) -> None:
        svc = _make_service()
        credential = MagicMock()
        credential.site_name = "test"
        page = MagicMock()

        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService"
        ) as mock_court, \
             patch("time.sleep"):
            mock_court.return_value.login.side_effect = [
                {"success": False, "message": "fail1"},
                {"success": True, "token": "tok_retry"},
            ]
            token = svc._sync_login_with_page(MagicMock(), credential, page)
        assert token == "tok_retry"

    def test_login_success_no_token_raises(self) -> None:
        svc = _make_service()
        credential = MagicMock()
        credential.site_name = "test"
        page = MagicMock()

        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService"
        ) as mock_court:
            mock_court.return_value.login.return_value = {"success": True, "token": None}
            with pytest.raises(Exception, match="登录成功但未获取到token"):
                svc._sync_login_with_page(MagicMock(), credential, page)

    def test_all_retries_fail(self) -> None:
        svc = _make_service()
        credential = MagicMock()
        credential.site_name = "test"
        page = MagicMock()

        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService"
        ) as mock_court, \
             patch("time.sleep"):
            mock_court.return_value.login.return_value = {"success": False, "message": "fail"}
            with pytest.raises(Exception, match="登录失败"):
                svc._sync_login_with_page(MagicMock(), credential, page)


class TestQueryAndDownload:
    """Test query_and_download orchestration."""

    def test_api_success(self) -> None:
        svc = _make_service()
        expected = _make_query_result(total_found=3)

        with patch.object(svc, "_try_api_approach", return_value=expected):
            result = svc.query_and_download(1, datetime(2025, 1, 1))
        assert result is expected

    def test_api_fail_fallback_to_playwright(self) -> None:
        svc = _make_service()
        expected = _make_query_result(total_found=5)

        with patch.object(svc, "_try_api_approach", return_value=None), \
             patch.object(svc, "_query_via_playwright", return_value=expected):
            result = svc.query_and_download(1, datetime(2025, 1, 1))
        assert result is expected


class TestCheckApiDocumentNotProcessed:
    """Test _check_api_document_not_processed."""

    def test_found_existing_sms(self) -> None:
        svc = _make_service()
        rec = _make_record(fssj="2025-12-10 16:25:37")

        mock_sms = MagicMock()
        mock_sms.id = 42

        with patch("queue.Queue") as mock_queue_cls, \
             patch("threading.Thread") as mock_thread_cls, \
             patch(
                 "apps.automation.services.sms.court_sms_dedup_service.CourtSMSDedupService"
             ) as mock_dedup, \
             patch("django.db.connection"):
            mock_dedup.return_value.find_document_delivery_sms.return_value = mock_sms

            # Simulate the do_check putting False into the queue
            fake_queue = MagicMock()
            fake_queue.empty.return_value = False
            fake_queue.get.return_value = False
            mock_queue_cls.return_value = fake_queue

            result = svc._check_api_document_not_processed(1, rec)

        assert result is False

    def test_not_found_allows_processing(self) -> None:
        svc = _make_service()
        rec = _make_record(fssj="2025-12-10 16:25:37")

        with patch("queue.Queue") as mock_queue_cls, \
             patch("threading.Thread") as mock_thread_cls, \
             patch(
                 "apps.automation.services.sms.court_sms_dedup_service.CourtSMSDedupService"
             ) as mock_dedup, \
             patch("django.db.connection"), \
             patch(
                 "apps.automation.models.DocumentQueryHistory"
             ) as mock_history:
            mock_dedup.return_value.find_document_delivery_sms.return_value = None
            mock_history.objects.filter.return_value.first.return_value = None

            fake_queue = MagicMock()
            fake_queue.empty.return_value = False
            fake_queue.get.return_value = True
            mock_queue_cls.return_value = fake_queue

            result = svc._check_api_document_not_processed(1, rec)

        assert result is True

    def test_timeout_returns_true(self) -> None:
        svc = _make_service()
        rec = _make_record(fssj="2025-12-10 16:25:37")

        with patch("queue.Queue") as mock_queue_cls, \
             patch("threading.Thread") as mock_thread_cls:
            fake_queue = MagicMock()
            fake_queue.empty.return_value = True  # empty means timeout
            mock_queue_cls.return_value = fake_queue

            result = svc._check_api_document_not_processed(1, rec)
        assert result is True


class TestQueryViaPlaywright:
    """Test _query_via_playwright end-to-end paths."""

    def test_credential_not_found(self) -> None:
        svc = _make_service()
        mock_org_svc = MagicMock()
        mock_org_svc.get_credential.return_value = None

        with patch(
            "apps.automation.services.document_delivery.document_delivery_service.ServiceLocator"
        ) as mock_locator:
            mock_locator.get_organization_service.return_value = mock_org_svc
            result = svc._query_via_playwright(1, datetime(2025, 1, 1))

        assert result.errors
        assert "账号凭证不存在" in result.errors[0]

    def test_login_failure(self) -> None:
        svc = _make_service()
        credential = MagicMock()
        mock_org_svc = MagicMock()
        mock_org_svc.get_credential.return_value = credential

        mock_browser_svc = MagicMock()
        mock_page = MagicMock()
        mock_browser_svc.get_browser.return_value.new_page.return_value = mock_page

        with patch(
            "apps.automation.services.document_delivery.document_delivery_service.ServiceLocator"
        ) as mock_locator, \
             patch(
                 "apps.core.services.browser.get_browser_service",
                 return_value=mock_browser_svc,
             ), \
             patch.object(svc, "_sync_login_with_page", side_effect=Exception("login fail")):
            mock_locator.get_organization_service.return_value = mock_org_svc
            result = svc._query_via_playwright(1, datetime(2025, 1, 1))

        assert any("登录失败" in e for e in result.errors)

    def test_api_after_login_success(self) -> None:
        svc = _make_service()
        credential = MagicMock()
        expected = _make_query_result(total_found=2)
        mock_org_svc = MagicMock()
        mock_org_svc.get_credential.return_value = credential

        mock_browser_svc = MagicMock()
        mock_page = MagicMock()
        mock_browser_svc.get_browser.return_value.new_page.return_value = mock_page

        with patch(
            "apps.automation.services.document_delivery.document_delivery_service.ServiceLocator"
        ) as mock_locator, \
             patch(
                 "apps.core.services.browser.get_browser_service",
                 return_value=mock_browser_svc,
             ), \
             patch.object(svc, "_sync_login_with_page", return_value="tok"), \
             patch.object(svc, "_try_api_after_login", return_value=expected):
            mock_locator.get_organization_service.return_value = mock_org_svc
            result = svc._query_via_playwright(1, datetime(2025, 1, 1))

        assert result is expected

    def test_exception_in_playwright(self) -> None:
        svc = _make_service()

        with patch(
            "apps.automation.services.document_delivery.document_delivery_service.ServiceLocator"
        ) as mock_locator:
            mock_locator.get_organization_service.side_effect = Exception("svc fail")
            result = svc._query_via_playwright(1, datetime(2025, 1, 1))

        assert any("svc fail" in e for e in result.errors)


class TestConstants:
    """Verify class constants exist."""

    def test_delivery_page_url(self) -> None:
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

        assert "zxfw.court.gov.cn" in DocumentDeliveryService.DELIVERY_PAGE_URL

    def test_selectors_not_empty(self) -> None:
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

        assert DocumentDeliveryService.PENDING_TAB_SELECTOR
        assert DocumentDeliveryService.REVIEWED_TAB_SELECTOR
        assert DocumentDeliveryService.CASE_NUMBER_SELECTOR
        assert DocumentDeliveryService.DOWNLOAD_BUTTON_SELECTOR
        assert DocumentDeliveryService.NEXT_PAGE_SELECTOR
