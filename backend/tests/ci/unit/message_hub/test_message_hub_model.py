"""Message Hub Model 测试 - InboxMessage, MessageSource"""

from __future__ import annotations

from typing import Any

import pytest
from django.utils import timezone

from apps.message_hub.models import InboxMessage, MessageSource, SourceType, SyncStatus
from apps.organization.models import AccountCredential, LawFirm, Lawyer


def _create_source() -> tuple[AccountCredential, MessageSource]:
    """创建消息来源测试数据"""
    firm = LawFirm.objects.create(name="模型测试律所")
    lawyer = Lawyer.objects.create_user(username="model_msg_lawyer", real_name="模型律师", law_firm=firm)
    cred = AccountCredential.objects.create(
        lawyer=lawyer, site_name="model_site", account="model_account", password="test_pass"
    )
    source = MessageSource.objects.create(
        credential=cred,
        source_type=SourceType.IMAP,
        display_name="模型测试邮箱",
        is_enabled=True,
        poll_interval_minutes=30,
        sync_since=timezone.now(),
    )
    return cred, source


@pytest.mark.django_db
class TestMessageSourceModel:
    """MessageSource 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回显示名称"""
        _, source = _create_source()
        assert "模型测试邮箱" in str(source)

    def test_source_type_choices(self) -> None:
        """来源类型选项"""
        assert SourceType.IMAP == "imap"
        assert SourceType.COURT_INBOX == "court_inbox"
        assert SourceType.COURT_SCHEDULE == "court_schedule"

    def test_sync_status_choices(self) -> None:
        """同步状态选项"""
        assert SyncStatus.PENDING == "pending"
        assert SyncStatus.SUCCESS == "success"
        assert SyncStatus.FAILED == "failed"

    def test_create_source_with_imap_settings(self) -> None:
        """创建 IMAP 来源包含设置"""
        _, source = _create_source()
        source.imap_host = "mail.example.com"
        source.imap_account = "test@example.com"
        source.save()
        assert source.imap_host == "mail.example.com"

    def test_create_source_with_sender_filter(self) -> None:
        """创建来源包含发件人过滤"""
        _, source = _create_source()
        source.sender_whitelist = "sender1@example.com\nsender2@example.com"
        source.save()
        assert "sender1@example.com" in source.sender_whitelist


@pytest.mark.django_db
class TestInboxMessageModel:
    """InboxMessage 模型测试"""

    def test_create_message(self) -> None:
        """创建收件箱消息"""
        _, source = _create_source()
        msg = InboxMessage.objects.create(
            source=source,
            message_id="msg_001",
            subject="测试邮件主题",
            sender="test@example.com",
            received_at=timezone.now(),
        )
        assert msg.subject == "测试邮件主题"
        assert msg.sender == "test@example.com"

    def test_unique_together(self) -> None:
        """source 和 message_id 应唯一"""
        _, source = _create_source()
        InboxMessage.objects.create(
            source=source,
            message_id="unique_msg",
            subject="唯一性测试",
            received_at=timezone.now(),
        )
        with pytest.raises(Exception):
            InboxMessage.objects.create(
                source=source,
                message_id="unique_msg",
                subject="重复消息",
                received_at=timezone.now(),
            )

    def test_message_with_attachments(self) -> None:
        """创建消息包含附件"""
        _, source = _create_source()
        attachments_meta = [
            {"filename": "doc.pdf", "size": 12345, "content_type": "application/pdf", "part_index": 0},
            {"filename": "image.jpg", "size": 67890, "content_type": "image/jpeg", "part_index": 1},
        ]
        msg = InboxMessage.objects.create(
            source=source,
            message_id="msg_with_attachments",
            subject="附件邮件",
            has_attachments=True,
            attachments_meta=attachments_meta,
            received_at=timezone.now(),
        )
        assert msg.has_attachments is True
        assert len(msg.attachments_meta) == 2

    def test_get_public_attachments_meta(self) -> None:
        """get_public_attachments_meta 应返回公开的附件元信息"""
        _, source = _create_source()
        attachments_meta = [
            {"filename": "doc.pdf", "size": 12345, "content_type": "application/pdf", "part_index": 0},
        ]
        msg = InboxMessage.objects.create(
            source=source,
            message_id="msg_public_meta",
            subject="公开元信息测试",
            has_attachments=True,
            attachments_meta=attachments_meta,
            received_at=timezone.now(),
        )
        public_meta = msg.get_public_attachments_meta()
        assert len(public_meta) == 1
        assert public_meta[0]["filename"] == "doc.pdf"
        assert public_meta[0]["size"] == 12345

    def test_message_with_body(self) -> None:
        """创建消息包含正文"""
        _, source = _create_source()
        msg = InboxMessage.objects.create(
            source=source,
            message_id="msg_with_body",
            subject="正文邮件",
            body_text="纯文本正文",
            body_html="<p>HTML正文</p>",
            received_at=timezone.now(),
        )
        assert msg.body_text == "纯文本正文"
        assert msg.body_html == "<p>HTML正文</p>"
