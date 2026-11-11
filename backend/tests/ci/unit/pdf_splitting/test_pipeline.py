"""Tests for split.pipeline：取字编排 / 取消 / 分段降级 / md 产出的无任务耦合流水线。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split.pipeline import (
    PageTextExtractor,
    PipelineCancelled,
    analyze_pdf,
    detect_segments_with_fallback,
)
from apps.pdf_splitting.services.split.split_models import OCRPageResult, OCRRuntimeProfile

TEMPLATE_KEY = "filing_materials_v1"
PROFILE = OCRRuntimeProfile(key="balanced", use_v5=True, dpi=200, workers=2)


def _make_pdf(path: Path, pages: list[str | None]) -> None:
    """生成测试 PDF：每页一段插入文本；None = 空白页（模拟扫描件，无文本层）。"""
    with fitz.open() as doc:
        for content in pages:
            page = doc.new_page()
            if content:
                page.insert_text((72, 96), content, fontname="china-s")
        doc.save(path.as_posix())


class _StubOCRHandler:
    """取字桩：缓存恒未命中；云端 / 本地 OCR 返回预置结果并记录调用。"""

    def __init__(
        self,
        *,
        cloud: dict[int, OCRPageResult] | None = None,
        cloud_error: Exception | None = None,
        local: dict[int, OCRPageResult] | None = None,
        backend: str | None = "mineru",
    ) -> None:
        self.cloud = cloud or {}
        self.local = local or {}
        self.cloud_error = cloud_error
        self.backend = backend
        self.cloud_calls: list[str] = []
        self.local_calls: list[list[int]] = []
        self.written: list[tuple[str, int]] = []

    def resolve_runtime_profile(self, profile_key: str) -> OCRRuntimeProfile:
        return PROFILE

    def resolve_cloud_backends(self, cloud_backend: str | None = None) -> list[str]:
        """候选顺序：本桩只模拟单平台场景，锁定时就返回它自己。

        容灾场景（多候选）由 TestCloudFailover 自己覆盖 side_effect。
        """
        return [self.backend] if self.backend else []

    def sha256_file(self, pdf_path: Path) -> str:
        return "hash-x"

    def read_ocr_cache(self, *, pdf_hash: str, profile_key: str, page_no: int) -> OCRPageResult | None:
        return None

    def write_ocr_cache(self, *, pdf_hash: str, profile_key: str, result: OCRPageResult) -> None:
        self.written.append((profile_key, result.page_no))

    def parse_cloud_pages(self, *, pdf_path: Path, backend: str) -> dict[int, OCRPageResult]:
        self.cloud_calls.append(backend)
        if self.cloud_error:
            raise self.cloud_error
        return self.cloud

    def parallel_ocr(
        self, *, pdf_path: Path, page_numbers: list[int], runtime_profile: OCRRuntimeProfile
    ) -> dict[int, OCRPageResult]:
        self.local_calls.append(page_numbers)
        return self.local


class _StubLLM:
    def __init__(self, segments: list[dict[str, Any]] | None = None, error: Exception | None = None) -> None:
        self.segments = segments
        self.error = error

    def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
        if self.error:
            raise self.error
        from apps.pdf_splitting.services.split.llm_segment_detector import parse_llm_segments

        return parse_llm_segments(json.dumps(self.segments), total_pages=len(pages), template_key=template_key)


class TestPageTextExtractor:
    def test_文本层直取_不走云端与本地(self, tmp_path: Path) -> None:
        pdf = tmp_path / "t.pdf"
        _make_pdf(pdf, ["民事起诉状原告张三被告李四诉讼请求事实与理由"])
        handler = _StubOCRHandler()
        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )

        assert [p.source_method for p in pages] == ["text"]
        assert handler.cloud_calls == []
        assert handler.local_calls == []
        assert summary["ocr_provider"] == "mineru"  # 桩声明了云端后端（未使用）
        assert summary["ocr_miss_count"] == 0

    def test_扫描页走云端_带版面进描述符(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, [None])
        layout = {"blocks": [{"type": "title", "text": "证据清单", "bbox": [0, 10, 100, 30]}]}
        handler = _StubOCRHandler(
            cloud={
                1: OCRPageResult(
                    page_no=1, text="证据清单证明内容", source_method="mineru_ocr", ocr_failed=False, layout=layout
                )
            }
        )
        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )

        assert handler.cloud_calls == ["mineru"]
        assert pages[0].layout_title == "证据清单"
        assert summary["ocr_provider"] == "mineru"
        assert summary["ocr_miss_count"] == 1
        # 缓存档案名带版面策略后缀（v2）：两种策略不得共用档案，否则关掉
        # 补版面后仍会读到带坐标的旧条目。这里按 summary 取值而不是写死字符串，
        # 档案命名再调整时用例不会无故红。
        assert (summary["ocr_cloud_cache_profile"], 1) in handler.written  # 云端结果写缓存

    def test_云端失败本地兜底_失败页记ocr_failed(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan2.pdf"
        _make_pdf(pdf, [None, None])
        handler = _StubOCRHandler(
            cloud_error=RuntimeError("mineru down"),
            local={1: OCRPageResult(page_no=1, text="银行流水交易明细", source_method="ocr", ocr_failed=False)},
        )
        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )

        assert handler.local_calls == [[1, 2]]
        assert [p.source_method for p in pages] == ["ocr", "ocr_failed"]
        assert pages[1].ocr_failed is True
        assert "RuntimeError" in summary["ocr_fallback_reason"]

    def test_取消回调抛PipelineCancelled(self, tmp_path: Path) -> None:
        pdf = tmp_path / "cancel.pdf"
        _make_pdf(pdf, [None] * 8)
        extractor = PageTextExtractor(ocr_handler=_StubOCRHandler(), is_cancelled=lambda: True)
        with pytest.raises(PipelineCancelled):
            extractor.extract(pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY)


class TestAnalyzePdf:
    def test_端到端_取字分段md一体产出(self, tmp_path: Path) -> None:
        pdf = tmp_path / "e2e.pdf"
        _make_pdf(pdf, ["民事起诉状原告张三诉讼请求", "此致人民法院具状人张三"])
        handler = _StubOCRHandler(backend=None)
        llm = _StubLLM(
            segments=[
                {"page_start": 1, "page_end": 2, "type": "complaint", "label": "起诉状", "confidence": 0.9},
            ]
        )
        progress: list[tuple[int, int]] = []
        outcome = analyze_pdf(
            pdf,
            template_key=TEMPLATE_KEY,
            on_progress=lambda done, total: progress.append((done, total)),
            ocr_handler=handler,
            llm_segment_detector=llm,
        )

        assert outcome.summary["segment_backend"] == "llm"
        assert [d.filename for d in outcome.drafts] == ["起诉状.pdf"]
        assert outcome.segments_md[0]["markdown"].startswith("# 起诉状\n")
        assert progress and progress[-1] == (2, 2)

    def test_llm失败降级规则引擎_summary记原因(self, tmp_path: Path) -> None:
        pdf = tmp_path / "fallback.pdf"
        _make_pdf(pdf, ["民事起诉状原告张三诉讼请求事实与理由人民法院"])
        outcome = analyze_pdf(
            pdf,
            template_key=TEMPLATE_KEY,
            ocr_handler=_StubOCRHandler(backend=None),
            llm_segment_detector=_StubLLM(error=RuntimeError("gateway down")),
        )
        assert outcome.summary["segment_backend"] == "rule"
        assert "gateway down" in outcome.summary["segment_llm_fallback_reason"]
        assert outcome.drafts  # 规则引擎兜底产出完整覆盖分段

    def test_detect_segments_with_fallback独立可调(self) -> None:
        from apps.pdf_splitting.services.split.split_models import PageDescriptor

        pages = [
            PageDescriptor(
                page_no=1,
                text="民事起诉状",
                normalized_text="民事起诉状",
                head_text="民事起诉状",
                source_method="text",
                ocr_failed=False,
                top_candidates=[
                    {
                        "segment_type": "complaint",
                        "label": "起诉状",
                        "score": 0.8,
                        "matched_strong": ["起诉状"],
                        "matched_weak": [],
                    }
                ],
            )
        ]
        drafts, summary = detect_segments_with_fallback(
            pages, template_key=TEMPLATE_KEY, llm_segment_detector=_StubLLM(error=RuntimeError("x"))
        )
        assert summary["segment_backend"] == "rule"
        assert drafts[0].page_start == 1 and drafts[0].page_end == 1


class TestLayoutMode:
    """「云端补版面」开关：电子页要不要为了坐标/表格而上云端。

    默认 fast_text 时电子页读到文本层就定稿（快、免费，但没有 bbox）；
    开 layout 后电子页也要上云端拿版面。这块最容易出的错是「开了却没生效」，
    所以除了正向用例，还要盯住"云端不可用/失败时如何告知"。
    """

    TEXT = "民事起诉状原告张三被告李四诉讼请求事实与理由"

    def _cloud_with_layout(self, page_nos: list[int]) -> dict[int, OCRPageResult]:
        return {
            no: OCRPageResult(
                page_no=no,
                text=self.TEXT,
                source_method="mineru_ocr",
                ocr_failed=False,
                layout={
                    "page_no": no,
                    "blocks": [{"type": "text", "text": self.TEXT, "bbox": [10, 10, 500, 60]}],
                },
            )
            for no in page_nos
        }

    def test_默认模式_电子页不调云端(self, tmp_path: Path) -> None:
        pdf = tmp_path / "digital.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = _StubOCRHandler(cloud=self._cloud_with_layout([1]))

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )

        assert pages[0].source_method == "text"
        assert pages[0].layout is None
        assert handler.cloud_calls == []  # 默认不为坐标去烧云端
        assert summary["layout_mode"] == "fast_text"

    def test_补版面模式_电子页也上云端拿版面(self, tmp_path: Path) -> None:
        pdf = tmp_path / "digital.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = _StubOCRHandler(cloud=self._cloud_with_layout([1]))

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout"
        )

        # 关键：电子页不再拿文本层定稿，而是走了云端并带回版面块
        assert handler.cloud_calls == ["mineru"]
        assert pages[0].source_method == "mineru_ocr"
        assert pages[0].layout is not None
        assert summary["cloud_used"] is True
        assert summary["layout_mode"] == "layout"
        assert summary["layout_unavailable_reason"] == ""

    def test_补版面模式_云端不可用时回落文本层并说明原因(self, tmp_path: Path) -> None:
        pdf = tmp_path / "digital.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = _StubOCRHandler(backend=None)  # 没配云端

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout"
        )

        # 回落但**不空页**：文本层是机器真值，不能因为拿不到版面就丢掉文字
        assert pages[0].source_method == "text"
        assert self.TEXT in pages[0].text
        # 必须显式说明「开了但没生效」，否则用户无从判断
        assert "未配置可用的云端解析平台" in summary["layout_unavailable_reason"]

    def test_补版面模式_云端失败回落文本层而非本地OCR(self, tmp_path: Path) -> None:
        """云端炸了也要用文本层补，不要拿可靠的字去喂 OCR 重新猜一遍。"""
        pdf = tmp_path / "digital.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = _StubOCRHandler(cloud_error=RuntimeError("cloud down"))

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout"
        )

        assert pages[0].source_method == "text"
        assert self.TEXT in pages[0].text
        assert handler.local_calls == []  # 没有降级到本地 OCR
        assert "云端解析失败" in summary["layout_unavailable_reason"]

    def test_补版面模式_扫描页仍走云端不受影响(self, tmp_path: Path) -> None:
        """扫描页本来就没有文本层，开关对它的行为不该有任何改变。"""
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, [None])
        cloud = {
            1: OCRPageResult(
                page_no=1,
                text=self.TEXT,
                source_method="mineru_ocr",
                ocr_failed=False,
                layout={"page_no": 1, "blocks": [{"type": "text", "text": self.TEXT, "bbox": [1, 2, 3, 4]}]},
            )
        }
        handler = _StubOCRHandler(cloud=cloud)

        pages, _summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout"
        )

        assert handler.cloud_calls == ["mineru"]
        assert pages[0].layout is not None

    def test_缓存档案按策略隔离(self, tmp_path: Path) -> None:
        """两种策略的结果不能共用一个缓存档案，否则关掉开关仍拿到带坐标的旧条目。"""
        pdf = tmp_path / "digital.pdf"
        _make_pdf(pdf, [self.TEXT])

        _pages_a, fast_summary = PageTextExtractor(ocr_handler=_StubOCRHandler()).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="fast_text"
        )
        _pages_b, layout_summary = PageTextExtractor(
            ocr_handler=_StubOCRHandler(cloud=self._cloud_with_layout([1]))
        ).extract(pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout")

        assert fast_summary["ocr_cloud_cache_profile"] != layout_summary["ocr_cloud_cache_profile"]
        assert "layout" in layout_summary["ocr_cloud_cache_profile"]

    def test_analyze_pdf_透传策略(self, tmp_path: Path) -> None:
        pdf = tmp_path / "digital.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = _StubOCRHandler(cloud=self._cloud_with_layout([1]))

        outcome = analyze_pdf(
            pdf,
            template_key=TEMPLATE_KEY,
            ocr_profile="balanced",
            layout_mode="layout",
            ocr_handler=handler,
            llm_segment_detector=_StubLLM(segments=[{"page_start": 1, "page_end": 1, "segment_type": "complaint"}]),
        )

        assert outcome.summary["layout_mode"] == "layout"
        assert handler.cloud_calls == ["mineru"]


class TestCloudFailover:
    """云端容灾与平台锁定。

    两者的差别不在"优先谁"，而在"失败怎么办"：
    · auto   —— 按优先级尝试，失败切下一个
    · 锁定值 —— 只用这一个，失败即失败，不降级（否则用户拿它做的比对会失效，
                计费也落在他没选的平台上）
    """

    TEXT = "民事起诉状原告张三被告李四诉讼请求事实与理由"

    def _handler(self, *, fail: set[str], candidates: list[str]) -> Any:
        handler = _StubOCRHandler()
        handler.resolve_cloud_backends = lambda pref=None: (  # type: ignore[method-assign]
            list(candidates) if (pref or "auto") == "auto" else [pref]
        )

        def _cloud(*, pdf_path: Path, backend: str) -> dict[int, OCRPageResult]:
            if backend in fail:
                raise RuntimeError(f"{backend} down")
            return {
                1: OCRPageResult(
                    page_no=1,
                    text=self.TEXT,
                    source_method=f"{backend}_ocr",
                    ocr_failed=False,
                    layout={"page_no": 1, "blocks": [{"type": "text", "text": self.TEXT, "bbox": [1, 2, 3, 4]}]},
                )
            }

        handler.parse_cloud_pages = _cloud  # type: ignore[method-assign]
        return handler

    def test_auto_首选可用时用首选(self, tmp_path: Path) -> None:
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [None])
        handler = self._handler(fail=set(), candidates=["mineru", "textin"])

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout", cloud_backend="auto"
        )

        assert summary["ocr_provider"] == "mineru"
        assert summary["cloud_failover_from"] == []

    def test_auto_首选失败切到下一个并记录来源(self, tmp_path: Path) -> None:
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [None])
        handler = self._handler(fail={"mineru"}, candidates=["mineru", "textin"])

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout", cloud_backend="auto"
        )

        assert summary["ocr_provider"] == "textin"
        # 记录"从谁切过来"，排障时能看出发生过容灾
        assert summary["cloud_failover_from"] == ["mineru"]
        assert summary["layout_unavailable_reason"] == ""

    def test_锁定平台失败时不降级(self, tmp_path: Path) -> None:
        """选了 MinerU 就只用 MinerU：失败不偷偷换成 Textin。"""
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [self.TEXT])  # 有文本层，补版面失败后能回落
        handler = self._handler(fail={"mineru"}, candidates=["mineru"])

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout", cloud_backend="mineru"
        )

        # 没有降级到 textin
        assert summary["ocr_provider"] == "mineru"
        assert summary["cloud_failover_from"] == []
        # 回落文本层，并说明原因（"开了但没生效"必须可见）
        assert pages[0].source_method == "text"
        assert "云端解析失败" in summary["layout_unavailable_reason"]

    def test_返回空结果也视为失败并继续下一个(self, tmp_path: Path) -> None:
        """解析"成功"但一页没出来，同样该换平台重试。"""
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [None])
        handler = _StubOCRHandler()
        handler.resolve_cloud_backends = lambda pref=None: ["mineru", "textin"]  # type: ignore[method-assign]

        def _cloud(*, pdf_path: Path, backend: str) -> dict[int, OCRPageResult]:
            if backend == "mineru":
                return {}  # 空结果
            return {
                1: OCRPageResult(
                    page_no=1, text=self.TEXT, source_method="textin_ocr", ocr_failed=False,
                    layout={"page_no": 1, "blocks": [{"type": "text", "text": self.TEXT, "bbox": [1, 2, 3, 4]}]},
                )
            }

        handler.parse_cloud_pages = _cloud  # type: ignore[method-assign]

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout", cloud_backend="auto"
        )

        assert summary["ocr_provider"] == "textin"
        assert summary["cloud_failover_from"] == ["mineru"]

    def test_全部失败时汇总各平台错误(self, tmp_path: Path) -> None:
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = self._handler(fail={"mineru", "textin"}, candidates=["mineru", "textin"])

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout", cloud_backend="auto"
        )

        # 两个平台都被尝试过（错误里两个名字都在），仍然回落文本层
        reason = summary["layout_unavailable_reason"]
        assert "mineru" in reason and "textin" in reason

    def test_无可用平台时不尝试云端(self, tmp_path: Path) -> None:
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = _StubOCRHandler(backend=None)
        handler.resolve_cloud_backends = lambda pref=None: []  # type: ignore[method-assign]

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout", cloud_backend="mineru"
        )

        assert handler.cloud_calls == []
        assert summary["ocr_provider"] == "local"
