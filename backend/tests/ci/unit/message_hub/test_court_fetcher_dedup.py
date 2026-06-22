"""court_fetcher 去重行为单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

try:
    from plugins import has_message_hub_plugin
    _HAS_MH = has_message_hub_plugin()
except ImportError:
    _HAS_MH = False

pytestmark = pytest.mark.skipif(not _HAS_MH, reason="message_hub plugin not installed")

from django.utils import timezone

from apps.message_hub.models import InboxMessage, MessageSource, SourceType
if _HAS_MH:
    from plugins.message_hub.services.court.court_fetcher import CourtInboxFetcher

from apps.organization.models import AccountCredential, Lawyer

@pytest.mark.django_db
class TestCourtFetcherDedup:
    """同一送达事件跨律师同步时，仅触发一次主流程。"""

    def setup_method(self) -> None:
        self.fetcher = CourtInboxFetcher()

        self.lawyer1, _ = Lawyer.objects.get_or_create(
            username="test_court_fetcher_lawyer_1",
            defaults={"real_name": "律师甲"},
        )
        self.lawyer2, _ = Lawyer.objects.get_or_create(
            username="test_court_fetcher_lawyer_2",
            defaults={"real_name": "律师乙"},
        )

        self.credential1 = AccountCredential.objects.create(
            lawyer=self.lawyer1,
            site_name="court_zxfw",
            account="lawyer1_account",
            password="placeholder",
            url="https://zxfw.court.gov.cn",
        )
        self.credential2 = AccountCredential.objects.create(
            lawyer=self.lawyer2,
            site_name="court_zxfw",
            account="lawyer2_account",
            password="placeholder",
            url="https://zxfw.court.gov.cn",
        )

        self.source1 = MessageSource.objects.create(
            credential=self.credential1,
            source_type=SourceType.COURT_INBOX,
            display_name="律师甲收件箱",
            is_enabled=True,
            poll_interval_minutes=30,
            sync_since=timezone.now(),
        )
        self.source2 = MessageSource.objects.create(
            credential=self.credential2,
            source_type=SourceType.COURT_INBOX,
            display_name="律师乙收件箱",
            is_enabled=True,
            poll_interval_minutes=30,
            sync_since=timezone.now(),
        )

    @patch("plugins.message_hub.services.court.court_fetcher._acquire_token", return_value="fake-token")
    @patch("plugins.message_hub.services.court.court_fetcher._fetch_attachments_meta")
    @patch("plugins.message_hub.services.court.court_fetcher._api_post")
    def test_same_event_keeps_two_inbox_messages_but_triggers_main_flow_once(
        self,
        mock_api_post,
        mock_fetch_attachments,
        _mock_acquire_token,
    ) -> None:
        shared_record = {
            "sdbh": "SDBH-SHARED-001",
            "ah": "（2026）粤0101民初100号",
            "wsmc": "判决书",
            "fymc": "广东省某法院",
            "fqr": "书记员",
            "sdzt": "已送达",
            "qdzt": "已签收",
            "fssj": "2026-04-15 10:00:00",
        }
        mock_api_post.return_value = {"data": {"total": 1, "data": [shared_record]}}
        mock_fetch_attachments.return_value = [
            {
                "filename": "doc.pdf",
                "original_filename": "doc.pdf",
                "content_type": "application/pdf",
                "size": 0,
                "part_index": 0,
                "wjlj": "https://example.com/doc.pdf",
            }
        ]

        existing_sms = SimpleNamespace(id=999, status="completed")

        with (
            patch.object(self.fetcher, "_download_attachments", return_value=["/tmp/doc.pdf"]) as mock_download,
        ):
            count1 = self.fetcher.fetch_new_messages(self.source1)
            count2 = self.fetcher.fetch_new_messages(self.source2)

        assert count1 == 1
        assert count2 == 1

        assert InboxMessage.objects.filter(message_id="SDBH-SHARED-001").count() == 2
        assert InboxMessage.objects.filter(source=self.source1, message_id="SDBH-SHARED-001").count() == 1
        assert InboxMessage.objects.filter(source=self.source2, message_id="SDBH-SHARED-001").count() == 1

        assert mock_download.call_count == 2
