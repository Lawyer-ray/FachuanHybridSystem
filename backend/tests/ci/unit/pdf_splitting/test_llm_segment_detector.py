"""Tests for pdf_splitting LLM 分段（方案二）：prompt 构造 / JSON 解析校验 / 规则引擎降级。"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
from apps.pdf_splitting.services.split.llm_segment_detector import (
    LLMSegmentDetector,
    build_page_digests,
    build_user_prompt,
    parse_llm_segments,
)
from apps.pdf_splitting.services.split.service import PdfSplitService
from apps.pdf_splitting.services.split.split_models import PageDescriptor

TEMPLATE_KEY = "filing_materials_v1"


def _page(
    page_no: int,
    text: str = "",
    *,
    ocr_failed: bool = False,
    layout_title: str = "",
    top_candidates: list[dict[str, Any]] | None = None,
) -> PageDescriptor:
    return PageDescriptor(
        page_no=page_no,
        text=text,
        normalized_text=text,
        head_text=text[:240],
        source_method="ocr" if text else "ocr_failed",
        ocr_failed=ocr_failed,
        top_candidates=top_candidates or [],
        layout=None,
        layout_title=layout_title,
    )


def _seg_json(
    page_start: int,
    page_end: int,
    seg_type: str = "complaint",
    label: str = "",
    confidence: float | None = 0.9,
) -> str:
    item = f'{{"page_start": {page_start}, "page_end": {page_end}, "type": "{seg_type}", "label": "{label}"'
    if confidence is not None:
        item += f', "confidence": {confidence}'
    return item + "}"


class _StubLLM:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> _StubLLM:
        self.calls.append({"messages": messages, **kwargs})
        return self


class _RaisingDetector:
    def detect(self, pages: list[PageDescriptor], *, template_key: str) -> list[Any]:
        raise RuntimeError("供给不可用")


class TestPageDigests:
    def test_标题行优先并标注取字失败页(self) -> None:
        pages = [
            _page(1, "民事起诉状原告张三", layout_title="民事起诉状"),
            _page(2, ocr_failed=True),
        ]
        digests = build_page_digests(pages)
        assert digests[0] == "【第1页｜标题：民事起诉状】\n民事起诉状原告张三"
        assert digests[1] == "【第2页】（未取到文字）"

    def test_保留行结构_换行不被剥掉(self) -> None:
        """规则 3 要看「落款/此致/具状人」这类**行级**信号，换行剥光就判不了。"""
        text = "民事起诉状\n诉讼请求：判令被告还款\n事实与理由：双方签订借款合同\n此致\n某人民法院\n具状人：甲某\n2024年1月1日"
        digest = build_page_digests([_page(1, text)])[0]
        assert digest == f"【第1页】\n{text}"

    def test_尾部收尾信号行不会被截掉(self) -> None:
        """长页中略时，尾窗必须保住收尾信号——这是边界判据的命门。"""
        body = [f"第{i}条 合同正文条款内容填充" for i in range(1, 41)]
        tail = ["此致", "某人民法院", "具状人：甲某", "2024年1月1日"]
        digest = build_page_digests([_page(9, "\n".join(body + tail))])[0]
        for signal in tail:
            assert signal in digest, f"收尾信号行被截掉了：{signal}"
        assert "（中略 28 行）" in digest  # 44 行 - 首 10 - 尾 6
        assert digest.endswith("2024年1月1日")

    def test_首窗保住标题行(self) -> None:
        lines = ["民事起诉状", "原告：甲某", "被告：乙某"] + [f"正文第{i}行" for i in range(30)]
        digest = build_page_digests([_page(1, "\n".join(lines))])[0]
        assert digest.startswith("【第1页】\n民事起诉状\n原告：甲某\n被告：乙某")

    def test_短页整页直出不省略(self) -> None:
        body = "\n".join(f"第{i}行" for i in range(1, 17))  # 恰好 16 行 = 首 10 + 尾 6
        assert build_page_digests([_page(3, body)])[0] == f"【第3页】\n{body}"

    def test_拍平成一行的表格页_首窗保行头尾窗保行尾(self) -> None:
        """引擎会把整张表拍成一行（实测单行 18516 字），两端都要看得到。"""
        head_monster = "表头交易日期对方账号金额" + "中" * 5000
        tail_monster = "中" * 5000 + "表尾合计余额12345.67"
        text = "\n".join([head_monster] + [f"第{i}行" for i in range(12)] + [tail_monster])
        digest = build_page_digests([_page(5, text)])[0]
        assert "表头交易日期对方账号金额" in digest  # 首窗长行保行头
        assert digest.endswith("表尾合计余额12345.67")  # 尾窗长行保行尾
        assert len(digest) < 1200  # 单行上限兜住，不让一行吃掉整批预算

    def test_纯html标签行不进窗口(self) -> None:
        text = '民事起诉状\n<div style="text-align: center;"><img src="imgs/a.jpg" /></div>\n此致'
        digest = build_page_digests([_page(1, text)])[0]
        assert "<img" not in digest
        assert digest == "【第1页】\n民事起诉状\n此致"

    def test_上下文页逐页标注(self) -> None:
        pages = [_page(1, "上一页收尾"), _page(2, "本批首页"), _page(3, "本批第二页")]
        digests = build_page_digests(pages, context_pages=1)
        assert digests[0].startswith("【第1页·上下文】")
        assert digests[1].startswith("【第2页】")
        assert "·上下文" not in digests[2]

    def test_user_prompt_含页数类型键与逐页摘要(self) -> None:
        prompt = build_user_prompt([_page(1, "起诉状内容"), _page(2, "证据清单内容")], template_key=TEMPLATE_KEY)
        assert "共 2 页" in prompt
        assert "- complaint：起诉状" in prompt
        assert "- other：其他材料" in prompt
        assert "【第1页】\n起诉状内容" in prompt
        assert "【第2页】\n证据清单内容" in prompt

    def test_user_prompt_列出开放命名高频材料(self) -> None:
        """转账回单/借条这类枚举外材料要给准确开放名，而不是硬塞既有键名。"""
        prompt = build_user_prompt([_page(1, "转账回单")], template_key=TEMPLATE_KEY)
        assert "转账回单" in prompt
        assert "借条" in prompt

    def test_user_prompt_明确上下文页不产出分段(self) -> None:
        pages = [_page(i, f"第{i}页正文") for i in range(1, 6)]
        prompt = build_user_prompt(pages, template_key=TEMPLATE_KEY, context_pages=2)
        assert "第 1 到第 2 页标为「上下文页」" in prompt
        assert "不要为它们产出分段" in prompt
        assert "第 3 页到第 5 页" in prompt


class TestBoundaryReviewPrompt:
    def test_两侧整页全文与边界页号都进prompt(self) -> None:
        from apps.pdf_splitting.services.split.llm_segment_detector import build_boundary_review_prompt

        prompt = build_boundary_review_prompt(
            left_page=125,
            right_page=126,
            left_text="5.3 抵押担保的范围为…提前还款补偿",
            right_text="金、损害赔偿金和实现债权及抵押权的费用。",
        )
        assert "第 125 页" in prompt and "第 126 页" in prompt
        assert "5.3 抵押担保的范围为…提前还款补偿" in prompt
        assert "金、损害赔偿金和实现债权及抵押权的费用。" in prompt

    def test_超长页截尾并标注(self) -> None:
        from apps.pdf_splitting.services.split.llm_segment_detector import build_boundary_review_prompt

        prompt = build_boundary_review_prompt(left_page=1, right_page=2, left_text="字" * 9000, right_text="短")
        assert "本页过长，后续省略" in prompt
        assert len(prompt) < 9000

    def test_空页标注未取到文字(self) -> None:
        from apps.pdf_splitting.services.split.llm_segment_detector import build_boundary_review_prompt

        assert "（未取到文字）" in build_boundary_review_prompt(left_page=1, right_page=2, left_text="", right_text="x")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"action": "merge", "reason": "半句话跨页"}', "merge"),
            ('```json\n{"action": "KEEP"}\n```', "keep"),
            ('{"action": "move_left"}', "move_left"),
            ('{"action": "move_right"}', "move_right"),
            ('{"action": "split_more"}', None),
            ('{"action": ""}', None),
            ("不是 JSON", None),
            ('["merge"]', None),
        ],
    )
    def test_非法或未知动作一律None(self, raw: str, expected: str | None) -> None:
        from apps.pdf_splitting.services.split.llm_segment_detector import parse_boundary_verdict

        assert parse_boundary_verdict(raw) == expected


class TestParseLlmSegments:
    def test_正常输出_类型映射与开放命名(self) -> None:
        raw = (
            '{"segments": ['
            + _seg_json(1, 3, "complaint", "民事起诉状", 0.95)
            + ", "
            + _seg_json(4, 10, "other", "借条", 0.7)
            + "]}"
        )
        drafts = parse_llm_segments(raw, total_pages=10, template_key=TEMPLATE_KEY)
        assert len(drafts) == 2
        first, second = drafts
        assert (first.page_start, first.page_end, first.segment_type) == (1, 3, PdfSplitSegmentType.COMPLAINT)
        assert first.filename == "民事起诉状.pdf"
        assert first.source_method == "llm"
        assert first.review_flag == PdfSplitReviewFlag.NORMAL
        assert first.confidence == 0.95
        # other → unrecognized + 开放命名落在 filename，标记低置信度复核
        assert (second.segment_type, second.filename) == (PdfSplitSegmentType.UNRECOGNIZED, "借条.pdf")
        assert second.review_flag == PdfSplitReviewFlag.LOW_CONFIDENCE
        assert [d.order for d in drafts] == [1, 2]

    def test_代码块围栏与裸数组都能解析(self) -> None:
        fenced = "```json\n[" + _seg_json(1, 2) + "]\n```"
        assert len(parse_llm_segments(fenced, total_pages=2, template_key=TEMPLATE_KEY)) == 1
        bare = "[" + _seg_json(1, 2) + "]"
        assert len(parse_llm_segments(bare, total_pages=2, template_key=TEMPLATE_KEY)) == 1

    def test_重叠区间被钳位_钳位后倒置的丢弃(self) -> None:
        raw = "[" + _seg_json(1, 5) + ", " + _seg_json(4, 8) + ", " + _seg_json(6, 6) + "]"
        drafts = parse_llm_segments(raw, total_pages=8, template_key=TEMPLATE_KEY)
        spans = [(d.page_start, d.page_end) for d in drafts]
        assert spans == [(1, 5), (6, 8)]  # 第三段 6-6 被第二段吞没后丢弃，末段并到 8

    def test_页码越界钳位(self) -> None:
        raw = "[" + _seg_json(0, 99, "evidence_list", "证据清单") + "]"
        drafts = parse_llm_segments(raw, total_pages=10, template_key=TEMPLATE_KEY)
        assert (drafts[0].page_start, drafts[0].page_end) == (1, 10)

    def test_未覆盖区间由gap补片兜底(self) -> None:
        raw = "[" + _seg_json(3, 4, "complaint", "起诉状") + "]"
        drafts = parse_llm_segments(raw, total_pages=6, template_key=TEMPLATE_KEY)
        spans = [(d.page_start, d.page_end, d.source_method) for d in drafts]
        assert spans == [
            (1, 2, "gap_fill"),
            (3, 4, "llm"),
            (5, 6, "gap_fill"),
        ]
        assert drafts[0].segment_type == PdfSplitSegmentType.UNRECOGNIZED
        assert drafts[0].review_flag == PdfSplitReviewFlag.UNRECOGNIZED

    def test_置信度钳位与缺省(self) -> None:
        raw = "[" + _seg_json(1, 1, confidence=1.7) + ", " + _seg_json(2, 2, confidence=None) + "]"
        drafts = parse_llm_segments(raw, total_pages=2, template_key=TEMPLATE_KEY)
        assert drafts[0].confidence == 1.0
        assert drafts[1].confidence == 0.5  # 缺省
        assert drafts[1].review_flag == PdfSplitReviewFlag.LOW_CONFIDENCE  # < 0.6

    def test_label缺省回退模板标签或区间名(self) -> None:
        raw = "[" + _seg_json(1, 2, "evidence_list", "") + ", " + _seg_json(3, 3, "other", "") + "]"
        drafts = parse_llm_segments(raw, total_pages=3, template_key=TEMPLATE_KEY)
        assert drafts[0].filename == "证据清单及明细.pdf"
        assert drafts[1].filename == "材料_3-3.pdf"

    @pytest.mark.parametrize(
        "raw",
        [
            "这不是 JSON",
            '{"segments": []}',
            '{"segments": "oops"}',
            '[{"page_start": "x", "page_end": 2}]',
            "[]",
        ],
    )
    def test_非法输出抛ValueError供上层降级(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_llm_segments(raw, total_pages=5, template_key=TEMPLATE_KEY)


class TestDetectorDetect:
    def test_端到端_stub_供给返回分段并透传调用参数(self) -> None:
        stub = _StubLLM("[" + _seg_json(1, 2, "complaint", "起诉状", 0.9) + "]")
        detector = LLMSegmentDetector(llm_service=stub)
        drafts = detector.detect([_page(1, "起诉状"), _page(2, "续页")], template_key=TEMPLATE_KEY)
        assert len(drafts) == 1
        assert drafts[0].filename == "起诉状.pdf"
        assert stub.calls and stub.calls[0]["temperature"] == 0.1
        assert stub.calls[0]["messages"][0]["role"] == "system"

    def test_空页面抛错(self) -> None:
        with pytest.raises(Exception):
            LLMSegmentDetector(llm_service=_StubLLM("[]")).detect([], template_key=TEMPLATE_KEY)

    def test_供给异常向上传播(self) -> None:
        class _Boom:
            def chat(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("gateway down")

        with pytest.raises(RuntimeError, match="gateway down"):
            LLMSegmentDetector(llm_service=_Boom()).detect([_page(1, "x")], template_key=TEMPLATE_KEY)

    def test_硬时限墙_挂死的调用按超时抛错(self) -> None:
        import time

        class _Hang:
            def chat(self, *args: Any, **kwargs: Any) -> Any:
                time.sleep(5)
                return self

        detector = LLMSegmentDetector(llm_service=_Hang(), wall_timeout_seconds=0.2)
        with pytest.raises(Exception, match="超时"):
            detector.detect([_page(1, "x")], template_key=TEMPLATE_KEY)


class TestBoundaryReview:
    """二审必须「失败即保持原边界」：返回 None 表示未复核，不是 keep。"""

    def test_合法动作透传(self) -> None:
        stub = _StubLLM('{"action": "merge", "reason": "半句话跨页"}')
        detector = LLMSegmentDetector(llm_service=stub)
        action = detector.review_boundary(left_page=125, right_page=126, left_text="…补偿", right_text="金、损害赔偿金")
        assert action == "merge"
        # 二审只读两页、只输出一个动作，预算比主分段小一个量级
        assert stub.calls[0]["max_tokens"] == 600
        assert stub.calls[0]["timeout_seconds"] == 60
        # wall_timeout_seconds 是墙的参数，不能转发给 chat()
        assert "wall_timeout_seconds" not in stub.calls[0]

    def test_供给异常返回None而不是乱切(self) -> None:
        class _Boom:
            def chat(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("gateway down")

        detector = LLMSegmentDetector(llm_service=_Boom())
        assert detector.review_boundary(left_page=1, right_page=2, left_text="a", right_text="b") is None

    def test_非法输出返回None(self) -> None:
        detector = LLMSegmentDetector(llm_service=_StubLLM("我觉得应该合并"))
        assert detector.review_boundary(left_page=1, right_page=2, left_text="a", right_text="b") is None

    def test_挂死按二审自己的短墙超时返回None(self) -> None:
        import time

        from apps.pdf_splitting.services.split import llm_segment_detector as mod

        class _Hang:
            def chat(self, *args: Any, **kwargs: Any) -> Any:
                time.sleep(5)
                return self

        detector = LLMSegmentDetector(llm_service=_Hang())
        with patch.object(mod, "_BOUNDARY_REVIEW_WALL_SECONDS", 0.2):
            assert detector.review_boundary(left_page=1, right_page=2, left_text="a", right_text="b") is None


class TestServiceFallback:
    def test_llm失败降级规则引擎并记录原因(self) -> None:
        pages = [
            _page(
                1,
                "民事起诉状",
                top_candidates=[
                    {
                        "segment_type": PdfSplitSegmentType.COMPLAINT,
                        "label": "起诉状",
                        "score": 0.8,
                        "matched_strong": ["起诉状"],
                        "matched_weak": [],
                    }
                ],
            ),
            _page(
                2,
                "证据清单",
                top_candidates=[
                    {
                        "segment_type": PdfSplitSegmentType.EVIDENCE_LIST,
                        "label": "证据清单及明细",
                        "score": 0.7,
                        "matched_strong": ["证据清单"],
                        "matched_weak": [],
                    }
                ],
            ),
        ]
        service = PdfSplitService(llm_segment_detector=_RaisingDetector())
        drafts, summary = service._detect_segments_with_fallback(pages, template_key=TEMPLATE_KEY)
        assert summary["segment_backend"] == "rule"
        assert "RuntimeError" in summary["segment_llm_fallback_reason"]
        assert drafts and all(d.source_method != "llm" for d in drafts)

    def test_llm成功时summary记录llm后端(self) -> None:
        class _OkDetector:
            def detect(self, pages: list[PageDescriptor], *, template_key: str) -> list[Any]:
                return parse_llm_segments(
                    "[" + _seg_json(1, len(pages), "complaint", "起诉状", 0.9) + "]",
                    total_pages=len(pages),
                    template_key=template_key,
                )

        service = PdfSplitService(llm_segment_detector=_OkDetector())
        drafts, summary = service._detect_segments_with_fallback([_page(1, "起诉状")], template_key=TEMPLATE_KEY)
        # summary 还带分批口径（segment_total_batches / segment_rule_batches），
        # 供前端提示「N 批其实是规则切的」，这里只锁后端与降级原因两个键。
        assert summary["segment_backend"] == "llm"
        assert summary["segment_llm_fallback_reason"] == ""
        assert summary["segment_rule_batches"] == 0
        assert drafts[0].source_method == "llm"
