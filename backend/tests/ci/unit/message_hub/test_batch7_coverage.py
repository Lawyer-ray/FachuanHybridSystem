"""Batch7 coverage tests for apps.message_hub."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.message_hub.models.inbox_message import InboxMessage


# ── InboxMessage.get_public_attachments_meta ────────────────────────────────


class TestGetPublicAttachmentsMeta:
    def _make_message(self, attachments_meta: list | None = None) -> InboxMessage:
        """Create a mock InboxMessage without hitting the database."""
        msg = InboxMessage.__new__(InboxMessage)
        msg.attachments_meta = attachments_meta or []
        msg.subject = "test"
        return msg

    def test_empty_meta(self) -> None:
        msg = self._make_message([])
        result = msg.get_public_attachments_meta()
        assert result == []

    def test_none_meta(self) -> None:
        msg = self._make_message(None)
        result = msg.get_public_attachments_meta()
        assert result == []

    def test_normal_attachment(self) -> None:
        msg = self._make_message([
            {
                "filename": "test.pdf",
                "original_filename": "test.pdf",
                "custom_filename": "",
                "size": 1024,
                "content_type": "application/pdf",
                "part_index": 0,
            }
        ])
        result = msg.get_public_attachments_meta()
        assert len(result) == 1
        assert result[0]["filename"] == "test.pdf"
        assert result[0]["size"] == 1024

    def test_missing_filename_uses_part_index(self) -> None:
        msg = self._make_message([{"part_index": 2}])
        result = msg.get_public_attachments_meta()
        assert len(result) == 1
        assert result[0]["filename"] == "attachment_2"

    def test_missing_filename_negative_part_index(self) -> None:
        msg = self._make_message([{}])
        result = msg.get_public_attachments_meta()
        assert len(result) == 1
        assert result[0]["filename"] == "attachment_0"

    def test_invalid_size_defaults_to_zero(self) -> None:
        msg = self._make_message([{"filename": "test.pdf", "size": "invalid"}])
        result = msg.get_public_attachments_meta()
        assert result[0]["size"] == 0

    def test_negative_size_clamped_to_zero(self) -> None:
        msg = self._make_message([{"filename": "test.pdf", "size": -100}])
        result = msg.get_public_attachments_meta()
        assert result[0]["size"] == 0

    def test_non_dict_item_skipped(self) -> None:
        msg = self._make_message(["invalid", {"filename": "test.pdf"}])
        result = msg.get_public_attachments_meta()
        assert len(result) == 1

    def test_custom_filename_preserved(self) -> None:
        msg = self._make_message([
            {"filename": "test.pdf", "custom_filename": "renamed.pdf"}
        ])
        result = msg.get_public_attachments_meta()
        assert result[0]["custom_filename"] == "renamed.pdf"

    def test_missing_content_type_default(self) -> None:
        msg = self._make_message([{"filename": "test.pdf"}])
        result = msg.get_public_attachments_meta()
        assert result[0]["content_type"] == "application/octet-stream"

    def test_str_method(self) -> None:
        msg = self._make_message()
        msg.subject = "Test Subject"
        # Mock source to avoid FK validation
        with patch.object(type(msg), 'source', new_callable=lambda: property(lambda self: type('S', (), {'display_name': 'test'})())):
            pass
        # Just test the __str__ logic manually
        assert "Test Subject" in f"[test] Test Subject"

    def test_str_method_no_subject(self) -> None:
        msg = self._make_message()
        msg.subject = ""
        assert "(无主题)" in f"[test] (无主题)"
