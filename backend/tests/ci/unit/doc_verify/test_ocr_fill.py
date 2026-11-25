"""扫描页取字层的单测：只补空页 / hint 优先 / 预算 / 失败分级 / 页段对齐。

**一律不跑真引擎**：用例 monkeypatch ``ocr_fill._ocr_page``（本模块唯一的 OCR 调用点），
真实 OCR 首次建 ONNX 会话约 20s，模型文件也不在 CI 里。

所有样本都在用例里现场拼字符串 —— 断言只盯 ``\\f`` 段与页码的对应关系，
而这正是上层按页下标比对时唯一在乎的东西：少一段就整份错位。
"""

from __future__ import annotations

import io
import logging
from typing import Any

import pymupdf
import pytest
from PIL import Image

from apps.doc_verify.services.anchor import ocr_fill
from apps.doc_verify.services.anchor.ocr_fill import (
    DEFAULT_OCR_PAGE_LIMIT,
    ENGINE_LOCAL,
    ENGINE_UNAVAILABLE,
    PAGE_BUDGET_ENV,
    OcrFillResult,
    fill_text_with_ocr,
)

_LOGGER_NAME = "apps.doc_verify.services.anchor.ocr_fill"


def _make_blank_pdf(page_count: int) -> bytes:
    """合成「无文本层」PDF：只有图形、没有字（同 extract 单测的扫描件口径）。"""
    document = pymupdf.open()
    for index in range(page_count):
        page = document.new_page()
        page.draw_rect(
            pymupdf.Rect(80 + index * 20, 120, 320, 260),
            color=(0, 0, 0),
            fill=(0.2, 0.2, 0.2),
        )
    data = document.tobytes()
    document.close()
    return data


class _StubOcrService:
    """只记录「引擎收到了什么字节」，不跑真引擎。"""

    def __init__(self) -> None:
        self.images: list[bytes] = []

    def recognize_bytes(self, image_bytes: bytes) -> str:
        self.images.append(image_bytes)
        return " 识别出来的文本 \n"


class _FakePages:
    """按页返回文本（或抛异常）的替身，并记录引擎被调了哪几页、按什么顺序。"""

    def __init__(self, texts: dict[int, str], failures: dict[int, BaseException] | None = None) -> None:
        self._texts = texts
        self._failures = failures or {}
        self.attempted: list[int] = []

    def __call__(self, data: bytes, page_index: int) -> str:
        self.attempted.append(page_index)
        failure = self._failures.get(page_index)
        if failure is not None:
            raise failure
        return self._texts.get(page_index, "")


def _install(monkeypatch: pytest.MonkeyPatch, fake: _FakePages) -> _FakePages:
    monkeypatch.setattr(ocr_fill, "_ocr_page", fake)
    return fake


def _segments(result: OcrFillResult) -> list[str]:
    return result.text.split("\f")


