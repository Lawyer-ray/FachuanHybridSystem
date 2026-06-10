"""Extended tests for message_hub services - inbox_query, base, court."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestInboxQuery:
    def test_import(self):
        from apps.message_hub.services.inbox_query import (
            get_base_queryset,
            get_message_or_none,
            list_sources,
            get_source_or_none,
            create_source,
            get_enabled_sources,
        )
        assert callable(get_base_queryset)
        assert callable(get_message_or_none)
        assert callable(list_sources)
        assert callable(get_source_or_none)
        assert callable(create_source)
        assert callable(get_enabled_sources)


class TestMessageHubBase:
    def test_import_base(self):
        from apps.message_hub.services import base

        assert base is not None


class TestMessageHubCourt:
    def test_import_court(self):
        from apps.message_hub.services import court

        assert court is not None


class TestMessageHubModels:
    def test_import_models(self):
        from apps.message_hub.models import InboxMessage, MessageSource

        assert InboxMessage is not None
        assert MessageSource is not None
