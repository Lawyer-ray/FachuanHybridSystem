"""收件箱列表 `slim=true`：剔除集、默认形状不变、SQL 不增。

背景（实测真库 limit=100）：列表响应里**没有** body_text / body_html（正文走
详情接口 ``GET /messages/{id}``），体积来自每行 27 个键（其中 15 个收件箱行
从不消费）。slim 把这些键整体省掉（含键名开销），492 行全量 481.1 KB → 325.3 KB。
"""

from __future__ import annotations

import json

import pytest
from django.db import connection
from django.http import JsonResponse
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.message_hub.api.inbox_api import list_messages
from apps.message_hub.models import InboxMessage, MessageSource
from apps.message_hub.schemas import InboxMessageOut, InboxMessageSlimOut

# 收件箱行真正消费的 12 个字段（InboxRowItem / InboxList / MessageDrawer / MessageContent）
ROW_SUMMARY_FIELDS = {
    "id",
    "source_name",
    "source_type",
    "subject",
    "sender",
    "recipient",
    "received_at",
    "has_attachments",
    "attachment_count",
    "attachments",
    "is_read",
    "converted_message_id",
}

# 材料预处理桌面 / 调试才用、收件箱行不消费 —— slim 必须整体省掉的 15 个键
DROPPED_FIELDS = {
    "status",
    "segs",
    "named",
    "pages",
    "mats",
    "types",
    "compose",
    "created_at",
    "uploaded_by_id",
    "uploaded_by_name",
    "upload_link_id",
    "upload_link_title",
    "upload_contract_id",
    "upload_contract_name",
    "read_at",
}


class _AdminRequest:
    """只提供 list_messages 用到的 request.user，且让 is_admin_user 判定为真。"""

    def __init__(self) -> None:
        self.user = type("_U", (), {"id": 1, "is_admin": True, "is_superuser": True, "is_authenticated": True})()


def _source() -> MessageSource:
    return MessageSource.objects.create(
        source_type="imap",
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
        sender="发件人 <a@example.com>",
        body_text="正文正文" * 50,
        body_html="<p>正文正文</p>" * 50,
        received_at=timezone.now(),
        read_at=timezone.now() if read else None,
        has_attachments=True,
        attachments_meta=[
            {
                "filename": "判决书.pdf",
                "original_filename": "判决书.pdf",
                "size": 1024,
                "content_type": "application/pdf",
                "part_index": 0,
                "local_path": "/secret/path.pdf",
            }
        ],
    )


def _rows() -> list[dict]:
    source = _source()
    _message(source, "m1")
    _message(source, "m2", read=True)
    resp = list_messages(_AdminRequest(), limit=10, slim=True)
    assert isinstance(resp, JsonResponse)
    return json.loads(resp.content)


@pytest.mark.django_db
def test_slim_row_carries_only_row_summary_fields() -> None:
    rows = _rows()

    assert rows, "夹具应至少有一行"
    for row in rows:
        assert set(row) == ROW_SUMMARY_FIELDS
        assert set(row) == set(InboxMessageSlimOut.model_fields)
        assert not (set(row) & DROPPED_FIELDS), f"slim 仍带回被剔除字段：{set(row) & DROPPED_FIELDS}"

    assert {r["subject"] for r in rows} == {"主题 m1", "主题 m2"}
    assert rows[0]["attachment_count"] == 1
    # 附件元信息仍保留（行内小样/预览要用），但不含 local_path 等内部字段
    assert rows[0]["attachments"][0]["filename"] == "判决书.pdf"
    assert "local_path" not in rows[0]["attachments"][0]
    assert {r["is_read"] for r in rows} == {True, False}


@pytest.mark.django_db
def test_default_response_shape_unmoved() -> None:
    """不带 slim：仍返回 QuerySet（由 response=list[InboxMessageOut] 序列化），
    27 个字段全在——默认路径的键集与本改动前逐字节一致。"""
    source = _source()
    _message(source, "m1")

    qs = list_messages(_AdminRequest(), limit=10)
    assert not isinstance(qs, JsonResponse), "默认路径不得走 slim 的 JsonResponse 分支"
    full = [InboxMessageOut.from_orm(obj).model_dump() for obj in qs]

    assert len(full) == 1
    assert set(full[0]) == set(InboxMessageOut.model_fields)
    assert set(full[0]) == ROW_SUMMARY_FIELDS | DROPPED_FIELDS
    # 列表从不带正文（正文只走 GET /messages/{id}），slim 与默认在这点上一致
    assert not ({"body_text", "body_html"} & set(full[0]))


@pytest.mark.django_db
def test_slim_does_not_add_queries() -> None:
    source = _source()
    for i in range(3):
        _message(source, f"m{i}")

    with CaptureQueriesContext(connection) as full_ctx:
        len(list_messages(_AdminRequest(), limit=10))
    with CaptureQueriesContext(connection) as slim_ctx:
        assert isinstance(list_messages(_AdminRequest(), limit=10, slim=True), JsonResponse)

    assert len(full_ctx) == 1
    assert len(slim_ctx) == len(full_ctx)
