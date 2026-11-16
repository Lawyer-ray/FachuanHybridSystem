"""Unit tests for pdf_splitting.services.job_service module."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException


class TestPdfSplitJobServiceNormalizeSplitMode:
    """测试 _normalize_split_mode"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_valid_mode(self) -> None:
        from apps.pdf_splitting.models import PdfSplitMode

        svc = self._make_service()
        assert svc._normalize_split_mode("content_analysis") == PdfSplitMode.CONTENT_ANALYSIS

    def test_empty_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitMode

        svc = self._make_service()
        assert svc._normalize_split_mode("") == PdfSplitMode.CONTENT_ANALYSIS

    def test_none_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitMode

        svc = self._make_service()
        assert svc._normalize_split_mode(None) == PdfSplitMode.CONTENT_ANALYSIS

    def test_invalid_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitMode

        svc = self._make_service()
        assert svc._normalize_split_mode("invalid") == PdfSplitMode.CONTENT_ANALYSIS


class TestPdfSplitJobServiceNormalizeOcrProfile:
    """测试 _normalize_ocr_profile"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_valid_profile(self) -> None:
        from apps.pdf_splitting.models import PdfSplitOcrProfile

        svc = self._make_service()
        assert svc._normalize_ocr_profile("balanced") == PdfSplitOcrProfile.BALANCED

    def test_empty_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitOcrProfile

        svc = self._make_service()
        assert svc._normalize_ocr_profile("") == PdfSplitOcrProfile.BALANCED

    def test_invalid_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitOcrProfile

        svc = self._make_service()
        assert svc._normalize_ocr_profile("invalid") == PdfSplitOcrProfile.BALANCED


class TestPdfSplitJobServiceIsAbsolutePath:
    """测试 _is_absolute_path"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_unix_absolute(self) -> None:
        svc = self._make_service()
        assert svc._is_absolute_path("/usr/local/bin") is True

    def test_windows_absolute(self) -> None:
        svc = self._make_service()
        assert svc._is_absolute_path("C:\\Users\\test") is True

    def test_relative(self) -> None:
        svc = self._make_service()
        assert svc._is_absolute_path("relative/path") is False

    def test_unc_path(self) -> None:
        svc = self._make_service()
        assert svc._is_absolute_path("\\\\server\\share") is True


class TestPdfSplitJobServiceValidateLocalPdfPath:
    """测试 _validate_local_pdf_path"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_empty_path_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._validate_local_pdf_path("")

    def test_smb_path_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._validate_local_pdf_path("smb://server/share")

    def test_relative_path_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._validate_local_pdf_path("relative/path.pdf")

    def test_nonexistent_path_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._validate_local_pdf_path("/nonexistent/path/file.pdf")


class TestPdfSplitJobServiceNormalizeConfirmedSegments:
    """测试 _normalize_confirmed_segments"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_empty_items_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=[], total_pages=10)

    def test_invalid_page_start_raises(self) -> None:
        svc = self._make_service()
        items = [{"page_start": "abc", "page_end": 5}]
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=items, total_pages=10)

    def test_page_range_invalid_raises(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 5, "page_end": 3}]
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=items, total_pages=10)

    def test_page_exceeds_total_raises(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 20}]
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=items, total_pages=10)

    def test_valid_segments(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 5, "segment_type": "evidence"}]
        result = svc._normalize_confirmed_segments(items=items, total_pages=10)
        assert len(result) >= 1
        assert result[0]["page_start"] == 1
        assert result[0]["page_end"] == 5

    def test_fills_gaps(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 3, "segment_type": "evidence"}]
        result = svc._normalize_confirmed_segments(items=items, total_pages=10)
        # Should have original + gap fill
        assert len(result) >= 2
        # Last segment should fill to page 10
        assert result[-1]["page_end"] == 10

    def test_overlap_raises(self) -> None:
        svc = self._make_service()
        items = [
            {"page_start": 1, "page_end": 5, "segment_type": "evidence"},
            {"page_start": 3, "page_end": 8, "segment_type": "evidence"},
        ]
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=items, total_pages=10)

    def test_default_filename_for_unrecognized(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 5}]
        result = svc._normalize_confirmed_segments(items=items, total_pages=5)
        assert "未识别材料" in result[0]["filename"]

    def test_pdf_extension_added(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 5, "segment_type": "evidence", "filename": "test"}]
        result = svc._normalize_confirmed_segments(items=items, total_pages=5)
        assert result[0]["filename"].endswith(".pdf")


