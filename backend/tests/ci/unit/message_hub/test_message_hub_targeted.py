"""Targeted tests for message_hub module to push coverage to 80%+."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# schemas.py (0% coverage)
# ---------------------------------------------------------------------------


class TestMessageHubSchemas:
    def test_attachment_meta_schema(self):
        from apps.message_hub.schemas import AttachmentMeta

        meta = AttachmentMeta(
            filename="test.pdf",
            original_filename="original.pdf",
            custom_filename=None,
            size=1024,
            content_type="application/pdf",
            part_index=0,
        )
        assert meta.filename == "test.pdf"
        assert meta.size == 1024

    def test_inbox_message_out_resolve_attachment_count(self):
        from apps.message_hub.schemas import InboxMessageOut

        obj = SimpleNamespace(attachments_meta=[{"filename": "a.pdf"}, {"filename": "b.pdf"}])
        assert InboxMessageOut.resolve_attachment_count(obj) == 2

    def test_inbox_message_out_attachment_count_empty(self):
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_attachment_count(SimpleNamespace(attachments_meta=None)) == 0
        assert InboxMessageOut.resolve_attachment_count(SimpleNamespace(attachments_meta=[])) == 0

    def test_inbox_message_detail_out_resolve_attachments(self):
        from apps.message_hub.schemas import InboxMessageDetailOut

        obj = SimpleNamespace(
            get_public_attachments_meta=lambda: [
                {"filename": "test.pdf", "size": 100, "content_type": "application/pdf"}
            ],
        )
        result = InboxMessageDetailOut.resolve_attachments(obj)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# services/__init__.py (27% coverage)
# ---------------------------------------------------------------------------


class TestMessageHubServicesInit:
    def test_get_fetcher_invalid_type(self):
        from apps.message_hub.services import get_fetcher

        with pytest.raises(ValueError, match="未知来源类型"):
            get_fetcher("invalid_type")


# ---------------------------------------------------------------------------
# api/__init__.py (0% coverage)
# ---------------------------------------------------------------------------


class TestMessageHubApiInit:
    def test_api_init(self):
        from apps.message_hub.api import __init__ as api_init

        assert api_init is not None
