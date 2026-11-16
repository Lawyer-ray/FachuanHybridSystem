"""get_material_draft_segments 纯逻辑测试（mock REST，不打网络、不碰数据库）。

钉死三件事：
1. 目录模式只投影起草需要的字段（md 本体不进目录，防 20KB 截断）；
2. 单段模式 md 窗口可续读，next_md_offset 按实际送达字符推进（含字节兜底）；
3. 权限/鉴权完全继承 get_inbox_message 的 REST 路径（passthrough 身份）。
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from mcp_server.tools.message_hub import inbox


def _seg(i: int, *, md: str = "", refs: list | None = None) -> dict:
    return {
        "id": f"seg-{i}",
        "t": "借款合同",
        "fn": f"材料{i}",
        "refs": refs if refs is not None else [{"mi": 0, "p": i + 1}],
        "md": md,
        "qualityFlags": ["疑似错字"] if i % 2 else [],
        "reviewFlag": "normal",
        "confidence": 0.9,
        "manualEdit": {"md": True} if i % 2 else {},
        "blocks": [{"text": "大字段不应进投影"}],
    }


def _call(segs: list, **kwargs):
    msg = {"id": 579, "draft_state": {"segs": segs}}
    with patch.object(inbox.client, "get", return_value=msg) as mock_get:
        out = inbox.get_material_draft_segments(579, **kwargs)
    mock_get.assert_called_once_with("/inbox/messages/579")
    return out


class TestDirectoryMode:
    def test_projection_fields_and_no_md_body(self) -> None:
        out = _call([_seg(0, md="正文" * 100), _seg(1)])
        assert out["total_segs"] == 2
        assert out["truncated"] is False
        item = out["items"][0]
        assert item["segment_index"] == 0
        assert item["id"] == "seg-0"
        assert item["name"] == "材料0"
        assert item["type"] == "借款合同"
        assert item["pages"] == [{"part_index": 0, "page_start": 1, "page_end": 1}]
        assert item["md_chars"] == 200
        assert item["manual_edit"] is False
        assert "md" not in item
        assert "blocks" not in item

    def test_pages_grouped_by_source_attachment(self) -> None:
        seg = _seg(0, refs=[{"mi": 1, "p": 5}, {"mi": 0, "p": 2}, {"mi": 1, "p": 3}, {"mi": 0, "p": 1}])
        out = _call([seg])
        assert out["items"][0]["pages"] == [
            {"part_index": 0, "page_start": 1, "page_end": 2},
            {"part_index": 1, "page_start": 3, "page_end": 5},
        ]

    def test_pagination_offset_limit(self) -> None:
        out = _call([_seg(i) for i in range(7)], offset=5, limit=5)
        assert out["total_segs"] == 7
        assert out["returned"] == 2
        assert out["truncated"] is False
        assert [it["segment_index"] for it in out["items"]] == [5, 6]

    def test_truncated_flag_when_more_segs(self) -> None:
        out = _call([_seg(i) for i in range(6)], offset=0, limit=5)
        assert out["truncated"] is True
        assert out["returned"] == 5

    def test_empty_draft_is_explicit(self) -> None:
        out = _call([])
        assert out["total_segs"] == 0
        assert out["items"] == []

    def test_missing_draft_state_treated_as_empty(self) -> None:
        with patch.object(inbox.client, "get", return_value={"id": 579}):
            out = inbox.get_material_draft_segments(579)
        assert out["total_segs"] == 0

    def test_directory_response_within_byte_budget(self) -> None:
        out = _call([_seg(i) for i in range(20)], limit=20)
        assert len(json.dumps(out, ensure_ascii=False).encode("utf-8")) < 19_000


class TestSingleSegmentMode:
    def test_short_md_returned_in_full(self) -> None:
        out = _call([_seg(0, md="# 标题\n正文")], segment_index=0)
        seg = out["segment"]
        assert seg["md"] == "# 标题\n正文"
        assert seg["name"] == "材料0"
        assert out["md_total_chars"] == 7
        assert out["md_truncated"] is False
        assert out["next_md_offset"] is None

    def test_long_md_window_and_continuation(self) -> None:
        md = "字" * 12000  # 36000 字节，远超单窗口
        first = _call([_seg(0, md=md)], segment_index=0)
        assert first["md_truncated"] is True
        assert first["md_total_chars"] == 12000
        delivered = len(first["segment"]["md"])
        assert 0 < delivered < 12000
        assert first["next_md_offset"] == delivered
        # 字节预算：md 本体 UTF-8 不超 16000，整包 JSON 留在 pi 截断线内
        assert len(first["segment"]["md"].encode("utf-8")) <= 16_000
        assert len(json.dumps(first, ensure_ascii=False).encode("utf-8")) < 19_000

        # 逐窗续读能拼回全文（无跳字、无重复）
        assembled = first["segment"]["md"]
        cursor = first["next_md_offset"]
        while cursor is not None:
            page = _call([_seg(0, md=md)], segment_index=0, md_offset=cursor)
            assembled += page["segment"]["md"]
            cursor = page["next_md_offset"]
        assert assembled == md

    def test_ascii_md_char_window(self) -> None:
        md = "a" * 12000  # 单字节字符：6000 字符窗口不触发字节兜底
        out = _call([_seg(0, md=md)], segment_index=0)
        assert len(out["segment"]["md"]) == 6000
        assert out["next_md_offset"] == 6000

    def test_md_offset_past_end_returns_empty_not_error(self) -> None:
        out = _call([_seg(0, md="短正文")], segment_index=0, md_offset=999)
        assert out["segment"]["md"] == ""
        assert out["md_truncated"] is False
        assert out["next_md_offset"] is None

    def test_segment_index_out_of_range_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="越界"):
            _call([_seg(0)], segment_index=5)

    def test_segment_without_md(self) -> None:
        out = _call([_seg(0)], segment_index=0)
        assert out["segment"]["md"] == ""
        assert out["md_total_chars"] == 0
        assert out["md_truncated"] is False
