"""块级结构构建测试：类型归一、layout 提取、能力位探测、可信度语义。"""

from __future__ import annotations

from typing import Any

from apps.document_parsing.protocols.document_parser_protocol import (
    BLOCK_TYPE_FOOTER,
    BLOCK_TYPE_FORMULA,
    BLOCK_TYPE_HEADER,
    BLOCK_TYPE_IMAGE,
    BLOCK_TYPE_TABLE,
    BLOCK_TYPE_TEXT,
    BLOCK_TYPE_TITLE,
    BLOCK_TYPE_UNKNOWN,
    ParsedBlock,
    ParsedDocument,
    normalize_block_type,
)
from apps.document_parsing.services.block_builder import (
    attach_blocks,
    block_to_dict,
    blocks_summary,
    build_blocks_from_layout,
    build_blocks_from_lines,
    detect_coverage,
    layout_page_count,
)


class TestNormalizeBlockType:
    """后端原始类型必须归一到架构层词汇，否则下游要认识每家后端的方言。"""

    def test_textin_types(self) -> None:
        assert normalize_block_type("NarrativeText") == BLOCK_TYPE_TEXT
        assert normalize_block_type("Title") == BLOCK_TYPE_TITLE

    def test_mineru_types(self) -> None:
        assert normalize_block_type("text") == BLOCK_TYPE_TEXT
        assert normalize_block_type("interline_equation") == BLOCK_TYPE_FORMULA
        assert normalize_block_type("image") == BLOCK_TYPE_IMAGE

    def test_header_footer(self) -> None:
        assert normalize_block_type("Header") == BLOCK_TYPE_HEADER
        assert normalize_block_type("Footer") == BLOCK_TYPE_FOOTER
        assert normalize_block_type("page_number") == BLOCK_TYPE_FOOTER

    def test_case_and_whitespace_insensitive(self) -> None:
        assert normalize_block_type("  TABLE  ") == BLOCK_TYPE_TABLE

    def test_unknown_kept_not_dropped(self) -> None:
        """未知类型保留为 unknown，不能返回 None——凭空消失的块无法排查。"""
        assert normalize_block_type("weird_new_type") == BLOCK_TYPE_UNKNOWN
        assert normalize_block_type(None) == BLOCK_TYPE_UNKNOWN
        assert normalize_block_type("") == BLOCK_TYPE_UNKNOWN


class TestParsedBlock:
    def test_defaults(self) -> None:
        block = ParsedBlock()
        assert block.type == BLOCK_TYPE_TEXT
        assert block.text == ""
        assert block.bbox is None
        assert block.page_no is None
        assert block.confidence is None
        assert block.needs_review is False
        assert block.review_reason == ""

    def test_confidence_none_means_unevaluated_not_zero(self) -> None:
        """None（未评估）与 0.0（评估为错）必须可区分，这是复核处置的前提。"""
        evaluated_bad = ParsedBlock(text="x", confidence=0.0)
        not_evaluated = ParsedBlock(text="x", confidence=None)
        assert evaluated_bad.confidence == 0.0
        assert not_evaluated.confidence is None
        assert evaluated_bad.confidence is not not_evaluated.confidence

    def test_is_body_excludes_header_footer(self) -> None:
        assert ParsedBlock(type=BLOCK_TYPE_TEXT).is_body() is True
        assert ParsedBlock(type=BLOCK_TYPE_TABLE).is_body() is True
        assert ParsedBlock(type=BLOCK_TYPE_HEADER).is_body() is False
        assert ParsedBlock(type=BLOCK_TYPE_FOOTER).is_body() is False


class TestBuildBlocksFromLayout:
    def _layout(self) -> dict[str, Any]:
        return {
            "page_count": 2,
            "pages": [
                {
                    "page_no": 1,
                    "width": 1000,
                    "height": 1400,
                    "blocks": [
                        {"type": "Title", "text": " 第一条  ", "bbox": [1, 2, 3, 4]},
                        {"type": "NarrativeText", "text": "甲方向乙方采购"},
                    ],
                    "text": "第一条 甲方向乙方采购",
                },
                {
                    "page_no": 2,
                    "width": 1000,
                    "height": 1400,
                    "blocks": [{"type": "Footer", "text": "第 2 页"}],
                    "text": "",
                },
            ],
        }

    def test_flattens_in_page_order(self) -> None:
        blocks = build_blocks_from_layout(self._layout())
        assert [b.text for b in blocks] == ["第一条", "甲方向乙方采购", "第 2 页"]
        assert [b.page_no for b in blocks] == [1, 1, 2]
        assert blocks[0].type == BLOCK_TYPE_TITLE
        assert blocks[2].type == BLOCK_TYPE_FOOTER

    def test_preserves_bbox_verbatim(self) -> None:
        """坐标系不统一，构建阶段不得换算——换错就再也对不上原图。"""
        blocks = build_blocks_from_layout(self._layout())
        assert blocks[0].bbox == [1, 2, 3, 4]
        assert blocks[1].bbox is None

    def test_confidence_stays_none(self) -> None:
        for block in build_blocks_from_layout(self._layout()):
            assert block.confidence is None

    def test_bad_pages_skipped(self) -> None:
        """块结构是增强信息，畸形 page 不该让整次解析失败。"""
        layout = {"pages": ["not-a-dict", {"page_no": "bad", "blocks": [{"type": "text", "text": "ok"}]}]}
        blocks = build_blocks_from_layout(layout)
        assert len(blocks) == 1
        assert blocks[0].page_no is None

    def test_non_dict_layout_returns_empty(self) -> None:
        assert build_blocks_from_layout(None) == []
        assert build_blocks_from_layout("nope") == []
        assert build_blocks_from_layout({"pages": "nope"}) == []