# ── confirm 后重建 segments_md（P0-3）────────────────────────────────
#
# 存在理由：`confirm_segments` 按 1 基重排 DB 段，却曾经**只写 segments.json**，
# 而 md 产物是按旧 order（LLM 路径 0 基）存的。读取侧 `md_by_order.get(item.order)`
# 于是拿 1 基查 0 基字典 —— 每段拿到上一段的正文、末段拿空串，**用户什么都没改也错**。
#
# 只统一基址不够：律师合并/拆分/改页区间后，旧 md 与新页区间根本对不上。所以修法是
# 「按确认后的页区间从 pages.json 重建」，这里锁住的正是重建结果与段的一致性。
#
# 全部合成数据；不碰 DB / media（纯函数直打）。


def _page(page_no: int, text: str, *, layout: dict[str, Any] | None = None) -> dict[str, Any]:
    """pages.json 里的一条页记录（形状与 PageDescriptor 的 asdict 一致）。"""
    return {
        "page_no": page_no,
        "text": text,
        "normalized_text": "".join(text.split()),
        "head_text": text[:20],
        "source_method": "fast_text",
        "ocr_failed": False,
        "top_candidates": [],
        "layout": layout,
        "layout_title": "",
    }


def _pages(count: int = 6) -> list[dict[str, Any]]:
    return [_page(no, f"第{no}页正文") for no in range(1, count + 1)]


def _confirmed(items: list[dict[str, Any]], *, total_pages: int = 6) -> list[dict[str, Any]]:
    """走真实归一化（排序 + 补洞），而不是手搓 normalized——补洞段也要有正文。"""
    from apps.pdf_splitting.services.job_service import PdfSplitJobService

    return PdfSplitJobService()._normalize_confirmed_segments(items=items, total_pages=total_pages)


def _item(start: int, end: int, filename: str, *, segment_type: str = "evidence") -> dict[str, Any]:
    return {"page_start": start, "page_end": end, "segment_type": segment_type, "filename": filename}


def _assert_md_matches_range(entry: dict[str, Any], *, total_pages: int = 6) -> None:
    """一段正文必须**恰好**覆盖自己的页区间：区间内每页都在、区间外每页都不在。"""
    start, end = entry["page_start"], entry["page_end"]
    markdown = entry["markdown"]
    assert markdown.strip(), f"第 {start}-{end} 页这段正文为空"
    for no in range(1, total_pages + 1):
        if start <= no <= end:
            assert f"第{no}页正文" in markdown, f"段 {start}-{end} 缺第 {no} 页"
        else:
            assert f"第{no}页正文" not in markdown, f"段 {start}-{end} 混进了第 {no} 页"


