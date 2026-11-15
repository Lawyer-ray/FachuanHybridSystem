"""双引擎**编排**（``dual_engine_runner``）的单测。

判据本身不在这里（在 ``test_dual_engine.py``）。本文件只验编排契约：

· 两个引擎必须**并行**跑（不是串行叠时间）；
· 一个引擎挂了不能拖垮另一个，且单引擎时不产生分歧；
· 只跑指定页时，分歧页码必须是**原卷页码**（不是切出来的小 PDF 的相对页号）；
· 写进 summary 的是纯 JSON（frozen dataclass 必须手动转），键名与前端约定一致；
· 跑哪几个引擎**完全由调用方给的引擎列表决定**，模块里没有任何开关配置；
· 每条分歧都带上两侧的块矩形（前端双框对照靠它画）。

数据一律虚构：张三丰 / 李四 / 示例机构 / 110101199001011234（明显假号）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split import dual_engine_runner as runner

#: 虚构身份证号（明显假号）。放在这里是为了验证「锚点升级为 high」能如实透出。
FAKE_ID_CARD = "110101199001011234"


def _make_pdf(path: Path, page_count: int) -> Path:
    """造一份只有页数、内容无关紧要的 PDF（编排测的是对齐与页码，不是 OCR 质量）。"""
    doc = fitz.open()
    try:
        for index in range(page_count):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 72), f"page {index + 1}")
        path.write_bytes(doc.tobytes())
    finally:
        doc.close()
    return path


class _FakeMineru:
    """MinerU 桩：按上传文件页数返回 layout.pages + 一个带 bbox 的块。

    ``text_by_relative_page`` 用来制造指定页上的特定文本（默认每页同一句）。
    """

    def __init__(self, *, text: str = "借款人：张三丰", text_by_relative_page: dict[int, str] | None = None) -> None:
        self._text = text
        self._by_page = text_by_relative_page or {}
        self.calls = 0

    def parse_document(self, *, file_path: str, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        with fitz.open(file_path) as doc:
            page_count = int(doc.page_count)
        pages = []
        for index in range(page_count):
            relative = index + 1
            pages.append(
                {
                    "page_no": relative,
                    "width": 595,
                    "height": 842,
                    "text": self._by_page.get(relative, self._text),
                }
            )
        # bbox 用 MinerU 真实的**千分比**口径（content_list.json 主路径）：
        # 实测第 31 页那块「地址：顺德区…」就是 [209, 89, 666, 118]。
        # 别写成像素 [72, 60, 400, 90]——那会掩盖「千分比被当成像素除」的 bug。
        blocks = [
            SimpleNamespace(type="text", text=self._by_page.get(1, self._text), bbox=[209, 89, 666, 118], page_no=1)
        ]
        return SimpleNamespace(layout={"pages": pages}, blocks=blocks)


class _FakeVL:
    """PaddleOCR-VL 桩：返回逐页 layoutParsingResults（页号由编排层按下标 +1 推）。"""

    def __init__(self, *, text: str = "借款人：张三半", text_by_relative_page: dict[int, str] | None = None) -> None:
        self._text = text
        self._by_page = text_by_relative_page or {}
        self.calls = 0

    def recognize_bytes(
        self, payload: bytes, *, is_pdf: bool = False, page_count: int | None = None
    ) -> SimpleNamespace:
        self.calls += 1
        with fitz.open(stream=payload, filetype="pdf") as doc:
            actual_count = int(doc.page_count)
        results = []
        for index in range(actual_count):
            relative = index + 1
            results.append(
                {
                    "markdown": {"text": self._by_page.get(relative, self._text)},
                    "prunedResult": {
                        "width": 595,
                        "height": 842,
                        "parsing_res_list": [
                            {
                                "block_label": "text",
                                "block_content": self._by_page.get(relative, self._text),
                                "block_bbox": [72, 60, 400, 90],
                            }
                        ],
                    },
                }
            )
        return SimpleNamespace(text="merged", layout_results=results)


def _factories(mineru: object, vl: object) -> dict[str, object]:
    return {runner.ENGINE_MINERU: lambda: mineru, runner.ENGINE_PADDLEOCR_VL: lambda: vl}


def test_runs_both_engines_in_parallel_not_serially(tmp_path: Path) -> None:
    """两引擎并行：各睡 0.4s 时总耗时明显低于串行的 0.8s。

    用「远小于串行总时长」做判据而不是精确秒数：线程池调度抖动很大，
    断言一个区间才不会在 CI 机器上随机红。
    """

    class _SlowMineru(_FakeMineru):
        def parse_document(self, **kwargs: object) -> SimpleNamespace:
            time.sleep(0.4)
            return super().parse_document(**kwargs)  # type: ignore[arg-type]

    class _SlowVL(_FakeVL):
        def recognize_bytes(self, payload: bytes, **kwargs: object) -> SimpleNamespace:
            time.sleep(0.4)
            return super().recognize_bytes(payload, **kwargs)  # type: ignore[arg-type]

    pdf = _make_pdf(tmp_path / "sample.pdf", 1)

    started = time.monotonic()
    runner.run_dual_engine(pdf, engine_factories=_factories(_SlowMineru(), _SlowVL()))
    elapsed = time.monotonic() - started

    assert elapsed < 0.75, f"看起来是串行跑的：{elapsed:.2f}s"


def test_one_engine_failure_does_not_break_the_other(tmp_path: Path) -> None:
    """VL 构造即失败：MinerU 结果照常返回，且不产生分歧（可比引擎不足 2 个）。"""
    pdf = _make_pdf(tmp_path / "sample.pdf", 3)

    def _boom() -> object:
        raise RuntimeError("PaddleOCR 未配置 API Token")

    outcome = runner.run_dual_engine(
        pdf,
        engine_factories={runner.ENGINE_MINERU: lambda: _FakeMineru(), runner.ENGINE_PADDLEOCR_VL: _boom},
    )

    assert sorted(outcome.engine_pages[runner.ENGINE_MINERU]) == [1, 2, 3]
    assert outcome.engine_pages[runner.ENGINE_PADDLEOCR_VL] == {}
    # 单引擎场景下没有「分歧」这个概念，报任何东西都是噪声
    assert outcome.disagreements == []
    assert outcome.summary[runner.SUMMARY_ENGINE_DISAGREEMENTS] == []

    status = outcome.summary["dual_engine"]["engines"]
    assert status[runner.ENGINE_MINERU]["ok"] is True
    assert status[runner.ENGINE_PADDLEOCR_VL]["ok"] is False
    assert "RuntimeError" in status[runner.ENGINE_PADDLEOCR_VL]["error"]


def test_engine_error_message_is_sanitized(tmp_path: Path) -> None:
    """引擎异常里带 Key 时必须脱敏：summary 会透给前端，密钥不能出现在那里。"""
    pdf = _make_pdf(tmp_path / "sample.pdf", 1)

    def _boom() -> object:
        raise RuntimeError("submit failed: Authorization: Bearer sk-live-123456 api_key=abcd1234")

    outcome = runner.run_dual_engine(
        pdf,
        engine_factories={runner.ENGINE_MINERU: _boom, runner.ENGINE_PADDLEOCR_VL: lambda: _FakeVL()},
    )

    error = outcome.summary["dual_engine"]["engines"][runner.ENGINE_MINERU]["error"]
    assert "sk-live-123456" not in error
    assert "abcd1234" not in error
    assert "***" in error


def test_disagreements_are_json_serializable_with_expected_keys(tmp_path: Path) -> None:
    """分歧 dict 是纯 JSON，且键名/结构与前端约定一致（含 variants 与 label）。"""
    pdf = _make_pdf(tmp_path / "sample.pdf", 1)

    outcome = runner.run_dual_engine(
        pdf,
        engine_factories=_factories(_FakeMineru(text="借款人：张三丰"), _FakeVL(text="借款人：张三半")),
    )

    payload = outcome.summary[runner.SUMMARY_ENGINE_DISAGREEMENTS]
    assert len(payload) == 1
    item = payload[0]
    # blocks 是「双框对照」的坐标（契约要求），另外七个键是判据本身的产物
    assert set(item) == {"page_no", "kind", "severity", "variants", "context", "anchor_hit", "similarity", "blocks"}
    assert item["page_no"] == 1
    assert item["kind"] == "char"
    assert item["severity"] == "medium"
    assert {variant["engine"] for variant in item["variants"]} == {runner.ENGINE_MINERU, runner.ENGINE_PADDLEOCR_VL}
    assert {variant["label"] for variant in item["variants"]} == {"MinerU", "PaddleOCR-VL"}

    # 真序列化一次：summary 会被 json.dumps 写进 job 详情
    assert json.loads(json.dumps(outcome.summary, ensure_ascii=False))


def test_anchor_page_disagreement_is_high_and_counted(tmp_path: Path) -> None:
    """身份证号当页出现时同页单字分歧 → high，并计入 engine_disagree_summary。"""
    pdf = _make_pdf(tmp_path / "sample.pdf", 1)
    mineru_text = f"姓名：张三丰 身份证号：{FAKE_ID_CARD}"
    vl_text = f"姓名：张三半 身份证号：{FAKE_ID_CARD}"

    outcome = runner.run_dual_engine(
        pdf,
        engine_factories=_factories(_FakeMineru(text=mineru_text), _FakeVL(text=vl_text)),
    )

    counts = outcome.summary[runner.SUMMARY_ENGINE_DISAGREE_SUMMARY]
    # 三个桶总是都在，缺的给 0 —— 前端抽屉不用写 ?? 0
    assert counts == {"high": 1, "medium": 0, "low": 0}
    assert outcome.summary[runner.SUMMARY_ENGINE_DISAGREEMENTS][0]["anchor_hit"] is True


def test_partial_pages_report_original_page_numbers(tmp_path: Path) -> None:
    """只跑第 2、4 页时，分歧的 page_no 必须是**原卷页码** 2 / 4，不是相对页号 1 / 2。

    这是试点模式最容易错的一步：切出来的小 PDF 第 1 页在原卷是第 2 页，
    不映射的话律师点开「第 1 页」看到的是封面。
    """
    pdf = _make_pdf(tmp_path / "sample.pdf", 5)

    outcome = runner.run_dual_engine(
        pdf,
        page_numbers=[4, 2],
        engine_factories=_factories(_FakeMineru(), _FakeVL()),
    )

    assert sorted(outcome.engine_pages[runner.ENGINE_MINERU]) == [2, 4]
    assert sorted(outcome.engine_pages[runner.ENGINE_PADDLEOCR_VL]) == [2, 4]
    assert sorted({item["page_no"] for item in outcome.summary[runner.SUMMARY_ENGINE_DISAGREEMENTS]}) == [2, 4]
    assert outcome.summary["dual_engine"]["pages"] == [2, 4]


def test_partial_pages_blocks_are_remapped_too(tmp_path: Path) -> None:
    """块坐标的页码也要一并映射，否则双框会画到错误的页上。"""
    pdf = _make_pdf(tmp_path / "sample.pdf", 5)

    outcome = runner.run_dual_engine(
        pdf,
        page_numbers=[3],
        engine_factories=_factories(_FakeMineru(), _FakeVL()),
    )

    assert [block.page_no for block in outcome.blocks_by_engine[runner.ENGINE_MINERU]] == [3]
    assert [block.page_no for block in outcome.blocks_by_engine[runner.ENGINE_PADDLEOCR_VL]] == [3]


def test_blocks_are_normalized_for_both_engines(tmp_path: Path) -> None:
    """两引擎都要产出归一化块（前端双框对照要求两边都有框）。"""
    pdf = _make_pdf(tmp_path / "sample.pdf", 1)

    outcome = runner.run_dual_engine(pdf, engine_factories=_factories(_FakeMineru(), _FakeVL()))

    mineru_block = outcome.blocks_by_engine[runner.ENGINE_MINERU][0]
    vl_block = outcome.blocks_by_engine[runner.ENGINE_PADDLEOCR_VL][0]
    # MinerU：千分比 [209,89,666,118] / 1000
    assert mineru_block.approx is False
    assert mineru_block.rect == {"x": 0.209, "y": 0.089, "w": 0.457, "h": 0.029}
    # VL：595×842 页面上绝对像素 [72,60,400,90]
    assert vl_block.approx is False
    assert vl_block.rect["x"] == pytest.approx(0.121, abs=0.001)
    for block in (mineru_block, vl_block):
        assert set(block.rect) == {"x", "y", "w", "h"}


def test_engine_returning_no_pages_is_treated_as_failure(tmp_path: Path) -> None:
    """解析「成功」但一页都没出来 → 记成失败，不能静默变成「没有分歧」。"""

    class _EmptyMineru(_FakeMineru):
        def parse_document(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(layout={"pages": []}, blocks=[])

    pdf = _make_pdf(tmp_path / "sample.pdf", 2)

    outcome = runner.run_dual_engine(pdf, engine_factories=_factories(_EmptyMineru(), _FakeVL()))

    status = outcome.summary["dual_engine"]["engines"][runner.ENGINE_MINERU]
    assert status["ok"] is False
    assert status["error"]


def test_single_engine_never_reports_disagreements(tmp_path: Path) -> None:
    """只给一个引擎也能跑，但没有「分歧」这个概念（可比引擎不足 2 个）。"""
    pdf = _make_pdf(tmp_path / "sample.pdf", 2)

    outcome = runner.run_dual_engine(pdf, engine_factories={runner.ENGINE_MINERU: lambda: _FakeMineru()})

    assert sorted(outcome.engine_pages[runner.ENGINE_MINERU]) == [1, 2]
    assert outcome.disagreements == []
    assert outcome.summary[runner.SUMMARY_ENGINE_DISAGREE_SUMMARY] == {"high": 0, "medium": 0, "low": 0}


def test_runner_reads_no_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """本模块不再有任何「开关 / 页码」配置入口：开了双引擎是任务输入，不是部署配置。

    这条断言的意义是防回流：早先那版用 ``PDF_SPLIT_DUAL_ENGINE`` 环境变量控制，
    用户明确要求改成「下拉菜单勾选」。再把开关加回来应该在调用方（任务字段
    ``PdfSplitJob.dual_engines``），不在这里。
    """
    assert not hasattr(runner, "dual_engine_enabled")
    assert not hasattr(runner, "dual_engine_pages")
    assert not hasattr(runner, "ENV_DUAL_ENGINE_ENABLED")

    # 环境里写着「开着 + 只跑第 1 页」，实际行为必须完全不受影响：两页都跑
    monkeypatch.setenv("PDF_SPLIT_DUAL_ENGINE", "1")
    monkeypatch.setenv("PDF_SPLIT_DUAL_ENGINE_PAGES", "1")
    pdf = _make_pdf(tmp_path / "sample.pdf", 2)

    outcome = runner.run_dual_engine(pdf, engine_factories={runner.ENGINE_MINERU: lambda: _FakeMineru()})

    assert sorted(outcome.engine_pages[runner.ENGINE_MINERU]) == [1, 2]


def test_plan_maps_selected_engines_and_reports_unsupported() -> None:
    """勾选的引擎 → 工厂字典；还不支持的引擎要**明说**，不能静默丢掉。"""
    factories, unavailable = runner.plan_dual_engine_factories(["MinerU", "paddleocr_vl", "textin", "bogus"])

    assert list(factories) == [runner.ENGINE_MINERU, runner.ENGINE_PADDLEOCR_VL]
    # 用户以为勾了三个引擎 → summary 里必须能看出哪两个真跑了
    assert unavailable == ["textin", "bogus"]


def test_plan_keeps_selection_order_and_dedupes() -> None:
    """顺序是语义（前一个是主引擎）：去重但不排序。"""
    factories, unavailable = runner.plan_dual_engine_factories(["paddleocr_vl", "mineru", "mineru", " "])

    assert list(factories) == [runner.ENGINE_PADDLEOCR_VL, runner.ENGINE_MINERU]
    assert unavailable == []


def test_paddleocr_slot_is_locked_to_vl_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """PaddleOCR 槽位固定用 ``paddleocr_vl_1_6``，不受配置里的默认模型影响。

    配置默认值可能是 PP-OCRv5（纯文字 OCR，不出逐页版面）：拿它当第二引擎
    既拿不到页码也拿不到 bbox，双框对照做不成。所以这里断言**构造参数**本身。
    """
    from apps.automation.services.ocr import paddleocr_api_service

    seen: list[str | None] = []
    real_engine = paddleocr_api_service.PaddleOCRApiEngine

    def _spy(model: str | None = None, timeout: float | None = None) -> object:
        seen.append(model)
        return real_engine(model=model, timeout=timeout)

    monkeypatch.setattr(paddleocr_api_service, "PaddleOCRApiEngine", _spy)

    factories, _unavailable = runner.plan_dual_engine_factories([runner.ENGINE_PADDLEOCR_VL])
    assert runner.PADDLEOCR_VL_MODEL == "paddleocr_vl_1_6"
    factories[runner.ENGINE_PADDLEOCR_VL]()

    assert seen == ["paddleocr_vl_1_6"]


def test_disagreements_carry_block_rects_for_double_box(tmp_path: Path) -> None:
    """每条分歧挂上两引擎各自的块矩形——前端「双框对照」读的就是 ``blocks``。

    坐标口径必须与 ``PositionedBlockOut.rect`` 一致（归一化 0-1），否则两个框
    会画在不同的比例尺上，「两框重叠时都可见」就无从谈起。
    """
    pdf = _make_pdf(tmp_path / "sample.pdf", 1)

    outcome = runner.run_dual_engine(
        pdf,
        engine_factories=_factories(_FakeMineru(text="借款人：张三丰"), _FakeVL(text="借款人：张三半")),
    )

    item = outcome.summary[runner.SUMMARY_ENGINE_DISAGREEMENTS][0]
    blocks = item["blocks"]
    assert {block["engine"] for block in blocks} == {runner.ENGINE_MINERU, runner.ENGINE_PADDLEOCR_VL}
    for block in blocks:
        assert block["page_no"] == 1
        assert set(block["rect"]) == {"x", "y", "w", "h"}
        assert block["approx"] is False
        assert block["block_type"]


def test_no_block_rects_key_when_nothing_can_be_linked() -> None:
    """匹配不上就**不写** ``blocks`` 键：宁可只画一个框，也不要把框画到不相干处。"""
    payload = runner.disagreements_to_dicts([])
    assert payload == []

    from apps.pdf_splitting.services.split.dual_engine import (
        ENGINE_MINERU,
        KIND_CHAR,
        SEVERITY_MEDIUM,
        EngineDisagreement,
        EngineVariant,
    )

    item = EngineDisagreement(
        page_no=1,
        kind=KIND_CHAR,
        severity=SEVERITY_MEDIUM,
        variants=[EngineVariant(engine=ENGINE_MINERU, text="不存在的块")],
        context="不存在的块",
    )
    assert "blocks" not in runner.disagreements_to_dicts([item])[0]
