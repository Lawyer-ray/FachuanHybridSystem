"""页面质量画像 / 跨页一致性校对接入流水线的单元测试。

两个判据模块（`page_quality` / `cross_page_consistency`）各自有自己的用例；
这里只锁**接入层**的契约：

- 页面质量写进 summary，不拦流程（判据是启发式，提示不该变成门禁）；
- 跨页一致性写进 summary 时只裁体积（前 N 条 + 真实总数），不做业务过滤；
- 段级 `quality_flags` 落在 segments_md.json 里，由 job API 读回；
- 两阶段链路（取字 → 分段是两个独立任务）能把页面质量从取字带到分段。

判据的内部实现会被改，所以这里**不假设具体判据**：需要「某页判成什么」时用
stub 或直接构造 `PageQuality`，不依赖字数和中文句子的具体门槛。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from apps.pdf_splitting.services.split.consistency_summary import (
    attach_quality_flags_to_markdown,
    detect_inconsistencies,
    flag_text,
    flags_for_markdown,
    pick_top_inconsistencies,
)
from apps.pdf_splitting.services.split.cross_page_consistency import Inconsistency
from apps.pdf_splitting.services.split.page_quality import PageQuality
from apps.pdf_splitting.services.split.page_quality_summary import (
    build_page_quality_summary,
    qualities_by_page,
    serialize_quality,
)


def _page(page_no: int, text: str = "", layout: dict[str, Any] | None = None) -> Any:
    """页描述符桩：聚合层只读 page_no / text / layout 三个属性。"""
    return SimpleNamespace(page_no=page_no, text=text, layout=layout)


def _quality(page_no: int, kind: str, *, review: bool, reason: str) -> PageQuality:
    return PageQuality(page_no=page_no, char_count=10, kind=kind, reason=reason, needs_visual_review=review)


def _hit(canonical: str, variant: str, *, canonical_count: int, variant_count: int, confidence: str = "high") -> Any:
    return Inconsistency(
        canonical=canonical,
        variant=variant,
        canonical_count=canonical_count,
        variant_count=variant_count,
        pages=[1, 2],
        confidence=confidence,
    )


class TestPageQualitySummary:
    def test_三类页各进自己的桶(self) -> None:
        pages = [_page(1), _page(2), _page(3)]
        qualities = {
            1: _quality(1, "graphic", review=True, reason="疑似图形页（图纸/印章/照片），请核对原图"),
            2: _quality(2, "sparse", review=False, reason="内容较少，可能是封面/证件/表单，建议核对"),
            3: _quality(3, "blank", review=False, reason="空白页"),
        }
        with patch(
            "apps.pdf_splitting.services.split.page_quality_summary.assess_page_quality",
            side_effect=lambda *, page_no, text, layout: qualities[page_no],
        ):
            summary = build_page_quality_summary(pages)

        assert summary["graphic_pages"] == [1]
        assert summary["sparse_pages"] == [2]
        assert summary["blank_pages"] == [3]

    def test_details只收需要看原图的页且直接用判据的reason(self) -> None:
        """details 的文案不再自己造：判据的 reason 就是给律师看的那句话。"""
        with patch(
            "apps.pdf_splitting.services.split.page_quality_summary.assess_page_quality",
            side_effect=lambda *, page_no, text, layout: _quality(
                page_no, "graphic" if page_no == 147 else "sparse", review=page_no == 147, reason=f"第{page_no}页说明"
            ),
        ):
            summary = build_page_quality_summary([_page(147), _page(148)])

        # 只有 needs_visual_review 的页进 details，否则 164 页全被列一遍等于没提示
        assert summary["details"] == {"147": "第147页说明"}

    def test_无页号对象被跳过(self) -> None:
        assert build_page_quality_summary([_page(0)]) == {
            "graphic_pages": [],
            "sparse_pages": [],
            "blank_pages": [],
            "details": {},
        }

    def test_空版面列表与None版面都交给判据处理(self) -> None:
        """接入层不预判 layout：有块没块是判据的事，这里只负责原样透传。"""
        seen: list[Any] = []
        with patch(
            "apps.pdf_splitting.services.split.page_quality_summary.assess_page_quality",
            side_effect=lambda *, page_no, text, layout: (
                seen.append(layout) or _quality(page_no, "text", review=False, reason="正常文本页")
            ),
        ):
            build_page_quality_summary([_page(1, layout={"blocks": []}), _page(2, layout=None)])

        assert seen == [{"blocks": []}, None]

    def test_落盘载荷含summary区块与逐页画像(self) -> None:
        qualities = {5: _quality(5, "graphic", review=True, reason="请核对原图")}
        payload = serialize_quality(summary={"graphic_pages": [5]}, qualities=qualities)

        assert payload["graphic_pages"] == [5]
        assert payload["pages"]["5"]["kind"] == "graphic"
        assert payload["pages"]["5"]["needs_visual_review"] is True

    def test_qualities_by_page按页号索引(self) -> None:
        with patch(
            "apps.pdf_splitting.services.split.page_quality_summary.assess_page_quality",
            side_effect=lambda *, page_no, text, layout: _quality(page_no, "sparse", review=False, reason="r"),
        ):
            result = qualities_by_page([_page(3), _page(7)])
        assert sorted(result) == [3, 7]


class TestInconsistencyIntegration:
    def test_输入是页号到原文的映射(self) -> None:
        """喂 text 而不是 normalized_text：判据靠空白做「排版差异不算错字」的排除。"""
        captured: dict[int, str] = {}

        def _fake(pages_text: dict[int, str], **kwargs: Any) -> list[Any]:
            captured.update(pages_text)
            return []

        with patch("apps.pdf_splitting.services.split.consistency_summary.find_inconsistencies", side_effect=_fake):
            detect_inconsistencies([_page(1, "经办人 张三"), _page(2, "受办人张三")])

        assert captured == {1: "经办人 张三", 2: "受办人张三"}

    def test_没有页号的占位不进比对(self) -> None:
        captured: dict[int, str] = {}
        with patch(
            "apps.pdf_splitting.services.split.consistency_summary.find_inconsistencies",
            side_effect=lambda pages_text, **kw: captured.update(pages_text) or [],
        ):
            detect_inconsistencies([_page(0, "噪声"), _page(1, "经办人")])
        assert 0 not in captured

    def test_summary只取前N条并单独报总数(self) -> None:
        """1340 条灌进 summary 会把 job 详情撑到几 MB，前端也展示不过来。"""
        items = [_hit(f"甲{i:03d}", f"乙{i:03d}", canonical_count=20, variant_count=5) for i in range(120)]

        picked = pick_top_inconsistencies(items, limit=50)

        assert len(picked) == 50
        assert picked[0]["canonical"] == "甲000"
        assert set(picked[0]) == {"canonical", "variant", "canonical_count", "variant_count", "pages", "confidence"}

    def test_排序_high在前_同级按变体次数降序(self) -> None:
        items = [
            _hit("甲", "乙", canonical_count=5, variant_count=2, confidence="medium"),
            _hit("丙", "丁", canonical_count=9, variant_count=1, confidence="high"),
            _hit("戊", "己", canonical_count=9, variant_count=9, confidence="high"),
        ]
        picked = pick_top_inconsistencies(items)

        assert [item["variant"] for item in picked] == ["己", "丁", "乙"]

    def test_裁条数不改变判据结果(self) -> None:
        """接入层只裁输出体积，**不做业务过滤**：条数上限之外的条目只是没进 summary。"""
        items = [_hit(f"甲{i}", f"乙{i}", canonical_count=10, variant_count=3) for i in range(8)]
        assert len(pick_top_inconsistencies(items, limit=3)) == 3
        assert len(items) == 8  # 入参没被改动

    def test_段Markdown命中variant才出flag(self) -> None:
        items = [_hit("经办人", "受办人", canonical_count=178, variant_count=30)]
        flags = flags_for_markdown("# 借条\n受办人：张三", items)
        assert len(flags) == 1

        assert flags_for_markdown("# 借条\n经办人：张三", items) == []
        assert flags_for_markdown("", items) == []

    def test_flag文案不写死具体数字(self) -> None:
        """频次来自判据统计，文案只是插值——写死「178 次」会在判据改动后变成谎话。"""
        text = flag_text(_hit("经办人", "受办人", canonical_count=178, variant_count=30))
        assert "受办人" in text and "经办人" in text
        assert "178" in text and "30" in text

        other = flag_text(_hit("经办人", "受办人", canonical_count=7, variant_count=2))
        assert "7" in other and "2" in other

    def test_同一variant只出一条flag(self) -> None:
        items = [
            _hit("经办人", "受办人", canonical_count=178, variant_count=30),
            _hit("受办人", "受办人", canonical_count=30, variant_count=3),
        ]
        flags = flags_for_markdown("受办人签字", items)
        assert len(flags) == 1

    def test_给每段补quality_flags且不动正文(self) -> None:
        items = [_hit("经办人", "受办人", canonical_count=178, variant_count=30)]
        segments_md = [
            {"order": 1, "markdown": "# 借条\n受办人：张三", "positioned": [{"page": 1}]},
            {"order": 2, "markdown": "# 证据清单\n经办人", "positioned": []},
        ]

        result = attach_quality_flags_to_markdown(segments_md, items)

        assert result[0]["quality_flags"] and result[0]["markdown"].startswith("# 借条")
        assert result[0]["positioned"] == [{"page": 1}]
        assert result[1]["quality_flags"] == []
        assert result is segments_md  # 就地补键，产物的其它结构不变


class TestTwoStageCarriesPageQuality:
    """两阶段链路：页面质量在取字阶段算出、分段阶段才用得着。

    这两个阶段是两个 Django-Q 任务，只靠 job 目录里的文件传递——不落盘的话
    ``quality_flags`` 在线上（走两阶段）永远是空的，而单任务入口却正常，
    这是「测试全绿但功能不可用」的典型形态。
    """

    def test_落盘读回往返(self, tmp_path: Path) -> None:
        from apps.pdf_splitting.services.split import two_stage

        storage = MagicMock()
        storage.page_quality_json_path = tmp_path / "page_quality.json"

        def write_json(path: Path, payload: object) -> None:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        storage.write_json.side_effect = write_json

        payload = {"graphic_pages": [147], "details": {"147": "请核对原图"}, "pages": {"147": {"kind": "graphic"}}}
        two_stage.save_page_quality(storage, payload)

        assert two_stage.load_page_quality(storage) == payload

    def test_产物缺失或损坏回空表不炸分段阶段(self, tmp_path: Path) -> None:
        from apps.pdf_splitting.services.split import two_stage

        storage = MagicMock()
        missing = tmp_path / "page_quality.json"
        storage.page_quality_json_path = missing
        assert two_stage.load_page_quality(storage) == {}  # 旧任务没有这个产物

        missing.write_text("{不是 json", encoding="utf-8")
        assert two_stage.load_page_quality(storage) == {}

        missing.write_text('["不是字典"]', encoding="utf-8")
        assert two_stage.load_page_quality(storage) == {}


class TestSegmentQualityFlagsReadBack:
    def test_从segments_md读回quality_flags(self, tmp_path: Path) -> None:
        from apps.pdf_splitting.services.job_service import load_segments_quality_flags

        path = tmp_path / "segments_md.json"
        path.write_text(
            json.dumps(
                [
                    {"order": 1, "markdown": "# a", "quality_flags": ["疑似错字：受办人"]},
                    {"order": 2, "markdown": "# b"},
                    {"order": 3, "markdown": "# c", "quality_flags": ["", 42, "x"]},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        flags = load_segments_quality_flags(path)

        assert flags == {1: ["疑似错字：受办人"], 3: ["x"]}  # 空串与非字符串被剔除

    def test_缺失或损坏回空表不阻断任务详情(self, tmp_path: Path) -> None:
        from apps.pdf_splitting.services.job_service import load_segments_quality_flags

        assert load_segments_quality_flags(tmp_path / "nope.json") == {}

        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        assert load_segments_quality_flags(broken) == {}

    def test_序列化分段带quality_flags(self) -> None:
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        segment = MagicMock()
        segment.id = 1
        segment.order = 1
        segment.page_start = 1
        segment.page_end = 2
        segment.segment_type = "complaint"
        segment.filename = "起诉状.pdf"
        segment.confidence = 0.9
        segment.source_method = "llm"
        segment.review_flag = "normal"
        segment.get_review_flag_display.return_value = "正常"

        payload = PdfSplitJobService()._serialize_segment(segment, quality_flags=["疑似错字：受办人"])

        assert payload["quality_flags"] == ["疑似错字：受办人"]
        # 旧任务没有产物时给空表，前端按「没有提示」降级
        assert PdfSplitJobService()._serialize_segment(segment)["quality_flags"] == []


def _make_pdf(path: Path, pages: list[str | None]) -> None:
    """生成测试 PDF：每页一段插入文本；None = 空白页（无文本层）。

    本文件自带一份而不 import test_pipeline 的同名辅助：pytest 以
    ``--import-mode=importlib`` 运行时测试模块没有包路径可导，跨文件借桩的写法
    一换执行方式就炸。
    """
    import pymupdf as fitz

    with fitz.open() as doc:
        for content in pages:
            page = doc.new_page()
            if content:
                page.insert_text((72, 96), content, fontname="china-s")
        doc.save(path.as_posix())


class _LocalOnlyOCRHandler:
    """取字桩：照电子版 PDF 的默认路径走（文本层直接定稿，不调云端、不调本地 OCR）。"""

    def resolve_runtime_profile(self, profile_key: str) -> Any:
        from apps.pdf_splitting.services.split.split_models import OCRRuntimeProfile

        return OCRRuntimeProfile(key="balanced", use_v5=True, dpi=200, workers=2)

    def resolve_cloud_backends(self, cloud_backend: str | None = None) -> list[str]:
        return []

    def sha256_file(self, pdf_path: Path) -> str:
        return "hash-x"

    def read_ocr_cache(self, *, pdf_hash: str, profile_key: str, page_no: int) -> Any:
        return None

    def write_ocr_cache(self, *, pdf_hash: str, profile_key: str, result: Any) -> None:
        return None

    def parse_cloud_pages(self, *, pdf_path: Path, backend: str) -> dict[int, Any]:
        return {}

    def parallel_ocr(self, *, pdf_path: Path, page_numbers: list[int], runtime_profile: Any) -> dict[int, Any]:
        return {}


class _OneShotLLM:
    """分段桩：整本一段「起诉状」，避开真实 LLM 调用。"""

    def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
        from apps.pdf_splitting.services.split.llm_segment_detector import parse_llm_segments

        segments = [{"page_start": 1, "page_end": len(pages), "segment_type": "complaint", "segment_label": "起诉状"}]
        return parse_llm_segments(
            json.dumps(segments, ensure_ascii=False), total_pages=len(pages), template_key=template_key
        )


class TestAnalyzePdfWritesSummary:
    """analyze_pdf 的 summary 只增不改：新字段追加，旧键一个不少。"""

    def test_summary含page_quality与inconsistencies(self, tmp_path: Path) -> None:
        from apps.pdf_splitting.services.split.pipeline import analyze_pdf

        pdf = tmp_path / "t.pdf"
        _make_pdf(pdf, ["民事起诉状原告张三诉讼请求事实与理由人民法院"])

        outcome = analyze_pdf(
            pdf,
            template_key="filing_materials_v1",
            ocr_handler=_LocalOnlyOCRHandler(),
            llm_segment_detector=_OneShotLLM(),
        )

        # 页面质量：三类分桶与 details 一定存在（哪怕全空），前端凭键判断
        quality = outcome.summary["page_quality"]
        assert set(quality) == {"graphic_pages", "sparse_pages", "blank_pages", "details"}
        # 一致性：列表 + 真实总数两个键都在
        assert isinstance(outcome.summary["inconsistencies"], list)
        assert outcome.summary["inconsistency_total"] >= len(outcome.summary["inconsistencies"])
        # 旧键没被顶掉
        assert outcome.summary["segment_backend"] == "llm"
        assert outcome.summary["ocr_provider"] == "local"
        assert outcome.summary["layout_mode"] == "fast_text"
        # 每段都带 quality_flags（空表也要有键，前端据此整块不渲染）
        assert all("quality_flags" in entry for entry in outcome.segments_md)