class TestOnlyEmptyPages:
    def test_pages_with_text_are_never_re_ocred(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """已有字的页重 OCR = 把正确文本换成识别误差，所以只能补空页。"""
        fake = _install(monkeypatch, _FakePages({2: "第二页识别文本"}))

        result = fill_text_with_ocr(b"pdf-bytes", page_count=3, existing_text="第一页原样\f\f第三页原样")

        assert fake.attempted == [2]
        assert result.pages_attempted == (2,)
        assert result.pages_filled == (2,)
        assert result.pages_failed == ()
        assert result.budget_exhausted is False
        assert result.engine == ENGINE_LOCAL
        assert _segments(result) == ["第一页原样", "第二页识别文本", "第三页原样"]

    def test_blank_whitespace_page_counts_as_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """扫描页的文本层常是纯空白字符：strip 后为空才算「有字」，否则永远不补。"""
        fake = _install(monkeypatch, _FakePages({1: "识别文本"}))

        result = fill_text_with_ocr(b"pdf-bytes", page_count=2, existing_text="  \n\t\f第二页原样")

        assert fake.attempted == [1]
        assert _segments(result) == ["识别文本", "第二页原样"]

    def test_empty_ocr_output_still_counts_as_filled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """引擎跑通但返回空串：页面本身可能真没字，记 filled 而不是 failed（attempted = filled + failed）。"""
        _install(monkeypatch, _FakePages({1: ""}))

        result = fill_text_with_ocr(b"pdf-bytes", page_count=1, existing_text="")

        assert result.pages_attempted == (1,)
        assert result.pages_filled == (1,)
        assert result.pages_failed == ()
        assert result.text == ""

    def test_digital_document_needs_no_engine_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """全是字的回传件：一次都不许调引擎（探测会白建 20s 的 ONNX 会话）。"""
        fake = _install(monkeypatch, _FakePages({}))

        result = fill_text_with_ocr(b"pdf-bytes", page_count=2, existing_text="甲\f乙")

        assert fake.attempted == []
        assert result.pages_attempted == ()
        assert result.budget_exhausted is False
        assert result.engine == ENGINE_LOCAL
        assert result.text == "甲\f乙"


class TestPageSelectionOrder:
    def test_hint_pages_are_attempted_before_ascending_pages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """hint = 上层已知「差异出在第 N 页」：上限用尽时先牺牲没被告状的页。"""
        fake = _install(monkeypatch, _FakePages({1: "p1", 2: "p2", 3: "p3", 4: "p4"}))

        result = fill_text_with_ocr(
            b"pdf-bytes",
            page_count=4,
            existing_text="\f\f\f",
            page_budget=2,
            hint_pages=(3,),
        )

        assert fake.attempted == [3, 1]
        assert result.pages_attempted == (3, 1)
        assert result.budget_exhausted is True

    def test_hint_dedup_out_of_range_and_already_filled_are_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """hint 来自上层解析，去重 / 越界 / 有字的页都得在这里剔干净，否则会多花预算。"""
        fake = _install(monkeypatch, _FakePages({1: "p1", 3: "p3"}))

        result = fill_text_with_ocr(
            b"pdf-bytes",
            page_count=3,
            existing_text="第一页有字\f\f",
            page_budget=5,
            hint_pages=(3, 3, 0, 4, -2, 2),
        )

        assert fake.attempted == [3, 2]
        assert result.pages_attempted == (3, 2)
        assert result.pages_filled == (3, 2)
        assert result.budget_exhausted is False


class TestPageBudget:
    def test_budget_stops_after_n_pages_and_flags_exhausted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _install(monkeypatch, _FakePages({1: "p1", 2: "p2"}))

        result = fill_text_with_ocr(b"pdf-bytes", page_count=5, existing_text="", page_budget=2)

        assert fake.attempted == [1, 2]
        assert result.pages_attempted == (1, 2)
        assert result.budget_exhausted is True
        # 没轮到的页留空段，段数仍是 page_count，页码不会错位
        assert _segments(result) == ["p1", "p2", "", "", ""]

    def test_budget_zero_ocrs_nothing_and_reports_exhaustion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _install(monkeypatch, _FakePages({1: "p1"}))

        result = fill_text_with_ocr(b"pdf-bytes", page_count=2, existing_text="", page_budget=0)

        assert fake.attempted == []
        assert result.pages_attempted == ()
        assert result.pages_filled == ()
        assert result.pages_failed == ()
        assert result.budget_exhausted is True
        assert result.engine == ENGINE_LOCAL
        assert result.text == "\f"

    def test_negative_budget_behaves_like_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _install(monkeypatch, _FakePages({1: "p1"}))

        result = fill_text_with_ocr(b"pdf-bytes", page_count=1, existing_text="", page_budget=-1)

        assert fake.attempted == []
        assert result.budget_exhausted is True

    def test_budget_zero_on_full_text_document_is_not_exhausted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """没有要 OCR 的页 → 预算耗尽无从谈起，否则上层会误报「还有页没取字」。"""
        _install(monkeypatch, _FakePages({}))

        result = fill_text_with_ocr(b"pdf-bytes", page_count=1, existing_text="甲", page_budget=0)

        assert result.budget_exhausted is False


class TestEngineUnavailable:
    def test_unavailable_returns_existing_text_and_empty_tuples(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """引擎不可用不许抛、也不许假装「没认出字」：上层要据此报灰色「无法核对」。"""
        fake = _install(monkeypatch, _FakePages({}, failures={1: ocr_fill._OcrUnavailable("rapidocr 未安装")}))
        existing = "\f第二页原样"

        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result = fill_text_with_ocr(b"pdf-bytes", page_count=2, existing_text=existing)

        assert result.engine == ENGINE_UNAVAILABLE
        assert result.text == existing
        assert result.pages_attempted == ()
        assert result.pages_filled == ()
        assert result.pages_failed == ()
        assert result.budget_exhausted is False
        assert fake.attempted == [1]
        assert "引擎不可用" in caplog.text
        assert "rapidocr 未安装" in caplog.text

    def test_service_acquisition_failure_maps_to_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``_ocr_service`` 的 import / 初始化失败必须翻译成 _OcrUnavailable，而不是单页失败。"""
        from apps.core.interfaces import ServiceLocator

        def _raise_import_error() -> Any:
            raise ImportError("No module named 'rapidocr'")

        monkeypatch.setattr(ServiceLocator, "get_ocr_service", _raise_import_error)

        with pytest.raises(ocr_fill._OcrUnavailable, match="OCR 服务不可用"):
            ocr_fill._ocr_service()

    def test_unavailable_after_a_successful_page_is_a_single_page_failure(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """已经有过跑通的页 → 引擎显然是活的，这一页只算单页失败，不许整轮判不可用。"""
        fake = _install(
            monkeypatch,
            _FakePages({1: "p1", 3: "p3"}, failures={2: ocr_fill._OcrUnavailable("会话被回收")}),
        )

        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result = fill_text_with_ocr(b"pdf-bytes", page_count=3, existing_text="")

        assert fake.attempted == [1, 2, 3]
        assert result.engine == ENGINE_LOCAL
        assert result.pages_filled == (1, 3)
        assert result.pages_failed == (2,)
        assert _segments(result) == ["p1", "", "p3"]


class TestSinglePageFailure:
    def test_one_failing_page_does_not_stop_the_others(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _install(
            monkeypatch,
            _FakePages({1: "p1", 3: "p3"}, failures={2: RuntimeError("第 2 页渲染失败")}),
        )

        result = fill_text_with_ocr(b"pdf-bytes", page_count=3, existing_text="")

        assert fake.attempted == [1, 2, 3]
        assert result.pages_attempted == (1, 2, 3)
        assert result.pages_filled == (1, 3)
        assert result.pages_failed == (2,)
        assert result.engine == ENGINE_LOCAL
        assert _segments(result) == ["p1", "", "p3"]

    def test_render_failure_of_a_broken_pdf_is_not_raised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """真实渲染路径：非 PDF 字节 → pymupdf 抛 RuntimeError → 只记单页失败，不冒泡。"""
        monkeypatch.setattr(ocr_fill, "_ocr_service", lambda: pytest.fail("不该走到引擎"))

        result = fill_text_with_ocr(b"not a pdf at all", page_count=2, existing_text="")

        assert result.pages_attempted == (1, 2)
        assert result.pages_filled == ()
        assert result.pages_failed == (1, 2)
        assert result.engine == ENGINE_LOCAL
        assert result.text == "\f"


class TestPageAlignment:
    def test_output_has_exactly_page_count_segments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """上层按页下标比对：少一段就整份错位，多出来的段落会顶掉后续页。"""
        _install(monkeypatch, _FakePages({4: "第四页识别文本"}))

        result = fill_text_with_ocr(b"pdf-bytes", page_count=5, existing_text="第一页\f第二页")

        assert len(_segments(result)) == 5
        assert _segments(result) == ["第一页", "第二页", "", "第四页识别文本", ""]

    def test_extra_segments_beyond_page_count_are_dropped(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _install(monkeypatch, _FakePages({}))

        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result = fill_text_with_ocr(b"pdf-bytes", page_count=2, existing_text="甲\f乙\f多出来的一段")

        assert _segments(result) == ["甲", "乙"]
        assert "多于页数" in caplog.text

    def test_zero_page_count_yields_empty_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """docx / 解析不出页数的回传件：没有页网格就什么都不补，也不许凭空造段。"""
        fake = _install(monkeypatch, _FakePages({1: "p1"}))

        result = fill_text_with_ocr(b"docx-bytes", page_count=0, existing_text="正文")

        assert fake.attempted == []
        assert result.text == ""
        assert result.pages_attempted == ()
        assert result.budget_exhausted is False


class TestOcrPageRender:
    def test_page_is_rasterized_to_png_bytes_for_the_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """渲染口径：pymupdf → PNG **字节**交给 ``recognize_bytes``，不落临时文件。"""
        stub = _StubOcrService()
        monkeypatch.setattr(ocr_fill, "_ocr_service", lambda: stub)
        data = _make_blank_pdf(page_count=2)

        text = ocr_fill._ocr_page(data, 2)

        assert text == "识别出来的文本"  # 首尾空白已 strip
        assert len(stub.images) == 1
        assert stub.images[0].startswith(b"\x89PNG")

    def test_render_dpi_matches_the_ocr_handler_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DPI 与 pdf_splitting 的 OCR 默认档（200dpi）对齐：两条 lane 的字不能因分辨率分化。"""
        stub = _StubOcrService()
        monkeypatch.setattr(ocr_fill, "_ocr_service", lambda: stub)
        data = _make_blank_pdf(page_count=1)
        with pymupdf.open(stream=data, filetype="pdf") as document:
            expected_width = round(document.load_page(0).rect.width * ocr_fill.OCR_RENDER_DPI / 72)

        ocr_fill._ocr_page(data, 1)

        assert ocr_fill.OCR_RENDER_DPI == 200
        with Image.open(io.BytesIO(stub.images[0])) as image:
            assert image.size[0] == pytest.approx(expected_width, abs=1)

    def test_page_index_is_one_based(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """1-based 是契约：传 1 渲染第一页；越界抛 ValueError（算单页失败，不整轮崩）。"""
        stub = _StubOcrService()
        monkeypatch.setattr(ocr_fill, "_ocr_service", lambda: stub)
        data = _make_blank_pdf(page_count=2)

        ocr_fill._ocr_page(data, 1)
        with pytest.raises(ValueError, match="页码越界"):
            ocr_fill._ocr_page(data, 3)

        assert len(stub.images) == 1


class TestPageBudgetEnv:
    def test_valid_env_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PAGE_BUDGET_ENV, "3")

        assert ocr_fill._resolve_page_limit() == 3

    @pytest.mark.parametrize("raw", ["", " ", "abc", "3.5", "-1"])
    def test_illegal_env_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        """负数按非法处理：环境变量里的 -1 多半是想写「不限」，那会 OCR 整份卷宗。"""
        monkeypatch.setenv(PAGE_BUDGET_ENV, raw)

        assert ocr_fill._resolve_page_limit() == DEFAULT_OCR_PAGE_LIMIT

    def test_module_default_is_ten_pages(self) -> None:
        # 默认**不设上限**：每一页都要核对（只核前 10 页的结论写不进卷宗）
        assert DEFAULT_OCR_PAGE_LIMIT is None
        assert ocr_fill.OCR_HARD_LIMIT >= 100
