"""收件箱消息 → 法院短信流程桥接测试。

覆盖的硬约束（每一条都是现场会踩的）：
1. 附件必须**复制**到 automation 上传目录，原 ``local_path`` 原地保留
   （短信链路的 ``DocumentRenamer`` 是原地改名，引用原路径会把收件箱附件弄丢）；
2. 本地文件已从磁盘消失时走 fetcher 重新取字节（一张网链接过期是常态）；
3. 三级幂等：同消息 / 跨来源同 message_id / 内容去重键，命中即返回既有记录；
4. 案号必须抽进 ``case_numbers``（否则 ``CaseMatcher`` 只剩当事人匹配）；
5. 自动通道只在 ``auto_sms_since`` 之后、单轮 50 条、单条失败不中断。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.automation.models import CourtSMS
from apps.core.exceptions import ValidationException
from apps.message_hub.models import InboxMessage, MessageSource, SourceType
from apps.message_hub.services import inbox_sms_bridge
from apps.message_hub.services.base import resolve_media_attachment_path


@pytest.fixture
def media_root(tmp_path: Path) -> Iterator[Path]:
    """隔离的 MEDIA_ROOT（复制落盘与原始文件都写在这里，不碰真实 media）。"""
    media = tmp_path / "media"
    media.mkdir()
    with override_settings(MEDIA_ROOT=str(media)):
        yield media


@pytest.fixture
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int, str]]:
    """记录提交出的异步任务（``(target, sms_id, task_name)``），不入真实队列。"""
    calls: list[tuple[str, int, str]] = []

    def _submit_task(target: str, *pos_args: Any, task_name: str = "", **_kwargs: Any) -> str:
        calls.append((target, int(pos_args[0]), task_name))
        return "fake-task-id"

    monkeypatch.setattr(inbox_sms_bridge, "submit_task", _submit_task)
    return calls


class _StubFetcher:
    """冒充外部来源 fetcher：按 part_index 返回固定字节（不碰真实 IMAP / 一张网）。"""

    def __init__(self, payloads: dict[int, bytes] | None = None, *, failing_ids: set[str] | None = None) -> None:
        self.payloads = payloads if payloads is not None else {}
        self.failing_ids = failing_ids or set()
        self.calls: list[tuple[str, int]] = []

    def fetch_new_messages(self, source: MessageSource, *, window_days: int | None = None) -> int:
        return 0

    def download_attachment(self, source: MessageSource, message_id: str, part_index: int) -> tuple[bytes, str, str]:
        self.calls.append((message_id, part_index))
        if message_id in self.failing_ids:
            raise ValueError(f"附件无下载链接: message_id={message_id}")
        payload = self.payloads.get(part_index, b"%PDF-1.4 stub")
        return payload, f"court_{part_index}.pdf", "application/pdf"


class _LocalPathFetcher:
    """按 ``attachments_meta[].local_path`` 读字节（与一张网 fetcher 的「本地命中」分支同构）。"""

    def __init__(self, local_paths: dict[int, str]) -> None:
        self.local_paths = local_paths
        self.calls: list[tuple[str, int]] = []

    def fetch_new_messages(self, source: MessageSource, *, window_days: int | None = None) -> int:
        return 0

    def download_attachment(self, source: MessageSource, message_id: str, part_index: int) -> tuple[bytes, str, str]:
        self.calls.append((message_id, part_index))
        resolved = resolve_media_attachment_path(self.local_paths[part_index])
        if resolved is None:
            raise ValueError(f"本地文件不存在: part_index={part_index}")
        return resolved.read_bytes(), resolved.name, "application/pdf"


# ---------------------------------------------------------------------------
# 构造数据
# ---------------------------------------------------------------------------


def _make_source(
    *,
    source_type: str = SourceType.COURT_INBOX,
    display_name: str = "一张网收件箱（测试）",
    auto_sms_since: datetime | None = None,
) -> MessageSource:
    return MessageSource.objects.create(
        source_type=source_type,
        display_name=display_name,
        is_enabled=True,
        sync_since=timezone.now(),
        auto_sms_since=auto_sms_since,
    )


def _attachments_meta(
    part_indexes: tuple[int, ...] = (0,), *, local_paths: dict[int, str] | None = None
) -> list[dict[str, Any]]:
    metas: list[dict[str, Any]] = []
    for index in part_indexes:
        meta: dict[str, Any] = {
            "filename": f"文书_{index}.pdf",
            "original_filename": f"文书_{index}.pdf",
            "content_type": "application/pdf",
            "size": 13,
            "part_index": index,
        }
        if local_paths and index in local_paths:
            meta["local_path"] = local_paths[index]
        metas.append(meta)
    return metas


def _make_message(
    source: MessageSource,
    *,
    message_id: str = "sdbh-1",
    subject: str = "（1999）粤06民终90001号 - 99-00001示例借款合同纠纷",
    body_text: str = "请查收文书。",
    received_at: datetime | None = None,
    has_attachments: bool = True,
    attachments_meta: list[dict[str, Any]] | None = None,
) -> InboxMessage:
    return InboxMessage.objects.create(
        source=source,
        message_id=message_id,
        subject=subject,
        sender="某某人民法院",
        received_at=received_at or timezone.now(),
        body_text=body_text,
        has_attachments=has_attachments,
        attachments_meta=attachments_meta if attachments_meta is not None else _attachments_meta(),
    )


@pytest.fixture
def use_fetcher(monkeypatch: pytest.MonkeyPatch) -> Any:
    """把来源 fetcher 换成替身（真实插件未装在测试环境，且不希望触网）。"""

    def _install(fetcher: Any) -> Any:
        monkeypatch.setattr("apps.message_hub.services.get_fetcher", lambda _source_type: fetcher)
        return fetcher

    return _install


# ---------------------------------------------------------------------------
# 门槛：来源 / 附件
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_rejects_message_without_attachments(media_root: Path, use_fetcher: Any) -> None:
    use_fetcher(_StubFetcher({0: b"%PDF-1.4 x"}))
    msg = _make_message(_make_source(), has_attachments=False, attachments_meta=[])

    with pytest.raises(ValidationException) as exc:
        inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    assert exc.value.code == "NO_ATTACHMENTS"
    assert CourtSMS.objects.count() == 0


@pytest.mark.django_db
def test_submit_rejects_unsupported_source_type(media_root: Path, use_fetcher: Any) -> None:
    use_fetcher(_StubFetcher({0: b"%PDF-1.4 x"}))
    msg = _make_message(_make_source(source_type=SourceType.MANUAL_UPLOAD, display_name="材料包"))

    with pytest.raises(ValidationException) as exc:
        inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    assert exc.value.code == "SOURCE_NOT_SUPPORTED"


@pytest.mark.django_db
def test_submit_raises_when_every_attachment_unavailable(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    use_fetcher(_StubFetcher({}, failing_ids={"sdbh-1"}))
    msg = _make_message(_make_source())

    with pytest.raises(ValidationException) as exc:
        inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    assert exc.value.code == "ATTACHMENTS_UNAVAILABLE"
    assert CourtSMS.objects.count() == 0
    assert dispatched == []


# ---------------------------------------------------------------------------
# 附件复制（原地改名的回归点）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_copies_attachment_and_keeps_original_local_path(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    source = _make_source()
    original = media_root / "message_hub" / "court_inbox" / "sdbh-1" / "裁定书.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"%PDF-1.4 original")
    local_path = str(original.relative_to(media_root))

    msg = _make_message(
        source,
        subject="（1999）粤06民终90001号 - 99-00001示例借款合同纠纷",
        attachments_meta=_attachments_meta(local_paths={0: local_path}),
    )
    fetcher = use_fetcher(_LocalPathFetcher({0: local_path}))

    result = inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    try:
        assert result.created is True
        assert result.attachment_count == 1
        assert result.skipped == []

        copied = Path(result.sms.document_file_paths[0])
        # 落盘是**副本**：新路径在 automation/uploads 下，且与原路径不同
        assert copied.is_absolute()
        assert copied.exists()
        assert copied != original
        assert copied.is_relative_to(media_root / "automation" / "uploads")
        assert copied.read_bytes() == b"%PDF-1.4 original"
        # 回归点：原 local_path 仍然存在且内容不变（否则收件箱预览/转包会 404）
        assert original.exists()
        assert original.read_bytes() == b"%PDF-1.4 original"
        # 收件箱那边一条 meta 都不该被改写
        msg.refresh_from_db()
        assert msg.attachments_meta[0]["local_path"] == local_path
        assert fetcher.calls == [("sdbh-1", 0)]
        assert dispatched == [
            (
                "apps.automation.workers.court_sms_tasks.process_sms_from_matching",
                result.sms.pk,
                f"court_sms_from_inbox_{msg.pk}",
            )
        ]
    finally:
        for path in result.sms.document_file_paths:
            Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_submit_refetches_when_local_attachment_is_gone(media_root: Path, use_fetcher: Any) -> None:
    """本地文件已从磁盘消失（一张网过期链接是常态）→ 走 fetcher 重新取字节。"""
    source = _make_source()
    missing_local_path = "message_hub/court_inbox/sdbh-2/已删除文书.pdf"
    assert resolve_media_attachment_path(missing_local_path) is None

    msg = _make_message(
        source,
        message_id="sdbh-2",
        attachments_meta=_attachments_meta(local_paths={0: missing_local_path}),
    )
    fetcher = use_fetcher(_StubFetcher({0: b"%PDF-1.4 refetched"}))

    result = inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    try:
        assert fetcher.calls == [("sdbh-2", 0)]
        copied = Path(result.sms.document_file_paths[0])
        assert copied.exists()
        assert copied.read_bytes() == b"%PDF-1.4 refetched"
        assert str(copied) != missing_local_path
    finally:
        for path in result.sms.document_file_paths:
            Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_submit_skips_one_bad_attachment_but_keeps_the_others(media_root: Path, use_fetcher: Any) -> None:
    source = _make_source()
    msg = _make_message(source, message_id="sdbh-3", attachments_meta=_attachments_meta((0, 1)))

    class _PartialFetcher(_StubFetcher):
        def download_attachment(
            self, source: MessageSource, message_id: str, part_index: int
        ) -> tuple[bytes, str, str]:
            if part_index == 1:
                raise ValueError("附件无下载链接")
            return super().download_attachment(source, message_id, part_index)

    use_fetcher(_PartialFetcher({0: b"%PDF-1.4 first"}))

    result = inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    try:
        assert result.created is True
        assert result.attachment_count == 1
        assert [item["name"] for item in result.skipped] == ["文书_1.pdf"]
        assert "附件无下载链接" in result.skipped[0]["reason"]
    finally:
        for path in result.sms.document_file_paths:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 幂等三级
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_is_idempotent_for_the_same_message(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    msg = _make_message(_make_source())
    fetcher = use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    service = inbox_sms_bridge.InboxSmsBridgeService()

    first = service.submit(msg)
    second = service.submit(InboxMessage.objects.get(pk=msg.pk))

    try:
        assert first.created is True
        assert second.created is False
        assert second.sms.pk == first.sms.pk
        assert CourtSMS.objects.count() == 1
        assert len(dispatched) == 1  # 第二次没有再派任务
        assert fetcher.calls == [("sdbh-1", 0)]  # 也没有再搬一次字节
    finally:
        for path in first.sms.document_file_paths:
            Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_submit_dedups_same_message_id_across_sources(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    """同一条 sdbh 出现在另一个来源里（例如换了收件箱来源）只处理一次。"""
    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    court_source = _make_source(display_name="一张网收件箱 A")
    imap_source = _make_source(source_type=SourceType.IMAP, display_name="法院邮箱")

    first = inbox_sms_bridge.InboxSmsBridgeService().submit(_make_message(court_source, message_id="sdbh-shared"))
    second = inbox_sms_bridge.InboxSmsBridgeService().submit(
        _make_message(imap_source, message_id="sdbh-shared", subject="同一份送达")
    )

    try:
        assert first.created is True
        assert second.created is False
        assert second.sms.pk == first.sms.pk
        assert CourtSMS.objects.count() == 1
        assert len(dispatched) == 1
    finally:
        for path in first.sms.document_file_paths:
            Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_submit_reuses_sms_found_by_delivery_event_key(media_root: Path, use_fetcher: Any) -> None:
    """兼容历史 admin 桥 / 手工提交：内容与接收时间都相同的记录不重复建。"""
    from apps.automation.services.sms.court_sms_delivery_dedup import build_delivery_event_key

    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    source = _make_source(display_name="一张网收件箱（测试）")
    received_at = timezone.now()
    msg = _make_message(source, message_id="sdbh-legacy", received_at=received_at)
    content = f"[来自收件箱][{source.display_name}]\n{msg.body_text}"
    legacy = CourtSMS.objects.create(
        content=content,
        received_at=received_at,
        delivery_event_key=build_delivery_event_key(content, received_at),
    )

    result = inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    assert result.created is False
    assert result.sms.pk == legacy.pk
    assert CourtSMS.objects.count() == 1


@pytest.mark.django_db
def test_submit_reuses_sms_created_by_the_old_admin_button(media_root: Path, use_fetcher: Any) -> None:
    """升级前用 Admin「提交到短信处理」建过的记录，升级后再点不能变成第二条。

    老记录的正文口径是 ``[来自收件箱] {subject}\\n发件人: …\\n消息ID: …``，且既无
    ``inbox_message_id`` 也无 ``delivery_event_id``，只能靠内容去重键命中。
    """
    from apps.automation.services.sms.court_sms_delivery_dedup import build_delivery_event_key

    use_fetcher(_StubFetcher({0: b"%PDF-1.4 legacy"}))
    source = _make_source(display_name="一张网收件箱（老按钮）")
    received_at = timezone.now()
    msg = _make_message(source, message_id="sdbh-admin-1", received_at=received_at)
    legacy_content = f"[来自收件箱] {msg.subject}\n发件人: {msg.sender}\n消息ID: {msg.message_id}"
    legacy = CourtSMS.objects.create(
        content=legacy_content,
        received_at=received_at,
        delivery_event_key=build_delivery_event_key(legacy_content, received_at),
    )

    result = inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    assert result.created is False
    assert result.sms.pk == legacy.pk
    assert CourtSMS.objects.count() == 1


@pytest.mark.django_db
def test_submit_uses_stable_hash_when_message_id_exceeds_field_width(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    """IMAP 的 Message-ID 可到 512，超过 ``delivery_event_id`` 的 128 只能存摘要。

    直接截断会让两条不同消息撞成同键、把真消息当重复跳过，所以必须是摘要。
    """
    from apps.message_hub.services.inbox_sms_bridge import DELIVERY_EVENT_ID_MAX_LENGTH

    use_fetcher(_StubFetcher({0: b"%PDF-1.4 long"}))
    source = _make_source(source_type=SourceType.IMAP, display_name="法院邮箱")
    long_id = "<" + "a" * (DELIVERY_EVENT_ID_MAX_LENGTH + 40) + "@court.gov.cn>"
    msg = _make_message(source, message_id=long_id)

    result = inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    try:
        assert result.created is True
        stored = result.sms.delivery_event_id or ""
        assert stored.startswith("sha1:")
        assert len(stored) <= DELIVERY_EVENT_ID_MAX_LENGTH
        # 同一条消息再提交仍然认得出来（跨轮次稳定）
        assert inbox_sms_bridge.InboxSmsBridgeService().submit(msg).created is False
        assert CourtSMS.objects.count() == 1
    finally:
        for path in result.sms.document_file_paths:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 建记录的字段口径
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_extracts_case_number_and_fills_traceability_fields(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    source = _make_source(display_name="一张网收件箱（测试）")
    msg = _make_message(
        source,
        subject="（1999）粤06民终90001号 - 99-00001示例借款合同纠纷",
        body_text="请查收文书。",
    )

    result = inbox_sms_bridge.InboxSmsBridgeService().submit(msg)

    try:
        sms = result.sms
        assert "（1999）粤06民终90001号" in sms.case_numbers
        # 派任务前必须已是 MATCHING（process_sms_from_matching 的入口状态）
        assert sms.status == "matching"
        assert sms.delivery_event_id == msg.message_id
        assert sms.inbox_message_id == msg.pk
        assert sms.delivery_event_key
        assert sms.received_at == msg.received_at
        # content 带来源与正文（归档 markdown 需要可读正文）
        assert f"[来自收件箱][{source.display_name}]" in sms.content
        assert "请查收文书。" in sms.content
    finally:
        for path in result.sms.document_file_paths:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# HTTP 端点（薄壳：形状 + 404 口径）
# ---------------------------------------------------------------------------


def _admin_request() -> Any:
    return SimpleNamespace(user=SimpleNamespace(id=1, is_authenticated=True, is_superuser=True))


@pytest.mark.django_db
def test_submit_to_sms_endpoint_returns_contract_shape(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    from apps.message_hub.api.inbox_api import submit_message_to_sms

    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    msg = _make_message(_make_source(), message_id="sdbh-api")

    payload = submit_message_to_sms(_admin_request(), msg.pk)

    try:
        assert payload["success"] is True
        assert payload["created"] is True
        assert payload["sms_id"] == CourtSMS.objects.get().pk
        assert payload["attachment_count"] == 1
        assert payload["skipped"] == []

        # 再点一次：200 + 既有 sms_id + created=false（前端靠它区分 toast 文案）
        repeat = submit_message_to_sms(_admin_request(), msg.pk)
        assert repeat["created"] is False
        assert repeat["sms_id"] == payload["sms_id"]
    finally:
        for sms in CourtSMS.objects.all():
            for path in sms.document_file_paths:
                Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_submit_to_sms_endpoint_returns_404_for_missing_message(media_root: Path) -> None:
    from apps.core.exceptions import NotFoundError
    from apps.message_hub.api.inbox_api import submit_message_to_sms

    with pytest.raises(NotFoundError):
        submit_message_to_sms(_admin_request(), 999_999)


# ---------------------------------------------------------------------------
# 自动通道
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_auto_submit_does_nothing_when_auto_since_is_empty(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    source = _make_source(auto_sms_since=None)
    _make_message(source, message_id="sdbh-auto-off")

    stats = inbox_sms_bridge.auto_submit_for_source(source)

    assert stats == {"examined": 0, "submitted": 0, "skipped": 0}
    assert CourtSMS.objects.count() == 0
    assert dispatched == []


@pytest.mark.django_db
def test_auto_submit_includes_messages_exactly_at_auto_since(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    """边界：``received_at == auto_sms_since`` 要提交，早于它一秒的不提交。"""
    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    since = timezone.now() - timedelta(hours=1)
    source = _make_source(auto_sms_since=since)
    _make_message(source, message_id="sdbh-too-old", received_at=since - timedelta(seconds=1))
    _make_message(source, message_id="sdbh-at-boundary", received_at=since)

    stats = inbox_sms_bridge.auto_submit_for_source(source)

    try:
        assert stats == {"examined": 1, "submitted": 1, "skipped": 0}
        assert [sms.delivery_event_id for sms in CourtSMS.objects.all()] == ["sdbh-at-boundary"]
    finally:
        for sms in CourtSMS.objects.all():
            for path in sms.document_file_paths:
                Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_auto_submit_skips_messages_already_in_sms_flow(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    since = timezone.now() - timedelta(hours=1)
    source = _make_source(auto_sms_since=since)
    # 两条正文必须不同：内容去重键（10 分钟桶 + content）同级时会先命中「历史重复」，
    # 那样测到的就不是「已提交过的消息被排除」这一条了。
    handled = _make_message(
        source, message_id="sdbh-handled", body_text="文书甲", received_at=since + timedelta(minutes=1)
    )
    inbox_sms_bridge.InboxSmsBridgeService().submit(handled)
    _make_message(source, message_id="sdbh-new", body_text="文书乙", received_at=since + timedelta(minutes=2))

    stats = inbox_sms_bridge.auto_submit_for_source(source)

    try:
        assert stats["examined"] == 1
        assert stats["submitted"] == 1
        assert CourtSMS.objects.count() == 2
    finally:
        for sms in CourtSMS.objects.all():
            for path in sms.document_file_paths:
                Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_auto_submit_caps_one_round_at_batch_limit(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    since = timezone.now() - timedelta(hours=1)
    source = _make_source(auto_sms_since=since)
    total = inbox_sms_bridge.AUTO_SUBMIT_BATCH_LIMIT + 2
    for index in range(total):
        _make_message(
            source,
            message_id=f"sdbh-{index:03d}",
            body_text=f"请查收文书 {index}。",
            received_at=since + timedelta(seconds=index),
        )

    stats = inbox_sms_bridge.auto_submit_for_source(source)

    try:
        assert stats == {"examined": 50, "submitted": 50, "skipped": 0}
        assert CourtSMS.objects.count() == 50
        # 按收到时间升序取，最早的一条必须在
        assert CourtSMS.objects.filter(delivery_event_id="sdbh-000").exists()
    finally:
        for sms in CourtSMS.objects.all():
            for path in sms.document_file_paths:
                Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_auto_submit_continues_after_a_single_failure(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}, failing_ids={"sdbh-bad"}))
    since = timezone.now() - timedelta(hours=1)
    source = _make_source(auto_sms_since=since)
    _make_message(source, message_id="sdbh-good-1", body_text="文书一", received_at=since + timedelta(minutes=1))
    _make_message(source, message_id="sdbh-bad", body_text="文书二", received_at=since + timedelta(minutes=2))
    _make_message(source, message_id="sdbh-good-2", body_text="文书三", received_at=since + timedelta(minutes=3))

    stats = inbox_sms_bridge.auto_submit_for_source(source)

    try:
        assert stats == {"examined": 3, "submitted": 2, "skipped": 1}
        # 失败一条不回滚已提交的两条
        assert sorted(str(event_id) for event_id in CourtSMS.objects.values_list("delivery_event_id", flat=True)) == [
            "sdbh-good-1",
            "sdbh-good-2",
        ]
        assert len(dispatched) == 2
    finally:
        for sms in CourtSMS.objects.all():
            for path in sms.document_file_paths:
                Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Admin 薄壳（行为保持：成功 / 重复 / 失败三种 messages + 跳转不变）
# ---------------------------------------------------------------------------


def _admin_request_with_messages() -> Any:
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    # FallbackStorage 只要求 `session` 可赋值（这里用不到 session 兜底），
    # `_messages` 是 Django messages 中间件的挂载点，两者都不在 WSGIRequest 的类型里。
    request.session = "session"  # type: ignore[assignment]
    request._messages = FallbackStorage(request)  # type: ignore[attr-defined]
    return request


def _message_texts(request: Any) -> list[str]:
    from django.contrib.messages import get_messages

    return [str(message) for message in get_messages(request)]


@pytest.mark.django_db
def test_admin_submit_view_reports_success_and_redirects_to_sms(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    from django.contrib import admin as dj_admin
    from django.urls import reverse

    from apps.message_hub.admin.inbox_message_admin import InboxMessageAdmin

    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    msg = _make_message(_make_source(), message_id="sdbh-admin")
    view = InboxMessageAdmin(InboxMessage, dj_admin.site)
    request = _admin_request_with_messages()

    response = view._submit_to_sms_view(request, msg.pk)

    try:
        sms = CourtSMS.objects.get()
        assert response.url == reverse("admin:automation_courtsms_change", args=[sms.pk])
        assert _message_texts(request) == [f"已提交到短信处理（SMS #{sms.pk}），共 1 个附件，正在后台处理..."]
    finally:
        for record in CourtSMS.objects.all():
            for path in record.document_file_paths:
                Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_admin_submit_view_reports_duplicate_and_redirects_to_existing_sms(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    from django.contrib import admin as dj_admin
    from django.urls import reverse

    from apps.message_hub.admin.inbox_message_admin import InboxMessageAdmin

    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    msg = _make_message(_make_source(), message_id="sdbh-admin-dup")
    view = InboxMessageAdmin(InboxMessage, dj_admin.site)
    view._submit_to_sms_view(_admin_request_with_messages(), msg.pk)

    request = _admin_request_with_messages()
    response = view._submit_to_sms_view(request, msg.pk)

    try:
        sms = CourtSMS.objects.get()
        assert response.url == reverse("admin:automation_courtsms_change", args=[sms.pk])
        assert _message_texts(request) == [f"该消息已提交过短信处理（SMS #{sms.pk}），已跳过重复提交"]
    finally:
        for record in CourtSMS.objects.all():
            for path in record.document_file_paths:
                Path(path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_admin_submit_view_reports_missing_attachments_without_creating_sms(
    media_root: Path, use_fetcher: Any, dispatched: list[tuple[str, int, str]]
) -> None:
    from django.contrib import admin as dj_admin
    from django.urls import reverse

    from apps.message_hub.admin.inbox_message_admin import InboxMessageAdmin

    use_fetcher(_StubFetcher({0: b"%PDF-1.4 first"}))
    msg = _make_message(_make_source(), message_id="sdbh-admin-empty", has_attachments=False, attachments_meta=[])
    view = InboxMessageAdmin(InboxMessage, dj_admin.site)
    request = _admin_request_with_messages()

    response = view._submit_to_sms_view(request, msg.pk)

    assert response.url == reverse("admin:message_hub_inboxmessage_change", args=[msg.pk])
    assert _message_texts(request) == ["该消息没有可处理的附件文件"]
    assert CourtSMS.objects.count() == 0
