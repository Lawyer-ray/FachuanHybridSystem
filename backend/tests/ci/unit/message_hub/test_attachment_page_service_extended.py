"""attachment_page_service.py 补充测试：判别函数、重命名锁路径、非 dict 容错.

（既有 test_attachment_page_service.py 已覆盖数页与回填主链路。）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.core.exceptions import NotFoundError
from apps.message_hub.models import InboxMessage
from apps.message_hub.services.attachment_page_service import (
    fill_page_counts,
    has_page_count,
    is_pdf_attachment,
    rename_attachment_in_meta,
)
from apps.message_hub.services.manual_upload_service import get_or_create_manual_source

pytestmark = pytest.mark.django_db


def _make_message(metas: list[dict]) -> InboxMessage:
    from django.utils import timezone

    source = get_or_create_manual_source()
    return InboxMessage.objects.create(
        source=source,
        message_id=f"t-attach-{timezone.now().timestamp()}",
        subject="附件元信息测试",
        received_at=timezone.now(),
        attachments_meta=metas,
        draft_state={},
    )


class TestIsPdfAttachment:
    def test_pdf_content_type(self) -> None:
        assert is_pdf_attachment({"content_type": "application/pdf", "filename": "x"}) is True

    def test_pdf_suffix(self) -> None:
        assert is_pdf_attachment({"content_type": "", "filename": "扫描件.PDF"}) is True

    def test_original_filename_suffix(self) -> None:
        assert is_pdf_attachment({"content_type": None, "filename": "", "original_filename": "doc.pdf"}) is True

    def test_image_not_pdf(self) -> None:
        assert is_pdf_attachment({"content_type": "image/png", "filename": "a.png"}) is False

    def test_empty(self) -> None:
        assert is_pdf_attachment({}) is False


class TestHasPageCount:
    def test_positive(self) -> None:
        assert has_page_count({"page_count": 3}) is True

    def test_string_number(self) -> None:
        assert has_page_count({"page_count": "5"}) is True

    def test_zero_missing_invalid(self) -> None:
        assert has_page_count({"page_count": 0}) is False
        assert has_page_count({}) is False
        assert has_page_count({"page_count": None}) is False
        assert has_page_count({"page_count": "abc"}) is False


class TestFillPageCountsNonDictGuard:
    def test_non_dict_entries_skipped(self, tmp_path: Path) -> None:
        metas: list = [
            "junk-string",
            None,
            42,
            {"filename": "a.pdf", "content_type": "application/pdf", "local_path": ""},
        ]
        assert fill_page_counts(metas) is False
        # 非 dict 条目原样保留，不抛 TypeError
        assert metas[0] == "junk-string"


class TestRenameAttachmentInMeta:
    def _metas(self) -> list[dict]:
        return [
            {
                "filename": "合同.pdf",
                "original_filename": "原始合同.pdf",
                "content_type": "application/pdf",
                "size": 10,
                "part_index": 0,
                "local_path": "",
            },
            {
                "filename": "照片.jpg",
                "original_filename": "照片.jpg",
                "content_type": "image/jpeg",
                "size": 20,
                "part_index": 1,
                "local_path": "",
            },
        ]

    def test_set_custom_name(self) -> None:
        msg = _make_message(self._metas())
        try:
            original, custom = rename_attachment_in_meta(msg, part_index=0, custom_filename="  借条副本  ")
            msg.refresh_from_db()
            assert original == "原始合同.pdf"
            assert custom == "借条副本"
            assert msg.attachments_meta[0]["custom_filename"] == "借条副本"
            # 其他附件不动
            assert "custom_filename" not in msg.attachments_meta[1]
        finally:
            msg.delete()

    def test_custom_equal_to_original_removed(self) -> None:
        """自定义名与原始名相同 → 视为恢复原始名。"""
        msg = _make_message(self._metas())
        try:
            original, custom = rename_attachment_in_meta(msg, part_index=0, custom_filename="原始合同.pdf")
            msg.refresh_from_db()
            assert custom == ""
            assert "custom_filename" not in msg.attachments_meta[0]
        finally:
            msg.delete()

    def test_blank_custom_removes(self) -> None:
        msg = _make_message(self._metas())
        try:
            original, custom = rename_attachment_in_meta(msg, part_index=1, custom_filename="   ")
            assert original == "照片.jpg"
            assert custom == ""
            msg.refresh_from_db()
            assert "custom_filename" not in msg.attachments_meta[1]
        finally:
            msg.delete()

    def test_missing_part_index_raises(self) -> None:
        msg = _make_message(self._metas())
        try:
            with pytest.raises(NotFoundError, match="不存在"):
                rename_attachment_in_meta(msg, part_index=99, custom_filename="x")
        finally:
            msg.delete()

    def test_falls_back_to_filename_when_no_original(self) -> None:
        metas = [{"filename": "只有filename.pdf", "part_index": 0}]
        msg = _make_message(metas)
        try:
            original, _ = rename_attachment_in_meta(msg, part_index=0, custom_filename="别名")
            assert original == "只有filename.pdf"
        finally:
            msg.delete()
