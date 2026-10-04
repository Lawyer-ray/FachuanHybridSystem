"""PdfSplitService._extract_layout_title 全分支覆盖。

纯静态方法：构造 Paddle 解析器风格的 layout dict，锁标题识别/
过滤/坐标优先级契约（材料命名与边界提示依赖该函数）。
"""

from __future__ import annotations

from apps.pdf_splitting.services.split.service import PdfSplitService

_extract = PdfSplitService._extract_layout_title


class TestExtractLayoutTitle:
    def test_none_and_empty_layout_returns_empty(self) -> None:
        assert _extract(None) == ""
        assert _extract({}) == ""
        assert _extract({"blocks": "not-a-list"}) == ""
        assert _extract({"blocks": []}) == ""

    def test_title_type_block_wins(self) -> None:
        layout = {"blocks": [{"type": "title", "text": "借款合同", "bbox": [0, 100, 0, 0]}]}
        assert _extract(layout) == "借款合同"

    def test_text_level_treated_as_title(self) -> None:
        layout = {"blocks": [{"type": "text", "text_level": 1, "text": "第一章 总则", "bbox": [0, 50, 0, 0]}]}
        assert _extract(layout) == "第一章 总则"

    def test_zero_string_text_level_not_title(self) -> None:
        layout = {"blocks": [{"type": "text", "text_level": "0", "text": "正文内容", "bbox": [0, 50, 0, 0]}]}
        assert _extract(layout) == ""

    def test_plain_text_block_ignored(self) -> None:
        layout = {"blocks": [{"type": "text", "text": "普通正文段落不作为标题", "bbox": [0, 10, 0, 0]}]}
        assert _extract(layout) == ""

    def test_oversize_title_ignored(self) -> None:
        long_text = "长" * 49
        layout = {"blocks": [{"type": "title", "text": long_text, "bbox": [0, 10, 0, 0]}]}
        assert _extract(layout) == ""

    def test_topmost_title_selected_among_candidates(self) -> None:
        """多个标题候选时按 bbox 顶坐标 y 最小者优先（页面上方的标题）。"""
        layout = {
            "blocks": [
                {"type": "title", "text": "下面的标题", "bbox": [0, 300, 0, 0]},
                {"type": "heading", "text": "页首标题", "bbox": [0, 20, 0, 0]},
            ]
        }
        assert _extract(layout) == "页首标题"

    def test_same_y_longer_text_wins(self) -> None:
        """y 相同时取更长文本（排序键 -len，升序=长度降序）——信息量更大的标题优先。"""
        layout = {
            "blocks": [
                {"type": "title", "text": "短标题", "bbox": [0, 20, 0, 0]},
                {"type": "title", "text": "较长的标题文本内容", "bbox": [0, 20, 0, 0]},
            ]
        }
        assert _extract(layout) == "较长的标题文本内容"

    def test_text_whitespace_collapsed_inner_hash_kept(self) -> None:
        """split() 归一空白；strip 只去首尾的空白/#，串内的 ## 保留。"""
        layout = {"blocks": [{"type": "标题", "text": "  起诉状 ## \n副本 ", "bbox": [0, 5, 0, 0]}]}
        assert _extract(layout) == "起诉状 ## 副本"

    def test_malformed_blocks_skipped(self) -> None:
        layout = {
            "blocks": [
                "not-a-dict",
                {"type": "title", "text": None, "bbox": None},  # 无文本
                {"type": "title", "text": "有效标题", "bbox": [0, 1, 0, 0]},
            ]
        }
        assert _extract(layout) == "有效标题"

    def test_bad_bbox_falls_back_to_zero_y(self) -> None:
        """bbox 非法时 y 兜底 0.0——与 y=0 的合法标题并列，按 -len 决胜取更长文本。"""
        layout = {
            "blocks": [
                {"type": "title", "text": "合法坐标标题", "bbox": ["x", "bad", 0, 0]},
                {"type": "title", "text": "零坐标标题", "bbox": [0, 0, 0, 0]},
            ]
        }
        assert _extract(layout) == "合法坐标标题"

    def test_bbox_short_array_ignored(self) -> None:
        layout = {"blocks": [{"type": "title", "text": "缺坐标标题", "bbox": [0, 1]}]}
        assert _extract(layout) == "缺坐标标题"
