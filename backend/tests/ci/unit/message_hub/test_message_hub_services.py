"""
Tests for apps.message_hub.services — 消息中心服务
"""

from __future__ import annotations

import pytest


class TestMessageHubModules:
    """消息中心模块可导入性测试"""

    def test_base_importable(self) -> None:
        from apps.message_hub.services.base import MessageFetcher

        assert MessageFetcher is not None

    def test_inbox_query_importable(self) -> None:
        from apps.message_hub.services.inbox_query import get_base_queryset

        assert callable(get_base_queryset)

    def test_court_fetcher_importable(self) -> None:
        from apps.message_hub.services.court.court_fetcher import CourtInboxFetcher

        assert CourtInboxFetcher is not None

    def test_court_schedule_fetcher_importable(self) -> None:
        from apps.message_hub.services.court.court_schedule_fetcher import CourtScheduleFetcher

        assert CourtScheduleFetcher is not None

    def test_imap_fetcher_importable(self) -> None:
        from apps.message_hub.services.imap.imap_fetcher import ImapFetcher

        assert ImapFetcher is not None
