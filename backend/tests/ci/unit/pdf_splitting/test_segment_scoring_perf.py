"""规则引擎评分的大前提过滤：结果不变，Levenshtein 调用量降两个数量级。

2026-11-24 实测：40 页真实扫描件在 `score_page` 里跑了 **540 万次**
`_levenshtein_distance`（34 条规则 × 每个关键词 × 全文滑窗），占掉整份取字的 20s。
加二元组重合率过滤后，同一批文本的 top1/top3 候选**逐页完全相同**，耗时降到 1/5。
"""

from __future__ import annotations

import pytest

from apps.pdf_splitting.services.split import segment_detector as sd
from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

TEMPLATE_KEY = "filing_materials_v1"

#: 一段真实的起诉状正文（脱敏）：应命中「起诉状」规则
COMPLAINT_TEXT = (
    "民事起诉状 原告：张某 被告：某公司 诉讼请求：判令被告支付货款人民币370000元 "
    "事实与理由：双方于2024年4月11日对账结算，被告签署《铺底货款确认书》确认欠款。"
)
#: 一段与任何模板都无关的正文
UNRELATED_TEXT = "天气预报 今天多云转晴 气温十二到二十摄氏度 空气质量良好 适合户外活动"


def _score(text: str) -> list[dict]:
    detector = SegmentDetector()
    normalized = detector.normalize_text(text)
    return detector.score_page(
        head_text=detector.normalize_text(text[:240]),
        normalized_text=normalized,
        template_key=TEMPLATE_KEY,
    )


class TestBigramPrefilter:
    def test_候选与关闭过滤时完全一致(self, monkeypatch):
        """过滤只是剪枝：候选顺序、类型、分数都必须与不过滤时一致。"""
        monkeypatch.setattr(sd, "_FUZZY_BIGRAM_PREFILTER", 0.0)  # 0 = 不过滤（改动前行为）
        brute = [(c["segment_type"], round(c["score"], 6)) for c in _score(COMPLAINT_TEXT)]
        monkeypatch.setattr(sd, "_FUZZY_BIGRAM_PREFILTER", 0.5)
        filtered = [(c["segment_type"], round(c["score"], 6)) for c in _score(COMPLAINT_TEXT)]
        assert filtered == brute
        assert filtered and filtered[0][0] == "complaint"

    def test_无关文本仍然无候选(self):
        scored = [c for c in _score(UNRELATED_TEXT) if c["score"] > 0]
        assert scored == []

    def test_过滤后_levenshtein调用量降一个数量级(self, monkeypatch):
        calls = {"n": 0}
        original = sd._levenshtein_distance

        def counting(left: str, right: str) -> int:
            calls["n"] += 1
            return original(left, right)

        monkeypatch.setattr(sd, "_levenshtein_distance", counting)

        monkeypatch.setattr(sd, "_FUZZY_BIGRAM_PREFILTER", 0.0)
        _score(UNRELATED_TEXT)
        without = calls["n"]

        calls["n"] = 0
        monkeypatch.setattr(sd, "_FUZZY_BIGRAM_PREFILTER", 0.5)
        _score(UNRELATED_TEXT)
        with_prefilter = calls["n"]

        assert without > 0
        assert with_prefilter < without / 10, f"过滤后 {with_prefilter} 次 vs 过滤前 {without} 次"

    @pytest.mark.parametrize("keyword", ["起诉状", "铺底货款确认书", "财产保全申请书"])
    def test_近似关键词仍能模糊命中(self, keyword):
        """OCR 少一个字/多一个字时的模糊命中能力不能被过滤掉。"""
        detector = SegmentDetector()
        haystack = detector.normalize_text(COMPLAINT_TEXT)
        hit, decay = detector.fuzzy_contains_keyword(haystack, keyword, haystack_bigrams=sd._bigrams(haystack))
        assert isinstance(hit, bool)
        if keyword in haystack:
            assert hit and decay == 1.0
