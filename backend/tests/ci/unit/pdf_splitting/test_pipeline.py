"""Tests for split.pipeline：取字编排 / 取消 / 分段降级 / md 产出的无任务耦合流水线。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split.pipeline import (
    LockedCloudBackendUnavailable,
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

    def write_ocr_cache(
        self, *, pdf_hash: str, profile_key: str, result: OCRPageResult, page_no: int | None = None
    ) -> None:
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
                    page_no=1,
                    text=self.TEXT,
                    source_method="textin_ocr",
                    ocr_failed=False,
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

    def test_auto_无可用平台时静默回落本地(self, tmp_path: Path) -> None:
        """auto（含 None / 脏值）没有可用平台：行为不变——不碰云端，直接本地兜底。"""
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = _StubOCRHandler(backend=None)
        handler.resolve_cloud_backends = lambda pref=None: []  # type: ignore[method-assign]

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout", cloud_backend="auto"
        )

        assert handler.cloud_calls == []
        assert summary["ocr_provider"] == "local"

    def test_显式锁定不可用平台时明确失败不降级本地(self, tmp_path: Path) -> None:
        """锁定的平台未启用：必须失败并说清「未降级」，不许拿文本层/本地 OCR 顶替。"""
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [self.TEXT])  # 有文本层也不许悄悄顶替
        handler = _StubOCRHandler(backend=None)
        handler.resolve_cloud_backends = lambda pref=None: []  # type: ignore[method-assign]

        with pytest.raises(LockedCloudBackendUnavailable) as excinfo:
            PageTextExtractor(ocr_handler=handler).extract(
                pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout", cloud_backend="mineru"
            )

        message = str(excinfo.value)
        assert "mineru" in message
        assert "未降级" in message
        assert handler.cloud_calls == []
        assert handler.local_calls == []

    def test_锁定不可用时不采信页缓存(self, tmp_path: Path) -> None:
        """页缓存命中也不能绕过「锁定不可用即失败」。

        真实复现路径：同一份 PDF 先跑过一次（云端失败 → 本地兜底），本地 OCR 的结果
        被写进「无平台」那份档案；之后用户改成「仅 MinerU」重跑，无候选 →
        档案名退化成 profile 名 → 命中同一批缓存 → pending 被清空 →
        `_parse_cloud` 的守卫根本不会执行 → 又一次静默降级（正文来自本地 OCR）。
        所以锁定不可用时必须**跳过页缓存**，把页留在 pending 让守卫按设计抛错。
        """
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = _StubOCRHandler(backend=None)
        handler.resolve_cloud_backends = lambda pref=None: []  # type: ignore[method-assign]
        # 缓存里躺着的是本地 OCR 的结果（正是上一次兜底写进去的那份）
        handler.read_ocr_cache = lambda **kwargs: OCRPageResult(  # type: ignore[method-assign]
            page_no=int(kwargs["page_no"]), text=self.TEXT, source_method="local_ocr"
        )

        with pytest.raises(LockedCloudBackendUnavailable) as excinfo:
            PageTextExtractor(ocr_handler=handler).extract(
                pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="layout", cloud_backend="mineru"
            )

        assert "mineru" in str(excinfo.value)
        assert handler.local_calls == [], "缓存被采信 → 页面不会进本地 OCR，说明守卫被绕过了"

    def test_纯电子件显式锁定不可用也不失败(self, tmp_path: Path) -> None:
        """fast_text 下文本层自己就够：压根走不到云端，锁定平台未启用也不能误伤。"""
        pdf = tmp_path / "d.pdf"
        _make_pdf(pdf, [self.TEXT])
        handler = _StubOCRHandler(backend=None)
        handler.resolve_cloud_backends = lambda pref=None: []  # type: ignore[method-assign]

        pages, _summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, layout_mode="fast_text", cloud_backend="mineru"
        )

        assert [page.source_method for page in pages] == ["text"]
        assert handler.cloud_calls == []


class TestUnstructuredNoiseCleaning:
    """文本层 / 兜底页的噪声清洗：云端块路径靠块类型滤，这两条路径以前零过滤。"""

    STAMPED = "民事判决书\n已核对与原件相符\n扫描件与留档资料相符\n经办人：李四\n12\n本院认为借款事实清楚"

    def test_印章套话与页码行被剔除(self) -> None:
        from apps.pdf_splitting.services.split.pipeline import clean_unstructured_page_text

        cleaned = clean_unstructured_page_text(self.STAMPED)
        assert "已核对与原件相符" not in cleaned
        assert "经办人" not in cleaned
        assert "本院认为借款事实清楚" in cleaned
        assert "\n12\n" not in cleaned

    def test_长纯数字行是账号_整页跳过页码清洗(self) -> None:
        from apps.pdf_splitting.services.split.pipeline import clean_unstructured_page_text

        # 579 兜底页实测有 16/18/22 位纯数字行（卡号/账号）。clean_page_artifacts
        # 会无条件删掉所有纯数字行，含这种行的页必须跳过它那一道。
        text = "交易明细\n1234567890123456\n7"
        assert clean_unstructured_page_text(text) == text

    def test_跳过页码清洗时印章套话仍然清(self) -> None:
        from apps.pdf_splitting.services.split.pipeline import clean_unstructured_page_text

        assert clean_unstructured_page_text("已核对与原件相符\n1234567890123456") == "1234567890123456"

    def test_只有无块类型的来源才清洗(self) -> None:
        from apps.pdf_splitting.services.split.pipeline import build_page_descriptor

        cloud = build_page_descriptor(
            page_no=1, text=self.STAMPED, source_method="mineru_ocr", ocr_failed=False, template_key=TEMPLATE_KEY
        )
        # 云端页的噪声由重建层按块类型处理，取字层不重复清洗（避免两套判据漂移）
        assert cloud.text == self.STAMPED

        for method in ("text", "ocr", "ocr_cache"):
            page = build_page_descriptor(
                page_no=1, text=self.STAMPED, source_method=method, ocr_failed=False, template_key=TEMPLATE_KEY
            )
            assert "已核对与原件相符" not in page.text, method

    def test_取字层不吞混合行正文(self) -> None:
        """回归：清洗曾在取字层把「经办人：」之后整段吃掉，律师读到的正文直接少一段。"""
        from apps.pdf_splitting.services.split.pipeline import build_page_descriptor

        lines = [
            "经办人：测试甲 测试乙根据《中华人民共和国物权法》等法律法规，经审查准予登记，颁发此证。",
            "| 经办人：测试甲 日期：2023.2.15 |",
            "经办人：测试甲 测试乙",
            "已核对与原件相符",
        ]
        page = build_page_descriptor(
            page_no=1, text="\n".join(lines), source_method="ocr", ocr_failed=False, template_key=TEMPLATE_KEY
        )

        assert lines[0] in page.text  # 权证正文
        assert lines[1] in page.text  # 表格行的日期单元格
        assert "经办人：测试甲 测试乙" not in page.text.splitlines()  # 纯套话行仍整行剔
        assert "已核对与原件相符" not in page.text.splitlines()


class TestCacheProvenance:
    """缓存档案名记的是首选平台，真实来源只能从条目里恢复——否则坐标系被污染。"""

    def _cached(self, source_method: str) -> OCRPageResult:
        return OCRPageResult(
            page_no=1,
            text="银行流水交易明细",
            source_method=source_method,
            ocr_failed=False,
            layout={
                "page_no": 1,
                "blocks": [{"type": "text", "text": "银行流水交易明细", "bbox": [10, 10, 500, 60]}],
                "width": 595,
                "height": 842,
            },
        )

    def _handler(self, cached: OCRPageResult) -> Any:
        handler = _StubOCRHandler()
        handler.resolve_cloud_backends = lambda pref=None: ["mineru", "textin"]  # type: ignore[method-assign]
        handler.read_ocr_cache = lambda **kwargs: cached  # type: ignore[method-assign]
        return handler

    def test_容灾写进的缓存命中后报真实平台(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, [None])
        handler = self._handler(self._cached("textin_ocr"))

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, cloud_backend="auto"
        )

        assert handler.cloud_calls == []  # 全命中，本轮没调云端
        assert pages[0].source_method == "textin_ocr"
        # 首选是 mineru，但产物是 TextIn 的绝对坐标：报 mineru 会让绿框整体错位
        assert summary["ocr_provider"] == "textin"

    def test_本地兜底缓存标记原样透传(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, [None])
        # 本地 OCR 没有平台可言，handler 给的就是 ocr_cache（转换在 handler 侧，见
        # test_ocr_cache_selection）；编排层不再二次改写来源。
        handler = self._handler(self._cached("ocr_cache"))

        pages, _summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )
        assert pages[0].source_method == "ocr_cache"

    def test_本轮云端成功时以本轮平台为准(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, [None, None])
        handler = _StubOCRHandler(
            cloud={2: OCRPageResult(page_no=2, text="第二页正文", source_method="mineru_ocr", ocr_failed=False)}
        )
        handler.resolve_cloud_backends = lambda pref=None: ["mineru", "textin"]  # type: ignore[method-assign]
        handler.read_ocr_cache = lambda **kwargs: (  # type: ignore[method-assign]
            self._cached("textin_ocr") if kwargs["page_no"] == 1 else None
        )

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY, cloud_backend="auto"
        )
        assert summary["ocr_provider"] == "mineru"


class TestSegmentBackendHonesty:
    """单批降级必须写进 summary：前端 segmentBackendOf 读到 llm 就不提示规则降级。"""

    def test_批次口径翻译成三种来源(self) -> None:
        from apps.pdf_splitting.services.split.pipeline import _segment_backend_of

        assert _segment_backend_of({"total_batches": 7, "llm_batches": 7, "rule_batches": 0}) == "llm"
        assert _segment_backend_of({"total_batches": 7, "llm_batches": 6, "rule_batches": 1}) == "mixed"
        assert _segment_backend_of({"total_batches": 7, "llm_batches": 0, "rule_batches": 7}) == "rule"
        # 拿不到统计（单批路径未填）时沿用原口径，不谎报降级
        assert _segment_backend_of({}) == "llm"

    def test_传stats与checkpoint并按批数写summary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.pdf_splitting.services.split import segment_batch
        from apps.pdf_splitting.services.split.split_models import PageDescriptor, SegmentDraft

        captured: dict[str, Any] = {}

        def _fake(**kwargs: Any) -> list[Any]:
            captured.update(kwargs)
            kwargs["stats"].update({"total_batches": 7, "llm_batches": 6, "rule_batches": 1, "single_batch": False})
            return [
                SegmentDraft(
                    order=0,
                    page_start=1,
                    page_end=1,
                    segment_type="complaint",
                    filename="起诉状.pdf",
                    confidence=0.9,
                    source_method="llm",
                    review_flag="normal",
                )
            ]

        monkeypatch.setattr(segment_batch, "detect_in_batches", _fake)
        pages = [
            PageDescriptor(
                page_no=1,
                text="民事起诉状",
                normalized_text="民事起诉状",
                head_text="民事起诉状",
                source_method="text",
                ocr_failed=False,
                top_candidates=[],
            )
        ]
        checkpoint = tmp_path / "segment_checkpoint.json"

        _drafts, summary = detect_segments_with_fallback(
            pages, template_key=TEMPLATE_KEY, llm_segment_detector=_StubLLM(), checkpoint_path=checkpoint
        )

        assert isinstance(captured["stats"], dict)
        assert captured["checkpoint_path"] == checkpoint
        assert summary["segment_backend"] == "mixed"
        assert summary["segment_rule_batches"] == 1
        assert summary["segment_total_batches"] == 7
        assert summary["segment_llm_fallback_reason"] == ""


class TestDuplicatePageDedupe:
    """一式三份：重复页只 OCR 一次，其余页继承文字。

    真实 40 页立案材料扫描件里 27 页是副本，本机 OCR 取字从 97s 降到 56.5s
    （fast 档，冷缓存）；balanced 档 418s → 155s。
    """

    def test_重复页只送代表作进OCR(self, tmp_path: Path) -> None:
        pdf = tmp_path / "dup.pdf"
        # 4 页：A / A / B / A —— 相同文本渲染相同 → 第 2、4 页应判为第 1 页的副本
        # 用**画线**而不是插文字造扫描页：插文字会生成文本层，那几页会走「文本层直取」
        # 根本不进 OCR；而且只在页顶写 4 个字母时两页墨迹差不到 0.001，指纹分不开。
        # 18 行 vs 5 行才像真实页（整页密排 vs 半页）。
        with fitz.open() as doc:
            for line_count in (18, 18, 0, 18):
                page = doc.new_page()
                for index in range(line_count):
                    y = 90 + index * 28
                    page.draw_line((72, y), (520, y), color=(0, 0, 0), width=2)
                if line_count == 0:  # 第 3 页：整块墨（模拟版式完全不同的另一种材料）
                    page.draw_rect(fitz.Rect(60, 60, 540, 760), color=None, fill=(0, 0, 0))
            doc.save(pdf.as_posix())
        handler = _StubOCRHandler(
            backend=None,  # 无云端 → 走本机 OCR（去重只在这条路径生效）
            local={
                1: OCRPageResult(page_no=1, text="第一页内容", source_method="local_ocr", ocr_failed=False),
                3: OCRPageResult(page_no=3, text="第三页内容", source_method="local_ocr", ocr_failed=False),
            },
        )
        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )

        assert handler.local_calls == [[1, 3]], "重复页不应再送 OCR"
        assert [p.source_method for p in pages] == ["local_ocr", "dedupe_copy", "local_ocr", "dedupe_copy"]
        assert pages[1].text == pages[0].text
        assert pages[3].text == pages[0].text
        assert summary["dedupe_skipped_pages"] == 2
        assert summary["dedupe_filled_pages"] == 2

    def test_云端路径不做去重(self, tmp_path: Path) -> None:
        """云端是整本一次解析，少送几页省不掉往返，反而让页序对齐更复杂。"""
        pdf = tmp_path / "dup2.pdf"
        _make_pdf(pdf, [None, None])
        handler = _StubOCRHandler(
            cloud={
                1: OCRPageResult(page_no=1, text="同一页", source_method="mineru_ocr", ocr_failed=False),
                2: OCRPageResult(page_no=2, text="同一页", source_method="mineru_ocr", ocr_failed=False),
            }
        )
        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )

        assert all(p.source_method != "dedupe_copy" for p in pages)
        assert summary["dedupe_skipped_pages"] == 0


class TestDegeneratePageRouting:
    """云端/缓存给出的「废正文」不能当取字成功——它们要么进 pending 重取，要么被挡住。

    「有字 = 成功」这个判据骗得过人：复读循环与空返回都有字、任务成功、分段还给高置信度，
    而正文是垃圾。实测一页复读吐到 17000 字，一路进了 Markdown / 分段 / 归案。
    """

    _LOOPED = "\n".join(["同一段话被模型反复吐出来"] * 60)

    def test_云端退化页不进描述符_转本地兜底(self, tmp_path: Path) -> None:
        from apps.pdf_splitting.services.split.page_degeneracy import degeneracy_reason

        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, [None])
        handler = _StubOCRHandler(
            cloud={1: OCRPageResult(page_no=1, text=self._LOOPED, source_method="mineru_ocr", ocr_failed=False)},
            local={
                1: OCRPageResult(page_no=1, text="本地 OCR 读回来的正常正文", source_method="ocr", ocr_failed=False)
            },
        )

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )

        # 云端那份垃圾既没进正文，也没写进页缓存（写进去 = 这页永久是垃圾）
        assert degeneracy_reason(pages[0].text) == ""
        assert pages[0].text == "本地 OCR 读回来的正常正文"
        # 云端那份垃圾一次都没写进「云端缓存档案」（本地兜底自己那份可以写）
        assert [item for item in handler.written if item[0] != "balanced"] == []
        # 本地兜底确实被调到了这一页
        assert handler.local_calls == [[1]]
        assert summary["degenerate_pages"] == [1]

    def test_缓存里的退化页不采信_重新取字(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, [None])
        handler = _StubOCRHandler(
            cloud={1: OCRPageResult(page_no=1, text="重新取到的正常正文", source_method="mineru_ocr", ocr_failed=False)}
        )
        handler.read_ocr_cache = lambda **kwargs: OCRPageResult(  # type: ignore[method-assign]
            page_no=1, text=self._LOOPED, source_method="mineru_ocr", ocr_failed=False
        )

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )

        assert pages[0].text == "重新取到的正常正文"
        assert summary["degenerate_pages"] == [1]

    def test_正常页不受影响(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, [None])
        body = "5.4 借款人应在本合同签订后三十日内办理抵押登记手续，并将登记证明文件交由贷款人保管。"
        handler = _StubOCRHandler(
            cloud={1: OCRPageResult(page_no=1, text=body, source_method="mineru_ocr", ocr_failed=False)}
        )

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY
        )

        assert pages[0].text == body
        assert summary["degenerate_pages"] == []
        # 正常页照旧写缓存（批量回调 + 逐页各写一次，重复写是既有行为）
        assert handler.written and all(item == ("balanced_mineru_text_v2", 1) for item in handler.written)
