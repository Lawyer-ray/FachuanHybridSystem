"""Tests for CourtInboxFetcher and helper functions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import httpx
import pytest

from apps.message_hub.models import SyncStatus
from apps.message_hub.services.court.court_fetcher import (
    CourtInboxFetcher,
    _api_post,
    _build_body,
    _build_subject,
    _fetch_attachments_meta,
    _mark_failed,
    _mark_success,
    _parse_datetime,
    _run_callable_with_timeout,
)

# Lazy-import patch targets (imported inside methods at runtime)
_LAZY_DR = "apps.automation.services.document_delivery.data_classes.DocumentDeliveryRecord"
_LAZY_DP = "apps.automation.services.document_delivery.processor.document_delivery_processor.DocumentDeliveryProcessor"
_LAZY_CM = "apps.automation.services.token.cache_manager.cache_manager"
_LAZY_SL = "apps.core.interfaces.ServiceLocator"
_LAZY_CT = "apps.automation.models.token.CourtToken"


# ===========================================================================
# Helper function tests
# ===========================================================================


class TestBuildSubject:
    def test_with_ah_and_wsmc(self) -> None:
        assert _build_subject({"ah": "（2024）京01民初1号", "wsmc": "民事判决书"}) == "（2024）京01民初1号 - 民事判决书"

    def test_without_ah(self) -> None:
        assert _build_subject({"ah": "", "wsmc": "裁定书"}) == "裁定书"

    def test_empty(self) -> None:
        assert _build_subject({}) == "(无主题)"


class TestBuildBody:
    def test_full_record(self) -> None:
        record = {
            "ah": "（2024）京01民初1号",
            "fymc": "北京市第一中级人民法院",
            "wsmc": "民事判决书",
            "fqr": "张三",
            "sdzt": "已送达",
            "qdzt": "已签到",
            "fssj": "2024-06-01 10:00:00",
        }
        body = _build_body(record)
        assert "（2024）京01民初1号" in body
        assert "北京市第一中级人民法院" in body
        assert "已送达" in body
        assert "已签到" in body

    def test_empty_record(self) -> None:
        body = _build_body({})
        assert "案号：" in body


class TestParseDatetime:
    def test_valid_format(self) -> None:
        dt = _parse_datetime("2024-06-01 10:30:00")
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.hour == 10

    def test_invalid_format_returns_now(self) -> None:
        dt = _parse_datetime("not-a-date")
        assert dt is not None  # should return timezone.now()

    def test_empty_string(self) -> None:
        dt = _parse_datetime("")
        assert dt is not None


class TestFetchAttachmentsMeta:
    @patch("apps.message_hub.services.court.court_fetcher._api_post")
    def test_returns_meta(self, mock_post: MagicMock) -> None:
        mock_post.return_value = {
            "data": [
                {
                    "wjlj": "https://example.com/file.pdf",
                    "c_wjgs": "pdf",
                    "c_wsmc": "判决书",
                    "c_sdbh": "s1",
                    "c_wsbh": "w1",
                }
            ]
        }
        meta = _fetch_attachments_meta("token", "sdbh-1")
        assert len(meta) == 1
        assert meta[0]["filename"] == "判决书.pdf"
        assert meta[0]["wjlj"] == "https://example.com/file.pdf"

    @patch("apps.message_hub.services.court.court_fetcher._api_post")
    def test_skips_empty_wjlj(self, mock_post: MagicMock) -> None:
        mock_post.return_value = {"data": [{"wjlj": "", "c_wjgs": "pdf"}]}
        meta = _fetch_attachments_meta("token", "sdbh-1")
        assert len(meta) == 0

    @patch("apps.message_hub.services.court.court_fetcher._api_post", side_effect=RuntimeError("fail"))
    def test_exception_returns_empty(self, mock_post: MagicMock) -> None:
        meta = _fetch_attachments_meta("token", "sdbh-1")
        assert meta == []


# ===========================================================================
# _api_post tests
# ===========================================================================


class TestApiPost:
    @patch("apps.message_hub.services.court.court_fetcher.httpx.Client")
    def test_success(self, MockClient: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 200, "data": {"total": 5}}
        MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(post=MagicMock(return_value=mock_resp)))
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        client_instance = MockClient.return_value.__enter__.return_value
        client_instance.post.return_value = mock_resp

        result = _api_post("https://api.example.com", "tok", {"pageNum": 1})
        assert result["code"] == 200

    @patch("apps.message_hub.services.court.court_fetcher.httpx.Client")
    def test_401_raises_permission_error(self, MockClient: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        client_instance = MagicMock()
        client_instance.post.return_value = mock_resp
        MockClient.return_value.__enter__ = MagicMock(return_value=client_instance)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(PermissionError, match="Token"):
            _api_post("https://api.example.com", "tok", {})

    @patch("apps.message_hub.services.court.court_fetcher.httpx.Client")
    def test_non_200_code_raises_runtime_error(self, MockClient: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 500, "msg": "服务器错误"}
        mock_resp.raise_for_status = MagicMock()
        client_instance = MagicMock()
        client_instance.post.return_value = mock_resp
        MockClient.return_value.__enter__ = MagicMock(return_value=client_instance)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(RuntimeError, match="API 错误"):
            _api_post("https://api.example.com", "tok", {})


# ===========================================================================
# Run callable with timeout
# ===========================================================================


class TestRunWithCallableTimeout:
    def test_success(self) -> None:
        result = _run_callable_with_timeout(lambda: "hello", timeout_seconds=5)
        assert result == "hello"

    def test_timeout_raises(self) -> None:
        import time

        def slow_func() -> str:
            time.sleep(1)  # 足够触发 0.1s 的 timeout
            return "done"

        with pytest.raises(TimeoutError):
            _run_callable_with_timeout(slow_func, timeout_seconds=0.1)

    def test_exception_propagates(self) -> None:
        def failing_func() -> str:
            raise ValueError("oops")

        with pytest.raises(ValueError, match="oops"):
            _run_callable_with_timeout(failing_func, timeout_seconds=5)


# ===========================================================================
# Mark success / failed
# ===========================================================================


class TestMarkSuccess:
    @patch("apps.message_hub.services.court.court_fetcher.timezone")
    def test_updates_source(self, mock_tz: MagicMock) -> None:
        mock_tz.now.return_value = datetime(2024, 1, 1)
        source = MagicMock()
        _mark_success(source)
        assert source.last_sync_status == SyncStatus.SUCCESS
        assert source.last_sync_error == ""
        source.save.assert_called_once()


class TestMarkFailed:
    @patch("apps.message_hub.services.court.court_fetcher.timezone")
    def test_updates_source(self, mock_tz: MagicMock) -> None:
        mock_tz.now.return_value = datetime(2024, 1, 1)
        source = MagicMock()
        _mark_failed(source, "some error")
        assert source.last_sync_status == SyncStatus.FAILED
        assert source.last_sync_error == "some error"
        source.save.assert_called_once()

    @patch("apps.message_hub.services.court.court_fetcher.timezone")
    def test_truncates_long_error(self, mock_tz: MagicMock) -> None:
        mock_tz.now.return_value = datetime(2024, 1, 1)
        source = MagicMock()
        long_error = "x" * 2000
        _mark_failed(source, long_error)
        assert len(source.last_sync_error) == 1000


# ===========================================================================
# CourtInboxFetcher tests
# ===========================================================================


class TestCourtInboxFetcherFetchNewMessages:
    @patch("apps.message_hub.services.court.court_fetcher._acquire_token")
    @patch("apps.message_hub.services.court.court_fetcher._mark_failed")
    def test_token_acquisition_failure(self, mock_mark_fail: MagicMock, mock_acquire: MagicMock) -> None:
        mock_acquire.side_effect = RuntimeError("no token")
        fetcher = CourtInboxFetcher()
        source = MagicMock()
        with pytest.raises(RuntimeError):
            fetcher.fetch_new_messages(source)
        mock_mark_fail.assert_called_once()

    @patch("apps.message_hub.services.court.court_fetcher._acquire_token")
    @patch("apps.message_hub.services.court.court_fetcher._mark_failed")
    @patch.object(CourtInboxFetcher, "_fetch_with_token", side_effect=PermissionError("token expired"))
    @patch("apps.message_hub.services.court.court_fetcher._invalidate_token")
    def test_permission_error_retries(self, mock_inv: MagicMock, mock_fetch: MagicMock, mock_mark_fail: MagicMock, mock_acquire: MagicMock) -> None:
        mock_acquire.return_value = "tok"
        fetcher = CourtInboxFetcher()
        source = MagicMock()
        # Second acquire also fails
        mock_acquire.side_effect = ["tok", RuntimeError("still bad")]
        with pytest.raises(RuntimeError):
            fetcher.fetch_new_messages(source)
        mock_inv.assert_called_once()


class TestCourtInboxFetcherFetchWithToken:
    @patch("apps.message_hub.services.court.court_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_fetcher._mark_success")
    def test_single_page(self, mock_mark_ok: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = {
            "data": {
                "total": 0,
                "data": [],
            }
        }
        fetcher = CourtInboxFetcher()
        source = MagicMock()
        count = fetcher._fetch_with_token(source, "tok", 1)
        assert count == 0
        mock_mark_ok.assert_called_once()

    @patch("apps.message_hub.services.court.court_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_fetcher._mark_success")
    def test_multi_page(self, mock_mark_ok: MagicMock, mock_post: MagicMock) -> None:
        page1 = {"data": {"total": 40, "data": []}}
        page2 = {"data": {"total": 40, "data": []}}
        mock_post.side_effect = [page1, page2]
        fetcher = CourtInboxFetcher()
        source = MagicMock()
        count = fetcher._fetch_with_token(source, "tok", 1)
        assert count == 0
        assert mock_post.call_count == 2


class TestCourtInboxFetcherProcessPage:
    _PATCH_INBOX = "apps.message_hub.services.court.court_fetcher.InboxMessage"

    def test_skips_empty_sdbh(self) -> None:
        fetcher = CourtInboxFetcher()
        source = MagicMock()
        source.credential.pk = 1
        count = fetcher._process_page(source, "tok", [{"sdbh": ""}])
        assert count == 0

    def test_skips_duplicate(self) -> None:
        with patch(self._PATCH_INBOX) as MockInbox, \
             patch("apps.message_hub.services.court.court_fetcher._fetch_attachments_meta", return_value=[]):
            MockInbox.objects.filter.return_value.exists.return_value = True
            fetcher = CourtInboxFetcher()
            source = MagicMock()
            source.credential.pk = 1
            count = fetcher._process_page(source, "tok", [{"sdbh": "s1"}])
            assert count == 0

    def test_creates_new_message_no_attachments(self) -> None:
        """Test message creation when there are no attachments (simpler path)."""
        with patch(self._PATCH_INBOX) as MockInbox, \
             patch("apps.message_hub.services.court.court_fetcher._fetch_attachments_meta", return_value=[]):
            MockInbox.objects.filter.return_value.exists.return_value = False
            mock_msg = MagicMock()
            MockInbox.objects.create.return_value = mock_msg
            fetcher = CourtInboxFetcher()
            source = MagicMock()
            source.credential.pk = 1
            count = fetcher._process_page(source, "tok", [{"sdbh": "s1", "ah": "case", "wsmc": "doc"}])
            assert count == 1
            MockInbox.objects.create.assert_called_once()

    def test_counts_new_messages(self) -> None:
        """Test that multiple new messages are counted."""
        with patch(self._PATCH_INBOX) as MockInbox, \
             patch("apps.message_hub.services.court.court_fetcher._fetch_attachments_meta", return_value=[]):
            MockInbox.objects.filter.return_value.exists.return_value = False
            MockInbox.objects.create.return_value = MagicMock()
            fetcher = CourtInboxFetcher()
            source = MagicMock()
            source.credential.pk = 1
            records = [{"sdbh": f"s{i}", "ah": f"case-{i}"} for i in range(3)]
            count = fetcher._process_page(source, "tok", records)
            assert count == 3
            assert MockInbox.objects.create.call_count == 3


class TestCourtInboxFetcherBuildDeliveryRecord:
    @patch(_LAZY_DR)
    def test_builds_record(self, MockDR: MagicMock) -> None:
        fetcher = CourtInboxFetcher()
        record = {"ah": "case-1", "fssj": "2024-06-01 10:00:00", "wsmc": "判决", "fymc": "法院", "sdbh": "sd-1"}
        MockDR.return_value = MagicMock()
        result = fetcher._build_delivery_record(record)
        MockDR.assert_called_once()


class TestCourtInboxFetcherDownloadAttachments:
    @patch("apps.message_hub.services.court.court_fetcher.Path")
    def test_download_success(self, MockPath: MagicMock) -> None:
        mock_dir = MagicMock()
        MockPath.return_value.__truediv__ = MagicMock(return_value=mock_dir)
        MockPath.return_value.__enter__ = MagicMock(return_value=mock_dir)
        MockPath.return_value.__exit__ = MagicMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.content = b"file-content"
        mock_resp.raise_for_status = MagicMock()

        with patch("apps.message_hub.services.court.court_fetcher.httpx.Client") as MockClient:
            client_inst = MagicMock()
            client_inst.get.return_value = mock_resp
            MockClient.return_value.__enter__ = MagicMock(return_value=client_inst)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            fetcher = CourtInboxFetcher()
            meta = [{"wjlj": "https://example.com/file.pdf", "filename": "test.pdf"}]
            with patch.object(fetcher, "_download_attachments") as mock_dl:
                mock_dl.return_value = ["/tmp/test.pdf"]
                result = mock_dl(meta, "sdbh-1")
                assert result == ["/tmp/test.pdf"]


class TestCourtInboxFetcherTriggerSmsFlow:
    @patch(_LAZY_DR)
    @patch(_LAZY_DP)
    def test_success(self, MockProcessor: MagicMock, MockDR: MagicMock) -> None:
        MockDR.return_value = MagicMock(case_number="case-1")
        MockProcessor.return_value.process_sms_in_thread.return_value = {"success": True, "case_id": 1}
        fetcher = CourtInboxFetcher()
        fetcher._trigger_sms_flow({"ah": "case-1", "fssj": "2024-01-01 00:00:00", "wsmc": "doc"}, ["/tmp/f.pdf"], 1)
        MockProcessor.return_value.process_sms_in_thread.assert_called_once()

    @patch(_LAZY_DR)
    @patch(_LAZY_DP)
    def test_exception_does_not_raise(self, MockProcessor: MagicMock, MockDR: MagicMock) -> None:
        MockDR.return_value = MagicMock(case_number="case-1")
        MockProcessor.return_value.process_sms_in_thread.side_effect = RuntimeError("processor error")
        fetcher = CourtInboxFetcher()
        # Should not raise
        fetcher._trigger_sms_flow({"ah": "case-1", "fssj": "", "wsmc": ""}, ["/tmp/f.pdf"], 1)


class TestCourtInboxFetcherDownloadAttachment:
    _PATCH_INBOX = "apps.message_hub.services.court.court_fetcher.InboxMessage"

    def test_not_found_raises(self) -> None:
        with patch(self._PATCH_INBOX) as MockInbox:
            MockInbox.objects.get.side_effect = Exception("not found")
            fetcher = CourtInboxFetcher()
            source = MagicMock()
            with pytest.raises(Exception):  # noqa: B017
                fetcher.download_attachment(source, "msg-1", 0)

    def test_local_file_exists(self) -> None:
        with patch(self._PATCH_INBOX) as MockInbox:
            mock_msg = MagicMock()
            mock_msg.attachments_meta = [{"part_index": 0, "filename": "f.pdf", "content_type": "application/pdf", "local_path": "/tmp/f.pdf", "size": 100}]
            MockInbox.objects.get.return_value = mock_msg

            # Patch Path in the court_fetcher module so Path(local_path).exists() returns True
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.read_bytes.return_value = b"content"
            with patch("apps.message_hub.services.court.court_fetcher.Path", return_value=mock_path_instance):
                fetcher = CourtInboxFetcher()
                source = MagicMock()
                content, fname, ctype = fetcher.download_attachment(source, "msg-1", 0)
                assert content == b"content"
                assert fname == "f.pdf"

    def test_part_index_not_found(self) -> None:
        with patch(self._PATCH_INBOX) as MockInbox:
            mock_msg = MagicMock()
            mock_msg.attachments_meta = [{"part_index": 99}]
            MockInbox.objects.get.return_value = mock_msg
            fetcher = CourtInboxFetcher()
            source = MagicMock()
            with pytest.raises(ValueError, match="未找到"):
                fetcher.download_attachment(source, "msg-1", 0)


class TestInvalidateToken:
    @patch(_LAZY_CT)
    @patch(_LAZY_SL)
    @patch(_LAZY_CM)
    def test_with_credential(self, mock_cm: MagicMock, mock_sl: MagicMock, MockToken: MagicMock) -> None:
        cred = MagicMock()
        cred.site_name = "court_zxfw"
        cred.account = "user@test.com"
        mock_sl.get_organization_service.return_value.get_credential.return_value = cred
        from apps.message_hub.services.court.court_fetcher import _invalidate_token

        _invalidate_token(1)
        mock_cm.invalidate_token_cache.assert_called_once_with("court_zxfw", "user@test.com")
        MockToken.objects.filter.return_value.update.assert_called_once()

    @patch(_LAZY_CT)
    @patch(_LAZY_SL)
    @patch(_LAZY_CM)
    def test_no_credential(self, mock_cm: MagicMock, mock_sl: MagicMock, MockToken: MagicMock) -> None:
        mock_sl.get_organization_service.return_value.get_credential.return_value = None
        from apps.message_hub.services.court.court_fetcher import _invalidate_token

        _invalidate_token(999)
        mock_cm.invalidate_token_cache.assert_not_called()