class TestBuildBlocksFromLines:
    def test_splits_and_strips(self) -> None:
        blocks = build_blocks_from_lines(["  行一  ", "", "   ", "行二"], page_no=3)
        assert [b.text for b in blocks] == ["行一", "行二"]
        assert all(b.type == BLOCK_TYPE_TEXT for b in blocks)
        assert all(b.page_no == 3 for b in blocks)

    def test_non_str_ignored(self) -> None:
        blocks = build_blocks_from_lines(["ok", None, 123])  # type: ignore[list-item]
        assert [b.text for b in blocks] == ["ok"]


class TestDetectCoverage:
    def test_no_blocks(self) -> None:
        cov = detect_coverage(None, None)
        assert cov.has_blocks is False
        assert cov.has_bbox is False
        assert cov.can_attach_confidence() is False

    def test_single_block_not_enough(self) -> None:
        """1 个块可能是巧合（整页只有一行标题），不足以宣称块结构可用。"""
        blocks = [ParsedBlock(text="只有一行", bbox=[0, 0, 1, 1])]
        cov = detect_coverage(blocks, None)
        assert cov.has_blocks is False

    def test_blocks_with_bbox(self) -> None:
        blocks = [
            ParsedBlock(text="a", bbox=[0, 0, 1, 1]),
            ParsedBlock(text="b", bbox=[0, 1, 1, 2]),
        ]
        cov = detect_coverage(blocks, None)
        assert cov.has_blocks is True
        assert cov.has_bbox is True
        assert cov.can_attach_confidence() is True

    def test_blocks_without_bbox_cannot_attach(self) -> None:
        """无坐标就没法从原图裁切送判定模型——这是 Jev 类外挂的前置条件。"""
        blocks = [ParsedBlock(text="a"), ParsedBlock(text="b")]
        cov = detect_coverage(blocks, None)
        assert cov.has_blocks is True
        assert cov.has_bbox is False
        assert cov.can_attach_confidence() is False

    def test_page_geometry(self) -> None:
        layout = {"page_count": 3, "pages": [{"page_no": 1, "width": 100, "height": 200}]}
        blocks = [ParsedBlock(text="a"), ParsedBlock(text="b")]
        assert detect_coverage(blocks, layout).has_page_geometry is True
        assert detect_coverage(blocks, {"pages": [{"page_no": 1}]}).has_page_geometry is False

    def test_image_only_blocks_still_count(self) -> None:
        """整幅插图页没有文本是正常的，不该据此判定块结构失效。"""
        blocks = [ParsedBlock(type=BLOCK_TYPE_IMAGE), ParsedBlock(type=BLOCK_TYPE_IMAGE)]
        assert detect_coverage(blocks, None).has_blocks is True


class TestAttachBlocks:
    def test_uses_layout(self) -> None:
        doc = ParsedDocument(
            text="甲方向乙方采购",
            parse_method="textin",
            layout={"pages": [{"page_no": 1, "blocks": [{"type": "NarrativeText", "text": "甲方向乙方采购"}]}]},
        )
        attach_blocks(doc)
        assert doc.blocks is not None
        assert len(doc.blocks) == 1
        assert doc.coverage.has_blocks is False  # 单块未达下限

    def test_line_fallback_only_when_allowed(self) -> None:
        """云端后端拿不到 layout 说明本次返回异常，用文本行冒充块会掩盖问题。"""
        cloud = ParsedDocument(text="行一\n行二\n行三", parse_method="mineru")
        attach_blocks(cloud)
        assert cloud.blocks == []
        assert cloud.coverage.has_blocks is False

        local = ParsedDocument(text="行一\n行二\n行三", parse_method="pymupdf")
        attach_blocks(local, allow_line_fallback=True)
        assert local.blocks is not None
        assert len(local.blocks) == 3
        assert local.coverage.has_blocks is True
        assert local.coverage.has_bbox is False
        assert local.coverage.can_attach_confidence() is False


class TestSummaryAndSerialization:
    def test_summary(self) -> None:
        assert blocks_summary(None) == {"block_count": 0, "block_types": {}, "review_needed": 0}
        blocks = [
            ParsedBlock(type=BLOCK_TYPE_TEXT),
            ParsedBlock(type=BLOCK_TYPE_TEXT, needs_review=True),
            ParsedBlock(type=BLOCK_TYPE_TABLE),
        ]
        summary = blocks_summary(blocks)
        assert summary["block_count"] == 3
        assert summary["block_types"] == {"text": 2, "table": 1}
        assert summary["review_needed"] == 1

    def test_block_to_dict_keeps_none_confidence(self) -> None:
        """None 必须原样透出，不能被压成 0——前端据此区分「未评估」和「判错」。"""
        assert block_to_dict(ParsedBlock(text="x"))["confidence"] is None
        assert block_to_dict(ParsedBlock(text="x", confidence=0.0))["confidence"] == 0.0

    def test_block_to_dict_fields(self) -> None:
        d = block_to_dict(
            ParsedBlock(type=BLOCK_TYPE_TABLE, text="|a|", bbox=[1, 2, 3, 4], page_no=2, review_reason="低于阈值")
        )
        assert d == {
            "type": "table",
            "text": "|a|",
            "bbox": [1, 2, 3, 4],
            "page_no": 2,
            "confidence": None,
            "needs_review": False,
            "review_reason": "低于阈值",
        }

    def test_layout_page_count(self) -> None:
        assert layout_page_count(None) == 0
        assert layout_page_count({"page_count": 5, "pages": []}) == 5
        assert layout_page_count({"pages": [{"page_no": 1}, {"page_no": 2}]}) == 2
