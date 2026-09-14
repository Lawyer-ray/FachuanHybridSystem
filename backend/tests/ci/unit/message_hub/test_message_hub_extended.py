"""Extended tests for message_hub services - inbox_query, base, court."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_message_hub_plugin
    _HAS_MH = has_message_hub_plugin()
except ImportError:
    _HAS_MH = False

pytestmark = pytest.mark.skipif(not _HAS_MH, reason="message_hub plugin not installed")



class TestInboxQuery:
    def test_import(self):
        from apps.message_hub.services.inbox_query import (
            create_source,
            get_base_queryset,
            get_enabled_sources,
            get_message_or_none,
            get_source_or_none,
            list_sources,
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
        from plugins.message_hub.services import court

        assert court is not None


class TestMessageHubModels:
    def test_import_models(self):
        from apps.message_hub.models import InboxMessage, MessageSource

        assert InboxMessage is not None
        assert MessageSource is not None
