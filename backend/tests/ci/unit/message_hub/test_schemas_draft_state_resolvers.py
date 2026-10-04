"""message_hub/schemas.py draft_state resolver 群纯逻辑测试.

用 SimpleNamespace 构造 draft dict / attachments_meta，逐行校验
7 个 resolver 对 JSONB 的读取语义（缺键、空值、类型混杂容错）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any


def _obj(draft_state: Any = None, attachments_meta: Any = None, **extra: Any) -> SimpleNamespace:
    return SimpleNamespace(
        draft_state=draft_state if draft_state is not None else {},
        attachments_meta=attachments_meta if attachments_meta is not None else [],
        **extra,
    )


class TestResolveStatus:
    def test_reads_status_from_draft(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_status(_obj({"status": "done"})) == "done"
        assert InboxMessageOut.resolve_status(_obj({"status": "filed"})) == "filed"

    def test_defaults_to_todo(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_status(_obj({})) == "todo"

    def test_unknown_status_falls_back_to_todo(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_status(_obj({"status": "weird"})) == "todo"
        assert InboxMessageOut.resolve_status(_obj({"status": ""})) == "todo"

    def test_non_string_status_coerced(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_status(_obj({"status": 123})) == "todo"  # 非法值回退


class TestResolveSegs:
    def test_counts_segs(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj({"segs": [{"t": "借条"}, {}, {"t": ""}]})
        assert InboxMessageOut.resolve_segs(obj) == 3

    def test_missing_or_none(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_segs(_obj({})) == 0
        assert InboxMessageOut.resolve_segs(_obj({"segs": None})) == 0


class TestResolveNamed:
    def test_counts_only_named_segs(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj({"segs": [{"t": "合同"}, {"t": "   "}, {"t": None}, {}]})
        assert InboxMessageOut.resolve_named(obj) == 1

    def test_empty(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_named(_obj({})) == 0


class TestResolvePages:
    def test_sums_mat_pages(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj({"mats": [{"pages": 3}, {"pages": "4"}, {"pages": 0}, {}]})
        assert InboxMessageOut.resolve_pages(obj) == 7

    def test_missing(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_pages(_obj({})) == 0


class TestResolveMats:
    def test_draft_mats_preferred(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj({"mats": [{"k": "photo"}]}, attachments_meta=[{"x": 1}, {"x": 2}])
        assert InboxMessageOut.resolve_mats(obj) == 1

    def test_falls_back_to_attachments(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj({}, attachments_meta=[{"x": 1}, {"x": 2}, {"x": 3}])
        assert InboxMessageOut.resolve_mats(obj) == 3

    def test_nothing(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_mats(_obj()) == 0


class TestResolveTypes:
    def test_unique_in_order(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj({"segs": [{"t": "借条"}, {"t": "借条"}, {"t": "合同"}, {"t": ""}, {}]})
        assert InboxMessageOut.resolve_types(obj) == ["借条", "合同"]

    def test_caps_at_three_unique(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj({"segs": [{"t": t} for t in ["a", "b", "c", "d"]]})
        assert InboxMessageOut.resolve_types(obj) == ["a", "b", "c"]

    def test_empty(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_types(_obj({})) == []


class TestResolveCompose:
    def test_draft_mats_grouped_by_kind(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj({"mats": [{"k": "photo"}, {"k": "photo"}, {"k": "office"}]})
        assert InboxMessageOut.resolve_compose(obj) == "2 个图片 · 1 个文档"

    def test_draft_mats_missing_k_defaults_office(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj({"mats": [{}]})
        assert InboxMessageOut.resolve_compose(obj) == "1 个文档"

    def test_no_mats_groups_attachments_by_content_type(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj(
            attachments_meta=[
                {"content_type": "application/pdf"},
                {"content_type": "image/jpeg"},
                {"content_type": None},
            ]
        )
        # 图片 / 文档分别计数
        compose = InboxMessageOut.resolve_compose(obj)
        assert "1 个图片" in compose
        assert "2 个文档" in compose

    def test_no_mats_no_attachments(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_compose(_obj()) == ""

    def test_kind_label_mapping(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut._kind_label("image/png") == "图片"
        assert InboxMessageOut._kind_label("application/pdf") == "文档"
        assert InboxMessageOut._kind_label("application/vnd.ms-excel") == "文档"
        assert InboxMessageOut._kind_label(None) == "文档"
        assert InboxMessageOut._kind_label("") == "文档"


class TestSourceResolvers:
    def _source_obj(self) -> SimpleNamespace:
        from datetime import timezone

        return _obj(
            source=SimpleNamespace(
                display_name="法院短信",
                source_type="court",
                credential=SimpleNamespace(account="cred@x.com"),
            ),
            received_at=datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC),
            created_at=datetime(2026, 3, 4, 5, 6, 8, tzinfo=UTC),
            uploaded_by_id=None,
            uploaded_by=None,
        )

    def test_source_name_and_type(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = self._source_obj()
        assert InboxMessageOut.resolve_source_name(obj) == "法院短信"
        assert InboxMessageOut.resolve_source_type(obj) == "court"

    def test_recipient_from_credential(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_recipient(self._source_obj()) == "cred@x.com"

    def test_recipient_empty_without_credential(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = _obj(source=SimpleNamespace(display_name="d", source_type="t", credential=None))
        assert InboxMessageOut.resolve_recipient(obj) == ""

    def test_uploaded_by_none(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_uploaded_by_id(self._source_obj()) is None
        assert InboxMessageOut.resolve_uploaded_by_name(self._source_obj()) == ""

    def test_uploaded_by_named(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = SimpleNamespace(uploaded_by_id=9, uploaded_by=SimpleNamespace(real_name="张律师", username="zhang"))
        assert InboxMessageOut.resolve_uploaded_by_id(obj) == 9
        assert InboxMessageOut.resolve_uploaded_by_name(obj) == "张律师"

    def test_uploaded_by_falls_back_to_username(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        obj = SimpleNamespace(uploaded_by_id=0, uploaded_by=SimpleNamespace(real_name="", username="zhang"))
        assert InboxMessageOut.resolve_uploaded_by_id(obj) is None  # 0 → None
        assert InboxMessageOut.resolve_uploaded_by_name(obj) == "zhang"

    def test_datetime_iso(self) -> None:
        from django.utils import timezone as dj_tz

        from apps.message_hub.schemas import InboxMessageOut

        obj = self._source_obj()
        # _resolve_datetime_iso 转本地时区（运行环境为 +08:00）
        assert InboxMessageOut.resolve_received_at(obj) == dj_tz.localtime(obj.received_at).isoformat()
        assert InboxMessageOut.resolve_created_at(obj) == dj_tz.localtime(obj.created_at).isoformat()

    def test_attachment_count(self) -> None:
        from apps.message_hub.schemas import InboxMessageOut

        assert InboxMessageOut.resolve_attachment_count(_obj(attachments_meta=[{}, {}])) == 2


class TestDetailOutResolvers:
    def test_draft_state_passthrough(self) -> None:
        from apps.message_hub.schemas import InboxMessageDetailOut

        draft = {"segs": [{"t": "x"}]}
        assert InboxMessageDetailOut.resolve_draft_state(_obj(draft)) == draft

    def test_draft_state_none_becomes_empty(self) -> None:
        from apps.message_hub.schemas import InboxMessageDetailOut

        obj = SimpleNamespace(draft_state=None)
        assert InboxMessageDetailOut.resolve_draft_state(obj) == {}

    def test_attachments_public_meta(self) -> None:
        from apps.message_hub.schemas import InboxMessageDetailOut

        obj = SimpleNamespace(get_public_attachments_meta=lambda: [{"filename": "a.pdf"}])
        assert InboxMessageDetailOut.resolve_attachments(obj) == [{"filename": "a.pdf"}]


class TestSimpleSchemas:
    def test_message_ack_out(self) -> None:
        from apps.message_hub.schemas import MessageAckOut

        out = MessageAckOut(ok=True, message_id=3)
        assert out.ok is True
        assert out.message_id == 3

    def test_message_rename_out(self) -> None:
        from apps.message_hub.schemas import MessageRenameOut

        out = MessageRenameOut(ok=True, message_id=3, subject="新名称")
        assert out.subject == "新名称"

    def test_attachment_meta_defaults(self) -> None:
        from apps.message_hub.schemas import AttachmentMeta

        meta = AttachmentMeta(filename="a.pdf", size=10, content_type="application/pdf", part_index=0)
        assert meta.page_count is None
        assert meta.original_filename is None
        assert meta.custom_filename is None
