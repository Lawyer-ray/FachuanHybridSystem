"""收件箱消息查询服务。"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from apps.message_hub.models import InboxMessage, MessageSource


def get_base_queryset() -> QuerySet[InboxMessage]:
    """获取收件箱消息基础查询集（含 source 和 credential 关联）。"""
    return InboxMessage.objects.select_related("source", "source__credential").order_by("-received_at")


def get_message_or_none(pk: int) -> InboxMessage | None:
    """按 ID 获取单条消息，不存在返回 None。"""
    return get_base_queryset().filter(pk=pk).first()


# ── MessageSource 查询 ──────────────────────────────────────


def list_sources() -> list[MessageSource]:
    """获取所有消息来源（含凭证关联）。"""
    return list(MessageSource.objects.select_related("credential").all())


def get_source_or_none(source_id: int) -> MessageSource | None:
    """按 ID 获取消息来源，不存在返回 None。"""
    return MessageSource.objects.select_related("credential").filter(pk=source_id).first()


def create_source(**kwargs: Any) -> MessageSource:
    """创建消息来源。"""
    return MessageSource.objects.create(**kwargs)


def get_enabled_sources() -> QuerySet[MessageSource]:
    """获取所有启用的消息来源。"""
    return MessageSource.objects.filter(is_enabled=True)
