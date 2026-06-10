"""Batch 6 coverage tests for message_hub module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestMessageFetcher:
    def test_abstract_class(self):
        from apps.message_hub.services.base import MessageFetcher

        with pytest.raises(TypeError):
            MessageFetcher()

    def test_download_attachment_not_implemented(self):
        from apps.message_hub.services.base import MessageFetcher

        class ConcreteFetcher(MessageFetcher):
            def fetch_new_messages(self, source):
                return 0

        fetcher = ConcreteFetcher()
        with pytest.raises(NotImplementedError):
            fetcher.download_attachment(None, "msg1", 0)


class TestInboxQuery:
    def test_get_base_queryset(self):
        from apps.message_hub.services.inbox_query import get_base_queryset

        qs = get_base_queryset()
        assert qs is not None

    def test_list_sources(self):
        from apps.message_hub.services.inbox_query import list_sources

        result = list_sources()
        assert isinstance(result, list)

    def test_get_enabled_sources(self):
        from apps.message_hub.services.inbox_query import get_enabled_sources

        qs = get_enabled_sources()
        assert qs is not None