class TestBuildConfirmedSegmentsMd:
    """重建结果必须与「用户确认后的段」逐段对齐。"""

    def test_什么都没改也不再有错位一格(self) -> None:
        """原自动分段是 0 基 order 的三段；直接确认必须逐段对上、末段非空。"""
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed(
            [_item(1, 2, "起诉状.pdf", segment_type="complaint"), _item(3, 4, "证据一.pdf"), _item(5, 6, "证据二.pdf")]
        )
        entries = build_confirmed_segments_md(normalized, _pages())

        assert [entry["order"] for entry in entries] == [1, 2, 3], "重建后 order 必须与 bulk_create 的 1 基一致"
        for entry, item in zip(entries, normalized, strict=True):
            assert (entry["page_start"], entry["page_end"]) == (item["page_start"], item["page_end"])
            _assert_md_matches_range(entry)
        assert entries[-1]["markdown"].strip(), "末段拿空串正是原 bug 的症状"

    def test_段标题跟着改名走(self) -> None:
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(1, 6, "律师改过的名字.pdf")])
        entries = build_confirmed_segments_md(normalized, _pages())

        assert entries[0]["markdown"].startswith("# 律师改过的名字\n")

    def test_合并两段后正文覆盖合并区间(self) -> None:
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(1, 4, "合并.pdf"), _item(5, 6, "尾段.pdf")])
        entries = build_confirmed_segments_md(normalized, _pages())

        assert len(entries) == 2
        for entry in entries:
            _assert_md_matches_range(entry)

    def test_拆分一段后两半各拿自己那几页(self) -> None:
        """原 [1-4] 一段被拆成 [1-2] / [3-4]：两半都不能照抄整段正文。"""
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(1, 2, "前半.pdf"), _item(3, 4, "后半.pdf"), _item(5, 6, "尾段.pdf")])
        entries = build_confirmed_segments_md(normalized, _pages())

        assert len(entries) == 3
        for entry in entries:
            _assert_md_matches_range(entry)

    def test_改页区间后正文跟着变(self) -> None:
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(2, 5, "挪过边界.pdf")])
        entries = build_confirmed_segments_md(normalized, _pages())

        # 头尾缺口被补成未识别段，它们同样要有正文（静默丢页是最坏的失败模式）
        assert [(e["page_start"], e["page_end"]) for e in entries] == [(1, 1), (2, 5), (6, 6)]
        for entry in entries:
            _assert_md_matches_range(entry)

    def test_输入乱序时按页序重排且正文不错位(self) -> None:
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(5, 6, "丙.pdf"), _item(1, 2, "甲.pdf"), _item(3, 4, "乙.pdf")])
        entries = build_confirmed_segments_md(normalized, _pages())

        assert [e["page_start"] for e in entries] == [1, 3, 5]
        assert entries[0]["markdown"].startswith("# 甲\n")
        for entry in entries:
            _assert_md_matches_range(entry)

    def test_实际平台决定坐标而不是auto(self) -> None:
        """bbox_backend 必须是取字落盘的实际平台：auto/空串换算不出坐标，positioned 恒空。"""
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        layout = {"blocks": [{"type": "text", "text": "第1页正文", "bbox": [100, 100, 500, 200]}]}
        pages = [_page(1, "第1页正文", layout=layout)]
        normalized = _confirmed([_item(1, 1, "有坐标.pdf")], total_pages=1)

        assert build_confirmed_segments_md(normalized, pages, bbox_backend="mineru")[0]["positioned"]
        assert build_confirmed_segments_md(normalized, pages, bbox_backend="auto")[0]["positioned"] == []
        assert build_confirmed_segments_md(normalized, pages)[0]["positioned"] == []

    def test_每段都带质量标记字段(self) -> None:
        """quality_flags 重算后仍要逐段存在（前端按段读它，缺键会 undefined）。"""
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        entries = build_confirmed_segments_md(_confirmed([_item(1, 6, "整本.pdf")]), _pages())
        assert isinstance(entries[0]["quality_flags"], list)

    def test_页锚点偏移按重建后的正文算(self) -> None:
        """锚点必须是对**新** md 字符串量出来的：拿旧偏移切新正文就是错位。"""
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(1, 2, "甲.pdf"), _item(3, 6, "乙.pdf")])
        entries = build_confirmed_segments_md(normalized, _pages())

        for entry in entries:
            spans = entry["page_spans"]
            assert spans, "有正文的段必须给出页锚点"
            assert [span["page"] for span in spans] == list(range(entry["page_start"], entry["page_end"] + 1))
            for span in spans:
                sliced = entry["markdown"][span["start"] : span["end"]]
                assert f"第{span['page']}页正文" in sliced, f"第 {span['page']} 页锚点切出来的不是本页正文"


