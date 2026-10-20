"""案号正则：机关字号（仲裁委 / 行政机关「代字〔年份〕第N号」）与法院案号并存的回归。

2026-10-20 真机事故：劳动仲裁开庭通知书原文（VLM 输出，无任何分隔）
「…开庭通知书X劳人仲通字〔年份〕第N号案号X劳人仲案字〔年份〕第N号案由…」
被兜底模式按法院结构重拼成「（年份）〕第N号」落库，且选中的还是文首的文号
（通字）而非「案号」标签后的案字；LLM 给出正确值却被「以正则为准」压掉。

本文件全部案号均为虚构夹具（privacy-allow）。
"""

from __future__ import annotations

import pytest

from apps.document_recognition.services._case_number_mixin import CaseNumberMixin

GARBAGE = "（2026）〕第777号"  # privacy-allow 假案号（事故残缺值形状）

# 与真机原文同构的合成文本：标题 + 文号（通字）+「案号」标签 + 案号（案字），全程无分隔
NOTICE_TEXT = (
    "海南省某市劳动人事争议仲裁委员会开庭通知书某劳人仲通字〔2026〕第777号"  # privacy-allow 假案号
    "案号某劳人仲案字〔2026〕第777号案由劳动争议案当事人申请人某某被申请人某公司"  # privacy-allow 假案号
)


@pytest.fixture
def mixin() -> CaseNumberMixin:
    return CaseNumberMixin()


class TestAgencyCaseNumber:
    def test_notice_layout_picks_labeled_case_number_not_doc_number(self, mixin):
        result = mixin._extract_case_number_by_regex(NOTICE_TEXT)
        assert result == "某劳人仲案字〔2026〕第777号"  # privacy-allow 假案号
        assert result != GARBAGE

    def test_doc_number_only_notice_returns_the_doc_number_intact(self, mixin):
        """只有文号没有案号的受理通知：返回唯一候选，但绝不能重拼成法院结构。"""
        text = "某市劳动人事争议仲裁委员会受理通知书某劳人仲通字〔2026〕第12号你方申请已受理"  # privacy-allow 假案号
        assert mixin._extract_case_number_by_regex(text) == "某劳人仲通字〔2026〕第12号"  # privacy-allow 假案号

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("案号：穗劳人仲案〔2024〕第1234号", "穗劳人仲案〔2024〕第1234号"),  # privacy-allow 假案号
            # 无「第」的地区写法原样保留，不擅自补「第」
            ("案号：深劳人仲案〔2024〕1234号", "深劳人仲案〔2024〕1234号"),  # privacy-allow 假案号
            # OCR 把 〔〕 认成半角 / 全角方括号
            ("案号：某劳人仲案字[2026]第777号", "某劳人仲案字〔2026〕第777号"),  # privacy-allow 假案号
            ("案号：某劳人仲案字［2026］第777号", "某劳人仲案字〔2026〕第777号"),  # privacy-allow 假案号
        ],
    )
    def test_agency_variants(self, mixin, text, expected):
        assert mixin._extract_case_number_by_regex(text) == expected

    def test_fallback_pattern_never_rebuilds_agency_number_in_court_shape(self, mixin):
        """兜底模式字符类排除 〔〕：只含机关字号的文本绝不能产出「（年份）…」法院结构的重拼。"""
        for text in (NOTICE_TEXT, "穗劳人仲案〔2024〕第1234号", "某字〔2024〕第1号"):  # privacy-allow 假案号
            result = mixin._extract_case_number_by_regex(text)
            assert result is not None
            assert not result.startswith("（")
            assert "〕" not in result.split("〔", 1)[0]


class TestCourtCaseNumberUnchanged:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("（2023）京0108民初12345号", "（2023）京0108民初12345号"),  # privacy-allow 假案号
            ("(2023)京0108民初12345号", "（2023）京0108民初12345号"),  # privacy-allow 假案号
            ("2023京0108民初12345号", "（2023）京0108民初12345号"),  # privacy-allow 假案号
            # 年份在前的仲裁委写法走法院结构
            ("（2024）京仲案字第0123号", "（2024）京仲案字第0123号"),  # privacy-allow 假案号
        ],
    )
    def test_court_formats(self, mixin, text, expected):
        assert mixin._extract_case_number_by_regex(text) == expected

    def test_reference_penalty_and_label_bonus_pick_own_case_number(self, mixin):
        text = "根据（2025）粤01民初1号判决书，本院定于某日开庭。案号：（2026）粤01民初2号"  # privacy-allow 假案号
        assert mixin._extract_case_number_by_regex(text) == "（2026）粤01民初2号"  # privacy-allow 假案号

    def test_label_bonus_beats_earlier_unlabeled_number(self, mixin):
        """文首另一个未标注的编号位置分更高，「案号」标签仍要赢。"""
        text = "传票（2025）粤01民初9号副本随附。案号：（2026）粤01民初2号"  # privacy-allow 假案号
        assert mixin._extract_case_number_by_regex(text) == "（2026）粤01民初2号"  # privacy-allow 假案号


class TestNormalizeCaseNumber:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # 机关字号：年份括号统一 〔〕（LLM 常回 ()，与正则结果对齐后交叉校验不再误报不一致）
            ("某劳人仲案字(2026)第777号", "某劳人仲案字〔2026〕第777号"),  # privacy-allow 假案号
            ("某劳人仲案字（2026）第777号", "某劳人仲案字〔2026〕第777号"),  # privacy-allow 假案号
            ("某劳人仲案字[2026]第777号", "某劳人仲案字〔2026〕第777号"),  # privacy-allow 假案号
            ("深劳人仲案〔2024〕1234号", "深劳人仲案〔2024〕1234号"),  # privacy-allow 假案号
            # 法院案号：维持全角括号归一
            ("（2023）京0108民初12345号", "（2023）京0108民初12345号"),  # privacy-allow 假案号
            ("(2023)京0108民初12345号", "（2023）京0108民初12345号"),  # privacy-allow 假案号
            ("2023京0108民初12345号", "（2023）京0108民初12345号"),  # privacy-allow 假案号
            ("", ""),
        ],
    )
    def test_normalize(self, mixin, raw, expected):
        assert mixin._normalize_case_number(raw) == expected
