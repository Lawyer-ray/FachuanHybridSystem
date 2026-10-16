"""Tests for pdf_splitting 分段 Markdown 重建与 job_service 的 content_md 透出。"""

from __future__ import annotations

import json
from typing import Any

from apps.pdf_splitting.services.job_service import load_segments_md
from apps.pdf_splitting.services.split.markdown_builder import (
    _html_table_to_markdown,
    build_segment_markdown,
    build_segments_markdown,
)
from apps.pdf_splitting.services.split.split_models import PageDescriptor, SegmentDraft


def _page(page_no: int, text: str = "", *, layout: dict[str, Any] | None = None, ocr_failed: bool = False) -> PageDescriptor:
    return PageDescriptor(
        page_no=page_no,
        text=text,
        normalized_text=text,
        head_text=text[:240],
        source_method="ocr",
        ocr_failed=ocr_failed,
        top_candidates=[],
        layout=layout,
        layout_title="",
    )


class TestBuildSegmentMarkdown:
    def test_版面块重建标题段落与表格(self) -> None:
        layout = {
            "blocks": [
                {"type": "title", "text": "证据清单"},
                {"type": "text", "text_level": 1, "text": "一、借款合同"},
                {"type": "text", "text": "证明借贷关系成立。"},
                {
                    "type": "table",
                    "text": "交易日期 金额",
                    "table_body": "<table><tr><td>交易日期</td><td>金额</td></tr><tr><td>2024-01-01</td><td>100,000</td></tr></table>",
                },
                {"type": "header", "text": "页眉噪音"},
                {"type": "image", "text": ""},
            ]
        }
        md = build_segment_markdown("证据清单及明细", [_page(1, layout=layout)])
        lines = md.splitlines()
        assert lines[0] == "# 证据清单及明细"
        assert "## 证据清单" in lines
        assert "## 一、借款合同" in lines  # text_level=1 → 段内标题 H2
        assert "证明借贷关系成立。" in lines
        assert "| 交易日期 | 金额 |" in lines
        assert "| --- | --- |" in lines
        assert "| 2024-01-01 | 100,000 |" in lines
        assert "页眉噪音" not in md

    def test_text_level_逐级映射且钳位(self) -> None:
        layout = {"blocks": [{"type": "text", "text_level": 3, "text": "三级"}]}
        assert "#### 三级" in build_segment_markdown("t", [_page(1, layout=layout)])
        deep = {"blocks": [{"type": "text", "text_level": 9, "text": "太深"}]}
        assert "###### 太深" in build_segment_markdown("t", [_page(1, layout=deep)])

    def test_无版面时退回页原文_页间空行(self) -> None:
        md = build_segment_markdown("起诉状", [_page(1, "原告张三。"), _page(2, "此致\n人民法院")])
        assert md == "# 起诉状\n\n原告张三。\n\n此致\n人民法院\n"

    def test_表格解析失败退回块文本(self) -> None:
        layout = {"blocks": [{"type": "table", "text": "交易明细 甲 乙", "table_body": "<div>not a table</div>"}]}
        assert "交易明细 甲 乙" in build_segment_markdown("t", [_page(1, layout=layout)])
        assert "|" not in build_segment_markdown("t", [_page(1, layout=layout)])

    def test_单元格竖线转义与短行补齐(self) -> None:
        table = _html_table_to_markdown(
            "<table><tr><td>类型</td><td>备注</td></tr><tr><td>借|条</td></tr></table>"
        )
        lines = table.splitlines()
        assert lines[0] == "| 类型 | 备注 |"
        assert lines[2] == "| 借\\|条 |  |"  # 缺列补空、| 转义


class TestBuildSegmentsMarkdown:
    def test_按drafts生成_标题取文件名stem_含gap段(self) -> None:
        pages = [_page(1, "起诉状正文"), _page(2, "身份证复印件"), _page(3, "证据正文")]
        drafts = [
            SegmentDraft(
                order=1, page_start=1, page_end=1, segment_type="complaint",
                filename="起诉状.pdf", confidence=0.9, source_method="llm", review_flag="normal",
            ),
            SegmentDraft(
                order=2, page_start=2, page_end=2, segment_type="unrecognized",
                filename="未识别材料_2-2.pdf", confidence=0.0, source_method="gap_fill", review_flag="unrecognized",
            ),
            SegmentDraft(
                order=3, page_start=3, page_end=3, segment_type="evidence_list",
                filename="证据清单.pdf", confidence=0.8, source_method="llm", review_flag="normal",
            ),
        ]
        results = build_segments_markdown(drafts, pages)
        assert [r["order"] for r in results] == [1, 2, 3]
        assert results[0]["markdown"].startswith("# 起诉状\n")
        assert results[1]["markdown"].startswith("# 未识别材料_2-2\n")
        assert results[2]["page_start"] == 3 and results[2]["page_end"] == 3


class TestLoadSegmentsMd:
    def test_缺失文件回空表(self, tmp_path: Any) -> None:
        assert load_segments_md(tmp_path / "segments_md.json") == {}

    def test_正常读取按order建映射(self, tmp_path: Any) -> None:
        path = tmp_path / "segments_md.json"
        path.write_text(
            json.dumps([{"order": 1, "markdown": "# a"}, {"order": 2, "markdown": "# b"}], ensure_ascii=False),
            encoding="utf-8",
        )
        assert load_segments_md(path) == {1: "# a", 2: "# b"}

    def test_损坏或非列表载荷回空表(self, tmp_path: Any) -> None:
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        assert load_segments_md(broken) == {}
        non_list = tmp_path / "non_list.json"
        non_list.write_text('{"order": 1}', encoding="utf-8")
        assert load_segments_md(non_list) == {}