class TestBuildConfirmedSegmentsMdWithoutPages:
    """旧任务没有 pages.json（或形状对不上）时**不许静默错位**。"""

    @staticmethod
    def _previous() -> list[dict[str, Any]]:
        """旧 md 产物：0 基 order（LLM 路径的真实形态）。"""
        return [
            {
                "order": index,
                "page_start": start,
                "page_end": end,
                "markdown": f"# 旧名{index}\n\n" + "\n\n".join(f"第{no}页正文" for no in range(start, end + 1)),
                "positioned": [{"page": no, "type": "text", "text": f"第{no}页正文"} for no in range(start, end + 1)],
                "quality_flags": [f"旧提示{index}"],
                "page_spans": [{"page": start, "start": 0, "end": 5}],
            }
            for index, (start, end) in enumerate([(1, 2), (3, 4), (5, 6)])
        ]

    def test_页区间没变时按区间配对而不是按旧order(self) -> None:
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(1, 2, "甲.pdf"), _item(3, 4, "乙.pdf"), _item(5, 6, "丙.pdf")])
        entries = build_confirmed_segments_md(normalized, [], previous_entries=self._previous())

        assert [e["order"] for e in entries] == [1, 2, 3]
        for entry in entries:
            _assert_md_matches_range(entry)
        # 区间完全一致 → 坐标/提示/页锚点都还有效，整条沿用
        assert entries[0]["page_spans"] == [{"page": 1, "start": 0, "end": 5}]
        assert entries[0]["quality_flags"] == ["旧提示0"]

    def test_合并段按页序拼接旧正文(self) -> None:
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(1, 4, "合并.pdf"), _item(5, 6, "尾段.pdf")])
        entries = build_confirmed_segments_md(normalized, [], previous_entries=self._previous())

        for entry in entries:
            _assert_md_matches_range(entry)
        assert [b["page"] for b in entries[0]["positioned"]] == [1, 2, 3, 4]
        assert entries[0]["quality_flags"] == ["旧提示0", "旧提示1"]

    def test_部分重叠时丢掉页锚点(self) -> None:
        """锚点是对旧 md 字符串量出来的偏移，拼接后指向已不对——留着比没有更糟。"""
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(1, 4, "合并.pdf"), _item(5, 6, "尾段.pdf")])
        entries = build_confirmed_segments_md(normalized, [], previous_entries=self._previous())

        assert entries[0]["page_spans"] == []
        assert entries[1]["page_spans"] == [{"page": 5, "start": 0, "end": 5}], "区间没变的那段锚点仍有效"

    def test_拆分段两半都拿到旧正文而不是各自为空(self) -> None:
        """无 pages.json 时切不开 md，宁可两半都带全文（可复核）也不能丢正文。"""
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(1, 1, "前半.pdf"), _item(2, 2, "后半.pdf"), _item(3, 6, "其余.pdf")])
        entries = build_confirmed_segments_md(normalized, [], previous_entries=self._previous())

        assert all(entry["markdown"].strip() for entry in entries)
        assert [b["page"] for b in entries[0]["positioned"]] == [1]
        assert [b["page"] for b in entries[1]["positioned"]] == [2]

    def test_配不上的段留空串并告警(self, caplog: Any) -> None:
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        normalized = _confirmed([_item(1, 6, "整本.pdf")])
        with caplog.at_level("WARNING", logger="apps.pdf_splitting"):
            entries = build_confirmed_segments_md(normalized, [], previous_entries=[])

        assert entries[0]["markdown"] == ""
        assert entries[0]["order"] == 1
        assert "pdf_split_confirm_md_realigned" in caplog.text

    def test_旧产物页区间非法时不崩(self) -> None:
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        broken = [{"order": 0, "page_start": "x", "page_end": None, "markdown": "脏数据"}]
        entries = build_confirmed_segments_md(_confirmed([_item(1, 6, "整本.pdf")]), [], previous_entries=broken)
        assert entries[0]["markdown"] == ""

    def test_pages形状对不上时走降级而不是抛(self) -> None:
        """旧任务写过的老结构（缺字段）：PageDescriptor(**item) 会 TypeError。"""
        from apps.pdf_splitting.services.job_service import build_confirmed_segments_md

        entries = build_confirmed_segments_md(
            _confirmed([_item(1, 2, "甲.pdf"), _item(3, 6, "乙.pdf")]),
            [{"page_no": 1}],
            previous_entries=self._previous(),
        )
        assert [e["order"] for e in entries] == [1, 2]
        _assert_md_matches_range(entries[0])


