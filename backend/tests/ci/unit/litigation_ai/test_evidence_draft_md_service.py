"""预处理 md → chunk 切分与适配的纯逻辑测试（mock，不碰数据库）。

钉死：
1. split_md 按段落边界切到 ≤1500 字，超长单段硬切，内容不丢；
2. chunks_from_draft_segments 首块带段页区间、续块 page_start=None（避唯一约束）；
3. 适配器无哈希/异常时降级为空（走原抽文本路径），不阻断起草。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.cases.services.material.material_draft_md_service import DraftSegmentMd
from apps.litigation_ai.services.evidence.evidence_draft_md_service import (
    MD_CHUNK_CHARS,
    EvidenceDraftMdService,
    chunks_from_draft_segments,
    split_md,
)


def _seg(md: str, *, start: int | None = 1, end: int | None = 3, ref: str = "s1") -> DraftSegmentMd:
    return DraftSegmentMd(segment_ref=ref, name="借款合同", page_start=start, page_end=end, md=md)


class TestSplitMd:
    def test_short_md_single_chunk(self) -> None:
        assert split_md("# 标题\n\n正文一段") == ["# 标题\n\n正文一段"]

    def test_empty_and_whitespace(self) -> None:
        assert split_md("") == []
        assert split_md("\n\n  \n\n") == []

    def test_paragraph_boundary_split(self) -> None:
        para = "字" * 800
        md = f"{para}\n\n{para}\n\n{para}"  # 3×800，拼接超 1500
        chunks = split_md(md)
        assert len(chunks) >= 2
        assert all(len(c) <= MD_CHUNK_CHARS for c in chunks)
        # 段落边界切分可无损拼回
        assert "\n\n".join(chunks) == md

    def test_giant_single_paragraph_hard_split(self) -> None:
        md = "x" * (MD_CHUNK_CHARS * 2 + 100)  # 无段落边界的怪兽行
        chunks = split_md(md)
        assert all(len(c) <= MD_CHUNK_CHARS for c in chunks)
        assert "".join(chunks) == md

    def test_each_chunk_within_limit(self) -> None:
        md = "\n\n".join(f"第{i}段 " + "内容" * 200 for i in range(20))
        assert all(len(c) <= MD_CHUNK_CHARS for c in split_md(md))


class TestChunksFromDraftSegments:
    def test_short_seg_single_chunk_with_pages(self) -> None:
        chunks = chunks_from_draft_segments([_seg("短正文", start=5, end=7)])
        assert len(chunks) == 1
        assert chunks[0]["page_start"] == 5
        assert chunks[0]["page_end"] == 7
        assert chunks[0]["text"] == "短正文"
        assert chunks[0]["extraction_method"] == "preprocessed_md"

    def test_long_seg_continuation_chunks_have_null_page(self) -> None:
        md = "\n\n".join("段" * 800 for _ in range(4))
        chunks = chunks_from_draft_segments([_seg(md, start=10, end=12)])
        assert len(chunks) > 1
        assert chunks[0]["page_start"] == 10
        assert chunks[0]["page_end"] == 12
        for c in chunks[1:]:
            assert c["page_start"] is None
            assert c["page_end"] is None

    def test_two_segs_distinct_first_page(self) -> None:
        chunks = chunks_from_draft_segments([_seg("甲", start=1, end=1, ref="a"), _seg("乙", start=2, end=2, ref="b")])
        first_pages = [c["page_start"] for c in chunks if c["page_start"] is not None]
        assert first_pages == [1, 2]  # 同证据下起始页互异，不撞唯一约束

    def test_seg_without_pages(self) -> None:
        chunks = chunks_from_draft_segments([_seg("无页码", start=None, end=None)])
        assert chunks[0]["page_start"] is None


class TestFindDraftSegmentsAdapter:
    def _patch_item(self, *, file_hash: str, case_id: int | None):
        item = SimpleNamespace(file_hash=file_hash, evidence_list=SimpleNamespace(case_id=case_id))
        ev = MagicMock()
        ev.query_service.get_evidence_item.return_value = item
        return patch("apps.litigation_ai.services.wiring.get_evidence_service", return_value=ev)

    def test_resolves_hash_and_case_then_queries_cases_service(self) -> None:
        segs = [_seg("正文")]
        fake_cases = MagicMock()
        fake_cases.return_value.find_draft_segments_for_file.return_value = segs
        with (
            self._patch_item(file_hash="abc", case_id=7),
            patch(
                "apps.cases.services.material.material_draft_md_service.MaterialDraftMdService",
                fake_cases,
            ),
        ):
            out = EvidenceDraftMdService().find_draft_segments(42)
        assert out == segs
        fake_cases.return_value.find_draft_segments_for_file.assert_called_once_with(7, "abc")

    def test_empty_hash_short_circuits(self) -> None:
        with self._patch_item(file_hash="", case_id=7):
            assert EvidenceDraftMdService().find_draft_segments(42) == []

    def test_no_case_short_circuits(self) -> None:
        with self._patch_item(file_hash="abc", case_id=None):
            assert EvidenceDraftMdService().find_draft_segments(42) == []

    def test_exception_degrades_to_empty(self) -> None:
        ev = MagicMock()
        ev.query_service.get_evidence_item.side_effect = RuntimeError("boom")
        with patch("apps.litigation_ai.services.wiring.get_evidence_service", return_value=ev):
            assert EvidenceDraftMdService().find_draft_segments(42) == []
