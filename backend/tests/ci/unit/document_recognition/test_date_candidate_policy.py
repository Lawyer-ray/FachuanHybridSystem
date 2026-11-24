"""date_candidate_policy 纯函数单测（不碰数据库、不依赖 Django）。

这一层负责三件以前塌缩成一个 ``confidence`` 数字的事：

1. 这份文书到底承不承载本案期限（``classify_document_role``）；
2. 期限句的起算锚指向谁（``parse_anchor_clause``）；
3. 该留还是该丢、能不能默认勾（``decide_candidate``）。

事故背景见 ``docs/analysis/date-candidate-provenance-2026-11-24/SUMMARY.md``：
一份《诉讼权利义务告知书》里的「至迟应在裁判文书送达之日起三日内提出」
被按「收到告知书 + 3 天」算成 2026-11-27，打上 85% 并默认勾选。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from apps.document_recognition.services.date_candidate_policy import (
    FLAG_ANCHOR_EFFECTIVE,
    FLAG_GENERIC_BOILERPLATE,
    FLAG_LOW_CONFIDENCE,
    AnchorDocument,
    AnchorKind,
    AnchorVerdict,
    DocumentRole,
    anchor_note_for,
    classify_document_role,
    confidence_for,
    decide_candidate,
    find_issue_date,
    has_concrete_issue_date,
    is_optional_motion,
    parse_anchor_clause,
)

TODAY = date(2026, 11, 24)


def _verdict(sentence: str, core: str, **kwargs: object) -> AnchorVerdict:
    """按"某段话在句中的位置"调用 parse_anchor_clause（模拟调用方）。"""
    start = sentence.index(core)
    return parse_anchor_clause(
        sentence=sentence,
        match_start=start,
        match_end=start + len(core),
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 落款日期：区分「本案专属」与「通用模板」
# ---------------------------------------------------------------------------


class TestIssueDate:
    def test_arabic_and_chinese_both_recognized(self) -> None:
        assert find_issue_date("打印日期：2026年11月24日") == datetime(2026, 11, 24)
        assert find_issue_date("落款：二〇二六年十一月二十四日") == datetime(2026, 11, 24)

    def test_takes_last_occurrence(self) -> None:
        text = "开庭日 2026年10月10日，打印日期：2026年11月11日"
        assert find_issue_date(text) == datetime(2026, 11, 11)

    def test_blank_placeholder_is_not_a_date(self) -> None:
        """通用模板文末是裸「年月日」，不能当落款日。"""
        assert find_issue_date("如不服本判决…特此告知。年月日") is None
        assert has_concrete_issue_date("特此告知。年月日") is False

    def test_out_of_range_year_rejected(self) -> None:
        assert find_issue_date("落款：1999年1月1日") is None


# ---------------------------------------------------------------------------
# 文书角色
# ---------------------------------------------------------------------------


class TestDocumentRole:
    def test_generic_notice_without_issue_date(self) -> None:
        text = "诉讼权利义务告知书一、当事人的诉讼权利1.原告有向法院提起诉讼的权利。年月日"
        role, reason = classify_document_role(text=text)
        assert role is DocumentRole.GENERIC_NOTICE
        assert "告知书" in reason

    def test_generic_notice_keyword_in_filename_only(self) -> None:
        """法院把归档名写成「告知书（…）.pdf」，标题区也就只有「告知书」。"""
        text = "告知书一、当事人的诉讼权利…特此告知。年月日"
        role, _ = classify_document_role(text=text, filename="告知书（某案）_20261124收.pdf")
        assert role is DocumentRole.GENERIC_NOTICE

    def test_carrier_by_issue_date(self) -> None:
        text = "案件受理费请你方于收到本通知次日起七日内向本院交纳。二〇二六年十一月二十四日"
        role, reason = classify_document_role(text=text)
        assert role is DocumentRole.CARRIER
        assert "落款日期" in reason

    def test_carrier_by_title_even_with_blank_date(self) -> None:
        """传票/判决书/举证通知书哪怕落款被 OCR 吃掉，也一定是本案文书。"""
        role, _ = classify_document_role(text="举证通知书 根据民事诉讼法…举证期限为十五日。年月日")
        assert role is DocumentRole.CARRIER

    def test_body_words_do_not_count_as_title(self) -> None:
        """正文里的「财产保全」「调解书」不能被当成标题命中（实测误判点）。"""
        text = "诉讼权利义务告知书1.有申请财产保全、证据保全的权利；2.有请求调解的权利。年月日"
        role, _ = classify_document_role(text=text)
        assert role is DocumentRole.GENERIC_NOTICE


# ---------------------------------------------------------------------------
# 锚点归属（治本的那道闸）
# ---------------------------------------------------------------------------


class TestAnchorOwnership:
    def test_self_notice(self) -> None:
        verdict = _verdict("保全费请你方于收到本通知次日起两日内向本院交纳", "收到本通知次日起两日内")
        assert verdict.document is AnchorDocument.SELF
        assert verdict.kind is AnchorKind.SERVICE_OF_SELF

    def test_omitted_subject_is_self(self) -> None:
        verdict = _verdict("请于收到之日起七日内交纳诉讼费", "收到之日起七日内")
        assert verdict.document is AnchorDocument.SELF

    def test_future_judgment_is_not_self(self) -> None:
        """「告知书」里「裁判文书送达之日起三日内」——那份裁判文书还没产生。"""
        sentence = (
            "申请对裁判文书中的有关内容进行技术处理或者申请不予公布的，至迟应在裁判文书送达之日起三日内以书面形式提出"
        )
        verdict = _verdict(sentence, "裁判文书送达之日起三日内")
        assert verdict.document is AnchorDocument.FUTURE_DOCUMENT
        assert verdict.subject == "裁判文书"

    def test_named_other_document_not_in_batch_is_future(self) -> None:
        sentence = "应自收到《缴费通知书》之日起七日内，按《缴费通知书》载明的收款账号交纳诉讼费用"
        verdict = _verdict(sentence, "收到《缴费通知书》之日起七日内")
        assert verdict.document is AnchorDocument.FUTURE_DOCUMENT
        assert "缴费通知书" in verdict.reason

    def test_named_other_document_in_batch(self) -> None:
        sentence = "应自收到《缴费通知书》之日起七日内交纳诉讼费用"
        verdict = _verdict(
            sentence,
            "收到《缴费通知书》之日起七日内",
            sibling_documents=("诉讼费用交费通知书（某案）.pdf",),
        )
        assert verdict.document in (AnchorDocument.OTHER_IN_BATCH, AnchorDocument.FUTURE_DOCUMENT)

    def test_effective_date_kept_but_flagged(self) -> None:
        """「本判决发生法律效力之日起十日内」：保留候选，但起算点需与书记员确认。"""
        verdict = _verdict("本判决发生法律效力之日起十日内向本院缴纳诉讼费", "十日内向本院缴纳")
        assert verdict.document is AnchorDocument.SELF
        assert verdict.kind is AnchorKind.EFFECTIVE_DATE

    def test_arbitration_award_reference(self) -> None:
        verdict = _verdict("裁决：一、某公司于本裁决书送达之日起十日内向原告支付检测费", "本裁决书送达之日起十日内")
        assert verdict.document is AnchorDocument.OTHER_CASE

    def test_business_letter_reference(self) -> None:
        verdict = _verdict("你公司在收到本函之日起十个工作日内书面答复", "收到本函之日起十个工作日内")
        assert verdict.document is AnchorDocument.OTHER_CASE

    @pytest.mark.parametrize(
        "sentence,core",
        [
            ("如不服本判决，可以在判决书送达之日起十五日内，向本院递交上诉状", "判决书送达之日起十五日内"),
            ("如不服本裁定，可在收到裁定书之日起五日内向本院申请复议", "收到裁定书之日起五日内"),
        ],
    )
    def test_procedural_remedy_anchor_is_self(self, sentence: str, core: str) -> None:
        """上诉期/复议期里「判决书/裁定书送达之日」指的是本文书，绝不能被当成"别份文书"丢掉。"""
        verdict = _verdict(sentence, core)
        assert verdict.document is AnchorDocument.SELF

    def test_self_titles_hint(self) -> None:
        verdict = _verdict("收到裁定书之日起五日内申请复议", "收到裁定书之日起五日内", self_titles=("裁定书",))
        assert verdict.document is AnchorDocument.SELF


# ---------------------------------------------------------------------------
# 选择性申请闸（业务口径 2026-11-24：不进日历）
# ---------------------------------------------------------------------------


class TestOptionalMotion:
    def test_apply_for_non_publication(self) -> None:
        hit, reason = is_optional_motion("申请对裁判文书中的有关内容进行技术处理或者申请不予公布的")
        assert hit is True
        assert "选择性申请" in reason

    @pytest.mark.parametrize(
        "sentence",
        [
            "申请延期举证",
            "申请证人出庭作证",
            "申请鉴定",
            "申请人民法院调查收集证据",
            "申请证据保全",
            "申请回避",
        ],
    )
    def test_other_optional_motions(self, sentence: str) -> None:
        assert is_optional_motion(sentence)[0] is True

    @pytest.mark.parametrize(
        "sentence",
        [
            "如不服本判决，可以在判决书送达之日起十五日内向本院递交上诉状",
            "如不服本裁定，可在收到裁定书之日起五日内向本院申请复议",
            "被告应当在答辩期内提出管辖异议",
            "当事人应在举证期限届满前提交证据",
        ],
    )
    def test_remedy_deadlines_are_not_optional_motions(self, sentence: str) -> None:
        assert is_optional_motion(sentence)[0] is False


# ---------------------------------------------------------------------------
# 置信度与默认勾选
# ---------------------------------------------------------------------------


def _self_verdict() -> AnchorVerdict:
    return AnchorVerdict(AnchorDocument.SELF, AnchorKind.SERVICE_OF_SELF)


class TestDecideCandidate:
    def test_self_anchored_rule_candidate_is_default_checked(self) -> None:
        decision = decide_candidate(
            derivation="rule_relative",
            anchor=_self_verdict(),
            role=DocumentRole.CARRIER,
            confidence=confidence_for(
                derivation="rule_relative", anchor=_self_verdict(), role=DocumentRole.CARRIER, raw=0.9
            ),
            due_at=datetime(2026, 11, 26),
            today=TODAY,
        )
        assert decision.keep is True
        assert decision.flags == ()
        assert decision.default_checked is True
        assert decision.confidence == 0.90

    def test_foreign_anchor_is_dropped(self) -> None:
        for document in (AnchorDocument.FUTURE_DOCUMENT, AnchorDocument.OTHER_IN_BATCH, AnchorDocument.OTHER_CASE):
            decision = decide_candidate(
                derivation="rule_relative",
                anchor=AnchorVerdict(document, AnchorKind.FOREIGN_DOCUMENT),
                role=DocumentRole.CARRIER,
                confidence=0.9,
                due_at=datetime(2026, 11, 27),
                today=TODAY,
            )
            assert decision.keep is False

    def test_generic_notice_rule_relative_dropped_but_absolute_kept(self) -> None:
        """通用文书不产规则推算候选，但 LLM/正则读到的**明文绝对日期**仍然保留。"""
        generic = decide_candidate(
            derivation="rule_relative",
            anchor=_self_verdict(),
            role=DocumentRole.GENERIC_NOTICE,
            confidence=0.4,
            due_at=datetime(2026, 12, 1),
            today=TODAY,
        )
        assert generic.keep is False

        absolute = decide_candidate(
            derivation="llm_absolute",
            anchor=AnchorVerdict(AnchorDocument.SELF, AnchorKind.UNKNOWN),
            role=DocumentRole.GENERIC_NOTICE,
            confidence=confidence_for(
                derivation="llm_absolute",
                anchor=_self_verdict(),
                role=DocumentRole.GENERIC_NOTICE,
                raw=0.9,
            ),
            due_at=datetime(2027, 3, 1),
            today=TODAY,
        )
        assert absolute.keep is True
        assert FLAG_GENERIC_BOILERPLATE in absolute.flags
        assert absolute.default_checked is False  # 有 flag 就不默认勾

    def test_effective_date_never_default_checked(self) -> None:
        """旧实现把这类候选压到「恰好 0.5」，而前端阈值是 >= 0.5 → 仍然默认勾（bug）。"""
        decision = decide_candidate(
            derivation="rule_relative",
            anchor=AnchorVerdict(AnchorDocument.SELF, AnchorKind.EFFECTIVE_DATE),
            role=DocumentRole.CARRIER,
            confidence=confidence_for(
                derivation="rule_relative",
                anchor=AnchorVerdict(AnchorDocument.SELF, AnchorKind.EFFECTIVE_DATE),
                role=DocumentRole.CARRIER,
                raw=0.9,
            ),
            due_at=datetime(2026, 12, 5),
            today=TODAY,
        )
        assert decision.keep is True
        assert FLAG_ANCHOR_EFFECTIVE in decision.flags
        assert decision.confidence == 0.45
        assert decision.default_checked is False

    def test_any_flag_blocks_default_checked(self) -> None:
        """不变量：只要带 flag 就绝不能默认勾选（用低置信度触发）。"""
        decision = decide_candidate(
            derivation="llm_absolute",
            anchor=_self_verdict(),
            role=DocumentRole.CARRIER,
            confidence=0.3,
            due_at=datetime(2026, 12, 5),
            today=TODAY,
        )
        assert FLAG_LOW_CONFIDENCE in decision.flags
        assert decision.default_checked is False


# ---------------------------------------------------------------------------
# 起算点人话说明
# ---------------------------------------------------------------------------


class TestAnchorNote:
    def test_service_of_self_with_days(self) -> None:
        note = anchor_note_for(
            kind=AnchorKind.SERVICE_OF_SELF,
            anchor_at=date(2026, 11, 24),
            delivery_date=date(2026, 11, 24),
            days=7,
        )
        assert note == "起算点：本份文书送达日 2026-11-24 + 7 天"

    def test_effective_date_note(self) -> None:
        note = anchor_note_for(kind=AnchorKind.EFFECTIVE_DATE, anchor_at=None, delivery_date=None)
        assert "判决生效之日" in note and "书记员" in note

    def test_unknown_kind_is_empty(self) -> None:
        assert anchor_note_for(kind=AnchorKind.UNKNOWN, anchor_at=None, delivery_date=None) == ""
