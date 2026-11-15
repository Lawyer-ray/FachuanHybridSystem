"""manual_upload_service.py 补充测试：追加附件、重命名、删除清理。

（既有 test_manual_upload.py 已覆盖创建/校验/草稿主链路。）
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.message_hub.models import InboxMessage
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.message_hub.services.manual_upload_service import (
    MANUAL_SOURCE_DISPLAY_NAME,
    ManualUploadFetcher,
    append_manual_attachments,
    create_manual_message,
    delete_manual_message,
    get_or_create_manual_source,
    rename_manual_message,
    save_draft,
)


def _cleanup(message: InboxMessage) -> None:
    for att in message.attachments_meta or []:
        path = resolve_media_attachment_path(str(att.get("local_path", "")))
        if path is not None and path.exists():
            path.unlink()
    message.delete()


pytestmark = pytest.mark.django_db


class TestAppendManualAttachments:
    def test_part_index_continues(self) -> None:
        base = SimpleUploadedFile("base.pdf", b"%PDF-1.4 base", content_type="application/pdf")
        extra1 = SimpleUploadedFile("more1.pdf", b"%PDF-1.4 one", content_type="application/pdf")
        extra2 = SimpleUploadedFile("more2.png", b"\x89PNG", content_type="image/png")
        msg = create_manual_message([base])
        try:
            returned = append_manual_attachments(msg, [extra1, extra2])
            msg.refresh_from_db()

            assert len(msg.attachments_meta) == 3
            indexes = [a["part_index"] for a in msg.attachments_meta]
            assert indexes == [0, 1, 2]
            # 调用方实例与库内同步
            assert returned is msg
            assert returned.attachments_meta == msg.attachments_meta
            # 新附件真实落盘
            for att in msg.attachments_meta[1:]:
                path = resolve_media_attachment_path(str(att.get("local_path", "")))
                assert path is not None and path.exists()
        finally:
            _cleanup(msg)

    def test_append_to_message_without_attachments(self) -> None:
        from django.utils import timezone

        source = get_or_create_manual_source()
        msg = InboxMessage.objects.create(
            source=source,
            message_id="manual-append-empty",
            subject="空材料包",
            received_at=timezone.now(),
            attachments_meta=[],
        )
        try:
            f = SimpleUploadedFile("only.pdf", b"%PDF-1.4", content_type="application/pdf")
            append_manual_attachments(msg, [f])
            msg.refresh_from_db()
            assert [a["part_index"] for a in msg.attachments_meta] == [0]
            assert msg.has_attachments is True
        finally:
            _cleanup(msg)


class TestRenameManualMessage:
    def test_rename_strips_and_persists(self) -> None:
        msg = create_manual_message([SimpleUploadedFile("a.pdf", b"%PDF-1.4", content_type="application/pdf")])
        try:
            returned = rename_manual_message(msg, "  张三 民间借贷  ")
            msg.refresh_from_db()
            assert msg.subject == "张三 民间借贷"
            assert returned is msg
        finally:
            _cleanup(msg)

    def test_rename_empty_rejected(self) -> None:
        msg = create_manual_message([SimpleUploadedFile("a.pdf", b"%PDF-1.4", content_type="application/pdf")])
        try:
            with pytest.raises(ValidationError, match="不能为空"):
                rename_manual_message(msg, "   ")
        finally:
            _cleanup(msg)

    def test_rename_truncates_to_512(self) -> None:
        msg = create_manual_message([SimpleUploadedFile("a.pdf", b"%PDF-1.4", content_type="application/pdf")])
        try:
            rename_manual_message(msg, "长" * 600)
            msg.refresh_from_db()
            assert len(msg.subject) == 512
        finally:
            _cleanup(msg)


class TestDeleteManualMessage:
    def test_deletes_files_and_row(self) -> None:
        f1 = SimpleUploadedFile("d1.pdf", b"%PDF-1.4 one", content_type="application/pdf")
        f2 = SimpleUploadedFile("d2.png", b"\x89PNG two", content_type="image/png")
        msg = create_manual_message([f1, f2])
        pk = msg.pk
        paths = [resolve_media_attachment_path(str(att.get("local_path", ""))) for att in msg.attachments_meta]

        deleted = delete_manual_message(msg)

        assert deleted == 2
        assert InboxMessage.objects.filter(pk=pk).count() == 0
        for path in paths:
            assert path is not None and not path.exists()

    def test_message_without_attachments(self) -> None:
        source = get_or_create_manual_source()
        from django.utils import timezone

        msg = InboxMessage.objects.create(
            source=source,
            message_id="manual-del-empty",
            subject="无附件",
            received_at=timezone.now(),
        )
        assert delete_manual_message(msg) == 0
        assert not InboxMessage.objects.filter(pk=msg.pk).exists()

    def test_row_deleted_before_files(self, monkeypatch) -> None:
        """删除顺序：DB 行先没，物理文件后清。

        反序会让 delete() 的失败（外键保护 / 异常）留下「文件已删、记录还在」的破包，
        所以这里断言 delete_media_file 被调用的那一刻行已经不在了。
        """
        msg = create_manual_message([SimpleUploadedFile("o.pdf", b"%PDF-1.4 o", content_type="application/pdf")])
        pk = msg.pk
        seen: list[bool] = []

        from apps.message_hub.services import manual_upload_service as svc

        real_delete = svc.delete_media_file

        def spy(path: str) -> bool:
            seen.append(InboxMessage.objects.filter(pk=pk).exists())
            return real_delete(path)

        monkeypatch.setattr(svc, "delete_media_file", spy)
        delete_manual_message(msg)
        assert seen == [False], "物理文件必须在 DB 行删除之后才清理"

    def test_file_cleanup_failure_does_not_undo_delete(self, monkeypatch) -> None:
        """物理文件清理失败只是残留孤儿文件，回包仍是成功、行仍然删掉。"""
        msg = create_manual_message([SimpleUploadedFile("w.pdf", b"%PDF-1.4 w", content_type="application/pdf")])
        pk = msg.pk

        from apps.message_hub.services import manual_upload_service as svc

        monkeypatch.setattr(svc, "delete_media_file", lambda _p: False)
        assert delete_manual_message(msg) == 0
        assert not InboxMessage.objects.filter(pk=pk).exists()

    def test_protected_by_payment_intake_keeps_record_and_files(self) -> None:
        """被财务凭证引用时必须拒绝删除，且**一个物理文件都不能动**。

        回归点：原实现先删附件再 delete()，PROTECT 触发后留下指向空文件的破包。
        """
        from datetime import date
        from decimal import Decimal

        from apps.contracts.models import PaymentIntake
        from apps.core.exceptions import ConflictError

        upload = SimpleUploadedFile("p.pdf", b"%PDF-1.4 p", content_type="application/pdf")
        msg = create_manual_message([upload])
        pk = msg.pk
        path = resolve_media_attachment_path(str(msg.attachments_meta[0]["local_path"]))
        PaymentIntake.objects.create(
            inbox_message=msg,
            dedupe_key="del-guard-1",
            amount=Decimal("100"),
            received_at=date(2026, 1, 1),
        )

        with pytest.raises(ConflictError) as exc:
            delete_manual_message(msg)
        assert "收款" in str(exc.value)
        assert InboxMessage.objects.filter(pk=pk).exists()
        assert path is not None and path.exists(), "被拒绝的删除不得留下残缺附件"

        # 清场：先撤掉凭证才能删掉这条消息
        PaymentIntake.objects.filter(inbox_message_id=pk).delete()
        _cleanup(InboxMessage.objects.get(pk=pk))

    def test_converting_message_keeps_original_row(self) -> None:
        """删材料包（转换产物）时，原邮件记录保留，converted_message 置空回到未转。"""
        from django.utils import timezone

        source = get_or_create_manual_source()
        original = InboxMessage.objects.create(
            source=source,
            message_id="orig-del-1",
            subject="原邮件",
            received_at=timezone.now(),
        )
        pack = create_manual_message([SimpleUploadedFile("c.pdf", b"%PDF-1.4 c", content_type="application/pdf")])
        original.converted_message = pack
        original.save(update_fields=["converted_message"])

        delete_manual_message(pack)

        original.refresh_from_db()
        assert original.converted_message_id is None, "材料包删掉后原邮件必须回到「未转」，否则收件箱会显示死链"
        _cleanup(original)


class TestSaveDraft:
    def test_empty_draft_normalized(self) -> None:
        msg = create_manual_message([SimpleUploadedFile("a.pdf", b"%PDF-1.4", content_type="application/pdf")])
        try:
            save_draft(msg.pk, None)
            msg.refresh_from_db()
            assert msg.draft_state == {}
        finally:
            _cleanup(msg)


class TestManualUploadFetcher:
    def test_fetch_new_messages_returns_zero(self) -> None:
        source = get_or_create_manual_source()
        assert ManualUploadFetcher().fetch_new_messages(source) == 0


class TestManualSourceDefaults:
    def test_source_defaults(self) -> None:
        source = get_or_create_manual_source()
        assert source.display_name == MANUAL_SOURCE_DISPLAY_NAME
        assert source.credential is None
        assert source.is_enabled is True
        assert source.poll_interval_minutes == 0
