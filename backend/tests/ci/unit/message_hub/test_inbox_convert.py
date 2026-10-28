"""收件箱「转材料包」链路测试。

覆盖转换的三个关键约束：
1. 外部来源消息的附件字节真的搬进 manual_upload 暂存目录（不是原地改 source）；
2. 幂等——重复点「转材料包」不再复制第二份字节；
3. 无附件 / 取回失败时不沉淀空材料包，而是明确报错。
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.core.exceptions import ValidationException
from apps.message_hub.models import InboxMessage, MessageSource, SourceType
from apps.message_hub.services import get_fetcher
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.message_hub.services.inbox_convert_service import convert_to_material_pack
from apps.message_hub.services.manual_upload_service import create_manual_message


class _StubFetcher:
    """冒充外部来源 fetcher：按 part_index 返回固定字节（不碰真实 IMAP / 一张网）。"""

    def __init__(self, payloads: dict[int, bytes]) -> None:
        self.payloads = payloads

    def fetch_new_messages(self, source: MessageSource) -> int:
        return 0

    def download_attachment(self, source: MessageSource, message_id: str, part_index: int) -> tuple[bytes, str, str]:
        if part_index not in self.payloads:
            raise ValueError(f"附件不存在: part={part_index}")
        return self.payloads[part_index], f"court_{part_index}.pdf", "application/pdf"


def _make_source() -> MessageSource:
    return MessageSource.objects.create(
        source_type=SourceType.COURT_INBOX,
        display_name="一张网收件箱（测试）",
        credential=None,
        is_enabled=True,
        sync_since=timezone.now(),
    )


def _make_court_message(*, subject: str = "（20XX）粤0606执保XXXX号 - 告知书") -> InboxMessage:
    source = _make_source()
    return InboxMessage.objects.create(
        source=source,
        message_id="court-msg-1",
        subject=subject,
        sender="某某人民法院",
        received_at="2026-10-27T15:14:00+08:00",
        has_attachments=True,
        attachments_meta=[
            {
                "filename": "裁定书.pdf",
                "original_filename": "裁定书.pdf",
                "content_type": "application/pdf",
                "size": 13,
                "part_index": 0,
            },
            {
                "filename": "告知书.pdf",
                "original_filename": "告知书.pdf",
                "content_type": "application/pdf",
                "size": 12,
                "part_index": 1,
            },
        ],
    )


def _cleanup(*messages: InboxMessage) -> None:
    for msg in messages:
        for att in msg.attachments_meta or []:
            path = resolve_media_attachment_path(str(att.get("local_path", "")))
            if path is not None and path.exists():
                path.unlink()
        msg.delete()


@pytest.mark.django_db
def test_convert_copies_bytes_into_manual_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    msg = _make_court_message()
    monkeypatch.setattr(
        "apps.message_hub.services.get_fetcher",
        lambda _t: _StubFetcher({0: b"%PDF-1.4 first", 1: b"%PDF-1.4 second"}),
    )

    pack = convert_to_material_pack(msg)

    try:
        assert pack.pk != msg.pk
        assert pack.source.source_type == SourceType.MANUAL_UPLOAD
        assert pack.attachments_meta and len(pack.attachments_meta) == 2
        # 标题沿用原消息主题，拆分线索（案号 + 文书名）不丢
        assert pack.subject == msg.subject
        assert pack.draft_state == {}
        for att in pack.attachments_meta:
            path = resolve_media_attachment_path(str(att.get("local_path", "")))
            assert path is not None and path.exists(), att.get("local_path")
            assert att["local_path"].startswith("message_hub/manual/")
        # 字节内容与来源一致（搬的是文件，不是改名引用）
        content, _, _ = get_fetcher(SourceType.MANUAL_UPLOAD).download_attachment(pack.source, pack.message_id, 0)
        assert content == b"%PDF-1.4 first"

        msg.refresh_from_db()
        assert msg.converted_message_id == pack.pk
        # 原消息本身没被改动归属
        assert msg.source.source_type == SourceType.COURT_INBOX
    finally:
        _cleanup(pack, msg)


@pytest.mark.django_db
def test_convert_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    msg = _make_court_message()
    stub = _StubFetcher({0: b"%PDF-1.4 first", 1: b"%PDF-1.4 second"})
    downloads = {"n": 0}
    original_download = stub.download_attachment

    def _counting_download(source: MessageSource, message_id: str, part_index: int) -> tuple[bytes, str, str]:
        downloads["n"] += 1
        return original_download(source, message_id, part_index)

    stub.download_attachment = _counting_download  # type: ignore[method-assign]
    monkeypatch.setattr("apps.message_hub.services.get_fetcher", lambda _t: stub)

    first = convert_to_material_pack(msg)
    after_first = downloads["n"]
    second = convert_to_material_pack(InboxMessage.objects.get(pk=msg.pk))

    try:
        assert first.pk == second.pk
        assert after_first == 2  # 首次搬运两个附件各一次
        assert downloads["n"] == after_first  # 第二次一步下载都没发生
        assert InboxMessage.objects.filter(source__source_type=SourceType.MANUAL_UPLOAD).count() == 1
    finally:
        _cleanup(first, msg)


@pytest.mark.django_db
def test_convert_rejects_message_without_attachments() -> None:
    msg = _make_court_message()
    msg.has_attachments = False
    msg.attachments_meta = []
    msg.save(update_fields=["has_attachments", "attachments_meta"])

    try:
        with pytest.raises(ValidationException) as exc:
            convert_to_material_pack(msg)
        assert exc.value.code == "NO_ATTACHMENTS"
    finally:
        _cleanup(msg)


@pytest.mark.django_db
def test_convert_rejects_already_material_pack() -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    pack = create_manual_message(
        [SimpleUploadedFile("POA.pdf", b"%PDF-1.4 x", content_type="application/pdf")],
        subject="已是材料包",
    )
    try:
        with pytest.raises(ValidationException) as exc:
            convert_to_material_pack(pack)
        assert exc.value.code == "ALREADY_MATERIAL_PACK"
    finally:
        _cleanup(pack)


@pytest.mark.django_db
def test_convert_skips_failed_attachment_but_keeps_others(monkeypatch: pytest.MonkeyPatch) -> None:
    """一张网历史附件过期是现场常态：一份取不到不该让整次转换失败。"""
    msg = _make_court_message()
    monkeypatch.setattr(
        "apps.message_hub.services.get_fetcher",
        lambda _t: _StubFetcher({0: b"%PDF-1.4 first"}),  # part_index=1 故意缺失
    )

    pack = convert_to_material_pack(msg)

    try:
        assert len(pack.attachments_meta) == 1
        assert pack.attachments_meta[0]["original_filename"] == "court_0.pdf"
    finally:
        _cleanup(pack, msg)


@pytest.mark.django_db
def test_convert_fails_when_every_attachment_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    msg = _make_court_message()
    monkeypatch.setattr(
        "apps.message_hub.services.get_fetcher",
        lambda _t: _StubFetcher({}),
    )

    try:
        with pytest.raises(ValidationException) as exc:
            convert_to_material_pack(msg)
        assert exc.value.code == "ATTACHMENTS_UNAVAILABLE"
        # 失败不能留下半成品材料包
        assert InboxMessage.objects.filter(source__source_type=SourceType.MANUAL_UPLOAD).count() == 0
    finally:
        _cleanup(msg)