class TestLoadSegmentsPageSpans:
    """页锚点读取的降级契约（与 load_segments_positioned 同口径）。"""

    @staticmethod
    def _load(path: Path) -> dict[int, list[dict[str, Any]]]:
        from apps.pdf_splitting.services.job_service import load_segments_page_spans

        return load_segments_page_spans(path)

    def test_正常往返(self, tmp_path: Path) -> None:
        path = tmp_path / "segments_md.json"
        path.write_text(
            json.dumps([{"order": 1, "page_spans": [{"page": 1, "start": 0, "end": 12}]}]), encoding="utf-8"
        )
        assert self._load(path) == {1: [{"page": 1, "start": 0, "end": 12}]}

    def test_文件不存在回空表(self, tmp_path: Path) -> None:
        assert self._load(tmp_path / "缺失.json") == {}

    def test_json损坏回空表(self, tmp_path: Path) -> None:
        path = tmp_path / "segments_md.json"
        path.write_text('[{"order": 1,', encoding="utf-8")
        assert self._load(path) == {}

    def test_顶层不是列表回空表(self, tmp_path: Path) -> None:
        path = tmp_path / "segments_md.json"
        path.write_text('{"order": 1}', encoding="utf-8")
        assert self._load(path) == {}

    def test_旧任务无该字段回空表(self, tmp_path: Path) -> None:
        path = tmp_path / "segments_md.json"
        path.write_text(json.dumps([{"order": 1, "markdown": "正文"}]), encoding="utf-8")
        assert self._load(path) == {}

    def test_非字典条目与非字典锚点被跳过(self, tmp_path: Path) -> None:
        path = tmp_path / "segments_md.json"
        path.write_text(
            json.dumps([{"order": 1, "page_spans": [{"page": 1, "start": 0, "end": 3}, "脏", 7]}, "脏"]),
            encoding="utf-8",
        )
        assert self._load(path) == {1: [{"page": 1, "start": 0, "end": 3}]}


class TestSegmentOutPageSpans:
    """API 字段名契约：前端按 ``page_spans`` 映射 pageSpans，改名就断链。"""

    @staticmethod
    def _payload(**extra: Any) -> dict[str, Any]:
        return {
            "id": 1,
            "order": 1,
            "page_start": 1,
            "page_end": 2,
            "segment_type": "evidence",
            "segment_label": "证据",
            "filename": "证据.pdf",
            "confidence": 0.9,
            "review_flag": "normal",
            "review_flag_label": "正常",
            "source_method": "llm",
            "content_md": "# 证据\n\n正文\n",
            **extra,
        }

    def test_页锚点按page_spans透出(self) -> None:
        from apps.pdf_splitting.api.pdf_splitting_api import SegmentOut

        spans = [{"page": 1, "start": 0, "end": 6}, {"page": 2, "start": 6, "end": 12}]
        out = SegmentOut(**self._payload(page_spans=spans))

        assert out.model_dump()["page_spans"] == spans

    def test_旧任务缺该字段时默认空列表(self) -> None:
        from apps.pdf_splitting.api.pdf_splitting_api import SegmentOut

        assert SegmentOut(**self._payload()).page_spans == []
