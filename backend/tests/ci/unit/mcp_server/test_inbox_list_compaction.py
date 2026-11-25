"""`list_inbox_messages` 的行投影（纯逻辑，mock REST，不打网络也不碰数据库）。

为什么值得单测：列表接口从 v27.25 起每行带**附件元信息**，那是模型判断
「这封邮件有什么材料」的依据，但原始元信息一条约 200 字节——不收敛的话
默认调用会撞上 pi 对工具输出的 20KB 腰斩线，模型拿到的是半截 JSON。
这里钉三件事：

1. 附件被压成「名字 + 页数」，最多 3 份；
2. 超出部分给出 `attachments_truncated`（不能让模型以为材料只有 3 份）；
3. 没有附件的行把空 `attachments` 整个去掉（空数组在 20KB 预算里也不是零成本）。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from mcp_server.tools.message_hub import inbox
from mcp_server.tools.message_hub.inbox import MAX_ATTACHMENTS_PER_ROW, _compact_row


def _att(index: int, name: str, pages: int | None = 3) -> dict[str, Any]:
    """一份「后端原样」的附件元信息（8 个字段全在，含要丢掉的内部/冗余字段）。"""
    return {
        "filename": name,
        "original_filename": name,
        "custom_filename": None,
        "size": 1024,
        "content_type": "application/pdf",
        "part_index": index,
        "page_count": pages,
        "expanded_from": None,
    }


def _row(items: list[dict[str, Any]], **over: Any) -> dict[str, Any]:
    return {
        "id": 1,
        "subject": "（20XX）粤0606执保XXXX号 - 告知书",
        "attachment_count": len(items),
        "attachments": items,
        **over,
    }


class TestCompactRow:
    def test_keeps_name_and_pages_only(self) -> None:
        out = _compact_row(_row([_att(0, "起诉状.pdf"), _att(1, "证据清单.pdf", pages=None)]))
        assert out["attachments"] == [
            {"filename": "起诉状.pdf", "pages": 3},
            {"filename": "证据清单.pdf", "pages": 0},
        ]
        # 冗余字段一律不留给模型（content_type / part_index / size 都能从详情拿）
        assert set(out["attachments"][0]) == {"filename", "pages"}

    def test_custom_filename_wins(self) -> None:
        att = _att(0, "1153_001.pdf")
        att["custom_filename"] = "1-起诉状（某某案）V4_20261106.pdf"
        out = _compact_row(_row([att]))
        assert out["attachments"][0]["filename"] == "1-起诉状（某某案）V4_20261106.pdf"

    def test_caps_at_three_and_reports_remainder(self) -> None:
        items = [_att(i, f"{i}.pdf") for i in range(6)]
        out = _compact_row(_row(items))
        assert len(out["attachments"]) == MAX_ATTACHMENTS_PER_ROW
        # 模型必须知道还有几份没列出来，否则会当成「这份材料只有 3 个附件」
        assert out["attachments_truncated"] == 6 - MAX_ATTACHMENTS_PER_ROW
        # 计数仍以后端为准，不被投影改写
        assert out["attachment_count"] == 6

    def test_no_attachments_key_is_dropped(self) -> None:
        assert "attachments" not in _compact_row(_row([]))
        assert "attachments" not in _compact_row({"id": 2})

    def test_other_fields_pass_through(self) -> None:
        out = _compact_row(_row([_att(0, "a.pdf")], is_read=False, converted_message_id=None))
        assert out["subject"].startswith("（20XX）")
        assert out["is_read"] is False


class TestListToolEnvelope:
    def test_default_call_stays_inside_tool_output_budget(self) -> None:
        """默认 20 条 × 每条 6 份附件：投影后仍要明显低于 20KB 截断线。"""
        default_limit = inbox.list_inbox_messages.__defaults__[3]  # limit 默认值
        # 模拟「还有更多」：REST 按 limit+1 取，拿到 limit+1 条即知可翻页
        rows = [
            _row([_att(i, f"某某人民法院送达文书{i}.pdf") for i in range(6)], id=n) for n in range(default_limit + 1)
        ]
        with patch.object(inbox.client, "get", return_value=rows) as mock_get:
            out = inbox.list_inbox_messages()

        assert mock_get.call_args.kwargs["params"]["limit"] == default_limit + 1
        assert out["truncated"] is True
        assert out["returned"] == default_limit
        payload = json.dumps(out, ensure_ascii=False)
        assert len(payload.encode("utf-8")) < 20 * 1024
        # 投影真的生效：每行只剩 3 个附件
        assert all(len(item["attachments"]) == 3 for item in out["items"])
