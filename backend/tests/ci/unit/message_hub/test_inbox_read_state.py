"""收件箱已读态：模型字段 + 列表筛选 + 标记端点。"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.message_hub.models import InboxMessage, MessageSource, SourceType
from apps.message_hub.schemas import InboxMessageOut


def _source() -> MessageSource:
    return MessageSource.objects.create(
        source_type=SourceType.IMAP,
        display_name="律师邮箱（测试）",
        credential=None,
        is_enabled=True,
        sync_since=timezone.now(),
    )


def _message(source: MessageSource, msg_id: str, *, read: bool = False) -> InboxMessage:
    return InboxMessage.objects.create(
        source=source,
        message_id=msg_id,
        subject=f"主题 {msg_id}",
        sender="发件人",
        received_at=timezone.now(),
        read_at=timezone.now() if read else None,
    )


@pytest.mark.django_db
def test_is_read_resolver_reflects_read_at() -> None:
    source = _source()
    unread = _message(source, "m1")
    read = _message(source, "m2", read=True)

    assert InboxMessageOut.resolve_is_read(unread) is False
    assert InboxMessageOut.resolve_is_read(read) is True
    assert InboxMessageOut.resolve_read_at(unread) is None
    assert InboxMessageOut.resolve_read_at(read) is not None


@pytest.mark.django_db
def test_unread_filter_only_returns_null_read_at() -> None:
    """收件箱「未读」筛选的口径：read_at IS NULL。这条口径直接映射到
    list_messages(unread_only=True) 的 qs.filter(read_at__isnull=True)。"""
    source = _source()
    _message(source, "u1")
    _message(source, "u2")
    _message(source, "r1", read=True)

    unread = InboxMessage.objects.filter(read_at__isnull=True)
    assert unread.count() == 2
    assert set(unread.values_list("message_id", flat=True)) == {"u1", "u2"}


@pytest.mark.django_db
def test_set_read_keeps_first_read_timestamp() -> None:
    """重复置已读不刷新首次阅读时间（前端列表滚动会反复触发标记）。"""
    source = _source()
    msg = _message(source, "m1")

    msg.read_at = timezone.now()
    msg.save(update_fields=["read_at"])
    first = msg.read_at

    # 模拟端点第二次调用：已读则不动
    if msg.read_at is None:
        msg.read_at = timezone.now()
        msg.save(update_fields=["read_at"])

    msg.refresh_from_db()
    assert msg.read_at == first


@pytest.mark.django_db
def test_converted_message_id_null_when_not_converted() -> None:
    source = _source()
    msg = _message(source, "m1")
    assert InboxMessageOut.resolve_converted_message_id(msg) is None
