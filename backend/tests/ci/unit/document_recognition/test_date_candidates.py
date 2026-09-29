"""date_candidate_service / DatetimeExtractionMixin / document_analyzer — 多日期候选测试。

改造核心：LLM key_events + 正则候选合并去重 → 律师人工确认后写入重要日期提醒。
全部无 DB（MagicMock / SimpleNamespace 风格，与现有单测一致）。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.document_recognition.services import date_candidate_service as dcs
from apps.document_recognition.services._datetime_extraction_mixin import DatetimeExtractionMixin
from apps.document_recognition.services.data_classes import DocumentType
from apps.document_recognition.services.date_candidate_service import (
    MAX_CANDIDATES,
    REMINDER_TYPE_PRIORITY,
    build_date_candidates,
    parse_candidate_datetime,
)

# ---------------------------------------------------------------------------
# parse_candidate_datetime
# ---------------------------------------------------------------------------


class TestParseCandidateDatetime:
    def test_supported_formats(self):
        assert parse_candidate_datetime("2026-10-15 09:30") == datetime(2026, 10, 15, 9, 30)
        assert parse_candidate_datetime("2026-10-15T09:30") == datetime(2026, 10, 15, 9, 30)
        assert parse_candidate_datetime("2026-10-15") == datetime(2026, 10, 15)

    def test_isoformat_with_tz_stripped_to_naive(self):
        parsed = parse_candidate_datetime("2026-10-15T09:30:00+08:00")
        assert parsed == datetime(2026, 10, 15, 9, 30)
        assert parsed.tzinfo is None

    def test_isoformat_fallback(self):
        assert parse_candidate_datetime("2026-10-15 09:30:45") == datetime(2026, 10, 15, 9, 30, 45)

    def test_invalid_returns_none(self):
        assert parse_candidate_datetime("not a date") is None
        assert parse_candidate_datetime("") is None

    def test_strips_whitespace(self):
        assert parse_candidate_datetime("  2026-10-15 ") == datetime(2026, 10, 15)


# ---------------------------------------------------------------------------
# build_date_candidates
# ---------------------------------------------------------------------------


def _stub_extractor(candidates: list[dict[str, Any]]):
    extractor = MagicMock()
    extractor.extract_datetime_candidates.return_value = candidates
    return extractor


def _event(dt: str, event_type: str = "hearing", context: str = "ctx", confidence: float = 0.7):
    return SimpleNamespace(datetime=dt, event_type=event_type, context=context, confidence=confidence)


class TestBuildDateCandidates:
    def test_llm_and_regex_same_time_and_type_merge(self):
        """同 (时间, 类型) 合并：source=merged、置信度取 max。"""
        extractor = _stub_extractor(
            [
                {
                    "datetime": datetime(2026, 10, 15, 9, 30),
                    "context_text": "定于…开庭",
                    "context_score": 100,  # → regex 置信 0.85
                    "reminder_type": "hearing",
                }
            ]
        )
        analysis = SimpleNamespace(key_events=[_event("2026-10-15 09:30", "hearing", confidence=0.7)])

        drafts = build_date_candidates("text", analysis, DocumentType.SUMMONS, regex_extractor=extractor)

        assert len(drafts) == 1
        merged = drafts[0]
        assert merged.source == "merged"
        assert merged.confidence == pytest.approx(0.85)  # max(0.7, 0.85)
        assert merged.reminder_type == "hearing"

    def test_llm_only_candidate(self):
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(key_events=[_event("2026-10-15 09:30", "appeal_deadline", "上诉期届满", 0.9)])

        drafts = build_date_candidates("text", analysis, DocumentType.SUMMONS, regex_extractor=extractor)

        assert len(drafts) == 1
        assert drafts[0].source == "llm"
        assert drafts[0].reminder_type == "appeal_deadline"
        assert drafts[0].confidence == 0.9
        assert drafts[0].context_text == "上诉期届满"

    def test_same_day_different_types_both_kept(self):
        """同日不同类型都保留（开庭日与举证截止同日是真实场景）。"""
        extractor = _stub_extractor(
            [
                {
                    "datetime": datetime(2026, 10, 15, 9, 30),
                    "context_text": "举证期限届满",
                    "context_score": 80,
                    "reminder_type": "evidence_deadline",
                }
            ]
        )
        analysis = SimpleNamespace(key_events=[_event("2026-10-15 09:30", "hearing")])

        drafts = build_date_candidates("text", analysis, DocumentType.SUMMONS, regex_extractor=extractor)

        assert len(drafts) == 2
        assert {d.reminder_type for d in drafts} == {"hearing", "evidence_deadline"}

    def test_ordering_by_type_priority(self):
        """排序按 REMINDER_TYPE_PRIORITY（开庭最关键），同类型按置信度降序。"""
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(
            key_events=[
                _event("2026-12-01 09:00", "other", "其他", 0.9),
                _event("2026-11-01 09:00", "evidence_deadline", "", 0.6),
                _event("2026-10-01 09:00", "hearing", "", 0.8),
                _event("2026-09-01 09:00", "hearing", "", 0.95),
            ]
        )

        drafts = build_date_candidates("text", analysis, DocumentType.SUMMONS, regex_extractor=extractor)

        assert [d.reminder_type for d in drafts] == ["hearing", "hearing", "evidence_deadline", "other"]
        assert drafts[0].confidence == 0.95  # 同类型内高置信在前

    def test_truncated_to_max_candidates(self):
        extractor = _stub_extractor([])
        events = [
            _event(f"2026-{month:02d}-15 09:00", "other", f"c{month}", 0.5 + month / 100) for month in range(1, 13)
        ]
        analysis = SimpleNamespace(key_events=events)

        drafts = build_date_candidates("text", analysis, DocumentType.SUMMONS, regex_extractor=extractor)

        assert len(drafts) == MAX_CANDIDATES
        # 截断保留置信度更高的 8 条（其他类型无优先级差异）
        assert all(d.confidence >= 0.05 + 5 / 100 for d in drafts)

    def test_stale_date_confidence_demoted(self):
        """过期超过 180 天的候选降置信（改判文书的历史日期折叠而非丢弃）。"""
        stale = datetime.now() - timedelta(days=200)
        fresh = datetime.now() + timedelta(days=10)
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(
            key_events=[
                _event(stale.strftime("%Y-%m-%d %H:%M"), "hearing", "旧日期", 0.95),
                _event(fresh.strftime("%Y-%m-%d %H:%M"), "hearing", "新日期", 0.95),
            ]
        )

        drafts = build_date_candidates("text", analysis, DocumentType.SUMMONS, regex_extractor=extractor)

        by_ctx = {d.context_text: d for d in drafts}
        assert by_ctx["旧日期"].confidence <= 0.3
        assert by_ctx["新日期"].confidence == 0.95

    def test_llm_invalid_event_type_falls_back_to_other(self):
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(key_events=[_event("2026-10-15 09:30", "bogus_type")])

        drafts = build_date_candidates("text", analysis, DocumentType.SUMMONS, regex_extractor=extractor)

        assert drafts[0].reminder_type == "other"

    def test_llm_unparseable_datetime_skipped(self):
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(key_events=[_event("not a date")])

        drafts = build_date_candidates("text", analysis, DocumentType.SUMMONS, regex_extractor=extractor)

        assert drafts == []

    def test_regex_candidate_without_type_uses_document_default(self):
        """上下文未命中类型关键词时按文书类型给默认（SUMMONS→hearing 等）。"""
        cases = {
            DocumentType.SUMMONS: "hearing",
            DocumentType.EXECUTION_RULING: "asset_preservation_expires",
            DocumentType.OTHER: "other",
        }
        for doc_type, expected in cases.items():
            extractor = _stub_extractor(
                [
                    {
                        "datetime": datetime(2026, 10, 15, 9, 0),
                        "context_text": "某日",
                        "context_score": 0,
                        "reminder_type": None,
                    }
                ]
            )
            drafts = build_date_candidates("text", None, doc_type, regex_extractor=extractor)
            assert drafts[0].reminder_type == expected
            assert drafts[0].source == "regex"

    def test_analysis_none_or_no_events(self):
        extractor = _stub_extractor([])
        assert build_date_candidates("text", None, DocumentType.OTHER, regex_extractor=extractor) == []
        assert (
            build_date_candidates(
                "text", SimpleNamespace(key_events=None), DocumentType.OTHER, regex_extractor=extractor
            )
            == []
        )

    def test_real_mixin_extraction_integration(self):
        """真实 Mixin 提取：文本含开庭时间，类型推断为 hearing。"""
        text = "本院定于2026年11月5日上午9时30分在第三审判庭开庭审理。"
        drafts = build_date_candidates(text, None, DocumentType.SUMMONS)

        assert len(drafts) == 1
        assert drafts[0].due_at == datetime(2026, 11, 5, 9, 30)
        assert drafts[0].reminder_type == "hearing"
        assert drafts[0].source == "regex"

    def test_reminder_type_priority_constants(self):
        assert REMINDER_TYPE_PRIORITY["hearing"] < REMINDER_TYPE_PRIORITY["evidence_deadline"]
        assert REMINDER_TYPE_PRIORITY["hearing"] < REMINDER_TYPE_PRIORITY["asset_preservation_expires"]
        assert REMINDER_TYPE_PRIORITY["other"] == max(REMINDER_TYPE_PRIORITY.values())


# ---------------------------------------------------------------------------
# 相对期限推算：「收到本通知次日起两日内交纳」等 → 以落款日为锚算届满日
# ---------------------------------------------------------------------------


class TestParseCnNumber:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("7", 7),
            ("15", 15),
            ("两", 2),
            ("七", 7),
            ("十", 10),
            ("拾", 10),
            ("十五", 15),
            ("二十", 20),
            ("三十一", 31),
            ("贰拾", 20),
        ],
    )
    def test_valid(self, text, expected):
        assert dcs._parse_cn_number(text) == expected

    @pytest.mark.parametrize("text", ["", "百", "十五六", "3x"])
    def test_invalid_returns_none(self, text):
        assert dcs._parse_cn_number(text) is None


class TestFindIssueDate:
    def test_cn_digits_issue_date(self):
        """task 7 真实形态：OCR 文本中「打印日期：二〇二五年十一月十一日」。"""
        text = "…二维码有效期为缴费后三个月内。zdqz打印日期：二〇二五年十一月十一日请扫二维码缴费…"
        assert dcs._find_issue_date(text) == datetime(2025, 11, 11)

    def test_arabic_issue_date(self):
        assert dcs._find_issue_date("落款：2026年10月10日") == datetime(2026, 10, 10)

    def test_takes_last_date_as_issue_date(self):
        """落款惯例在文末：正文中段的开庭日不应被当作锚。"""
        text = "定于2026年10月20日10时0分开庭。二〇二六年十月十日"
        assert dcs._find_issue_date(text) == datetime(2026, 10, 10)

    def test_no_date_returns_none(self):
        assert dcs._find_issue_date("没有任何日期") is None

    def test_year_out_of_range_ignored(self):
        assert dcs._find_issue_date("落款：1999年1月1日") is None


class TestRelativeDeadlineRules:
    """_apply_relative_deadline_rules（经 build_date_candidates 端到端验证）。"""

    TASK7_TEXT = (
        "广东法院诉讼费用交费通知书。保全费请你方于收到本通知次日起两日内向本院交纳。"
        "超过缴款截止日期的，代收银行不予受理。zdqz打印日期：二〇二五年十一月十一日请扫二维码缴费"
    )

    def test_task7_llm_anchor_date_corrected_to_deadline(self):
        """LLM 把落款日当事件日（task 7 实际形态）→ 规则校正为锚+2 天。"""
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(
            key_events=[_event("2025-11-11", "payment_deadline", "保全费请你方于收到本通知次日起两日内向本院交纳", 0.7)]
        )

        drafts = build_date_candidates(self.TASK7_TEXT, analysis, DocumentType.OTHER, regex_extractor=extractor)

        assert len(drafts) == 1
        assert drafts[0].due_at == datetime(2025, 11, 13)
        assert drafts[0].reminder_type == "payment_deadline"
        # 历史日期仍会被陈旧降权，但校正动作本身应发生（source 保留 llm）
        assert drafts[0].source == "llm"

    def test_fingerprint_match_when_context_rewritten(self):
        """LLM context 被截断/改写时，按「同类型且日期=锚日」指纹匹配校正。"""
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(key_events=[_event("2026-10-10", "payment_deadline", "（LLM 改写的上下文）", 0.6)])
        text = "请于收到本通知书之日起7日内向本院交纳诉讼费用。落款：2026年10月10日"

        drafts = build_date_candidates(text, analysis, DocumentType.OTHER, regex_extractor=extractor)

        assert len(drafts) == 1
        assert drafts[0].due_at == datetime(2026, 10, 17)

    def test_llm_missing_event_appends_regex_draft(self):
        """LLM 漏提相对期限 → 补一条正则候选（届满=锚+7）。"""
        extractor = _stub_extractor([])
        text = "请于收到本通知书之日起7日内向本院交纳诉讼费用。落款：2026年10月10日"

        drafts = build_date_candidates(text, None, DocumentType.OTHER, regex_extractor=extractor)

        assert len(drafts) == 1
        assert drafts[0].due_at == datetime(2026, 10, 17)
        assert drafts[0].reminder_type == "payment_deadline"
        assert drafts[0].source == "regex"
        assert drafts[0].confidence == 0.85
        assert "7日内" in drafts[0].context_text

    def test_cn_seven_days(self):
        text = "保全费应自收到本决定书之日起七日内缴纳。落款：二〇二六年十月十日"

        drafts = build_date_candidates(text, None, DocumentType.OTHER, regex_extractor=_stub_extractor([]))

        assert drafts[0].due_at == datetime(2026, 10, 17)

    def test_cn_compound_days_fifteen(self):
        text = "如不服本判决，应在判决送达之日起十五日内向本院递交上诉状。落款：2026年10月10日"

        drafts = build_date_candidates(text, None, DocumentType.OTHER, regex_extractor=_stub_extractor([]))

        assert drafts[0].due_at == datetime(2026, 10, 25)
        assert drafts[0].reminder_type == "appeal_deadline"

    def test_bare_action_phrase_arabic(self):
        """无「收到」锚的动作版：7日内付款。"""
        text = "请于7日内付款，逾期加收滞纳金。落款：2026年10月10日"

        drafts = build_date_candidates(text, None, DocumentType.OTHER, regex_extractor=_stub_extractor([]))

        assert drafts[0].due_at == datetime(2026, 10, 17)
        assert drafts[0].reminder_type == "payment_deadline"

    def test_preservation_fee_typed_as_payment(self):
        """「保全费…交纳」按动作词判 payment，不被名词「保全」带偏成保全到期。"""
        text = "保全费请你方于收到本通知次日起两日内向本院交纳。落款：2026年10月10日"

        drafts = build_date_candidates(text, None, DocumentType.OTHER, regex_extractor=_stub_extractor([]))

        assert drafts[0].reminder_type == "payment_deadline"

    def test_llm_already_computed_not_duplicated(self):
        """LLM 按 prompt 正确推算 → 不再补重复候选。"""
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(
            key_events=[_event("2026-10-17", "payment_deadline", "收到本通知次日起七日内交纳", 0.9)]
        )
        text = "收到本通知次日起七日内交纳。落款：2026年10月10日"

        drafts = build_date_candidates(text, analysis, DocumentType.OTHER, regex_extractor=extractor)

        assert len(drafts) == 1
        assert drafts[0].due_at == datetime(2026, 10, 17)
        assert drafts[0].confidence == 0.9

    def test_no_issue_date_keeps_drafts_untouched(self):
        """无锚点日期时规则静默退出（LLM 候选原样保留）。"""
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(key_events=[_event("2026-10-15 09:30", "hearing", "开庭", 0.8)])

        drafts = build_date_candidates(
            "收到本通知次日起两日内交纳，无落款日期", analysis, DocumentType.OTHER, regex_extractor=extractor
        )

        assert len(drafts) == 1
        assert drafts[0].due_at == datetime(2026, 10, 15, 9, 30)

    def test_multiple_relative_phrases_each_computed(self):
        """同一文书多个相对期限句各自推算（缴费 7 日 + 上诉 15 日）。"""
        text = "诉讼费请于收到本通知书之日起7日内交纳。如不服本裁定，可于送达之日起十日内申请复议。落款：2026年10月10日"

        drafts = build_date_candidates(text, None, DocumentType.OTHER, regex_extractor=_stub_extractor([]))

        by_type = {d.reminder_type: d.due_at for d in drafts}
        assert by_type["payment_deadline"] == datetime(2026, 10, 17)
        # 「申请复议」未命中动作词映射 → other，但日期仍按锚+10 推算
        assert by_type["other"] == datetime(2026, 10, 20)

    def test_two_payment_phrases_no_draft_stealing(self):
        """两句 payment 期限 + LLM 只给一条落款日候选：context 精确认领优先于指纹，

        两句各自有候选（task 7 真实形态：保全费两日内 + 受理费七日内）。"""
        extractor = _stub_extractor([])
        analysis = SimpleNamespace(
            key_events=[_event("2026-10-10", "payment_deadline", "保全费请你方于收到本通知次日起两日内向本院交纳", 0.7)]
        )
        text = (
            "案件受理费请你方于收到本通知次日起七日内向本院交纳。"
            "保全费请你方于收到本通知次日起两日内向本院交纳。落款：2026年10月10日"
        )

        drafts = build_date_candidates(text, analysis, DocumentType.OTHER, regex_extractor=extractor)

        by_due = {d.due_at: d for d in drafts}
        assert len(by_due) == 2
        # LLM 候选归属 context 精确命中的「两日内」，而非被「七日内」的指纹抢走
        assert by_due[datetime(2026, 10, 12)].source == "llm"
        assert "两日内" in by_due[datetime(2026, 10, 12)].context_text
        assert by_due[datetime(2026, 10, 17)].source == "regex"
        assert "七日内" in by_due[datetime(2026, 10, 17)].context_text

    def test_absolute_hearing_date_not_affected(self):
        """绝对日期候选不受相对期限规则影响（无相对句时零侵入）。"""
        text = "本院定于2026年11月5日上午9时30分开庭审理。落款：2026年10月10日"

        drafts = build_date_candidates(text, None, DocumentType.SUMMONS)

        assert len(drafts) == 1
        assert drafts[0].due_at == datetime(2026, 11, 5, 9, 30)
        assert drafts[0].reminder_type == "hearing"


# ---------------------------------------------------------------------------
# DatetimeExtractionMixin.extract_datetime_candidates / _guess_reminder_type
# ---------------------------------------------------------------------------


class TestExtractDatetimeCandidates:
    def setup_method(self):
        self.mixin = DatetimeExtractionMixin()

    def test_exposes_all_candidates_with_context(self):
        evidence = self.mixin.extract_datetime_candidates("举证期限届满前请于2026年10月20日10时0分提交证据材料")
        hearing = self.mixin.extract_datetime_candidates("开庭时间为2026年11月5日 9时30分")

        assert evidence[0]["datetime"] == datetime(2026, 10, 20, 10, 0)
        assert evidence[0]["reminder_type"] == "evidence_deadline"
        assert hearing[0]["datetime"] == datetime(2026, 11, 5, 9, 30)
        assert hearing[0]["reminder_type"] == "hearing"
        for c in evidence + hearing:
            assert isinstance(c["context_text"], str) and c["context_text"]
            assert isinstance(c["context_score"], int)
            assert 0 <= c["context_score"] <= 100

    def test_multiple_dates_in_one_text_all_exposed(self):
        text = "2026年10月20日10时0分与2026年11月5日 9时30分两个时间点"
        candidates = self.mixin.extract_datetime_candidates(text)
        assert len(candidates) == 2

    def test_afternoon_converted_to_24h(self):
        candidates = self.mixin.extract_datetime_candidates("2026年11月5日 下午2时30分开庭")
        assert candidates[0]["datetime"] == datetime(2026, 11, 5, 14, 30)

    def test_no_dates_returns_empty(self):
        assert self.mixin.extract_datetime_candidates("没有日期的文本") == []

    def test_duplicate_within_one_minute_deduped(self):
        candidates = self.mixin.extract_datetime_candidates(
            "2026年11月5日 9时30分开庭，再次强调2026-11-05 09:30准时到庭"
        )
        assert len(candidates) == 1


class TestGuessReminderType:
    @pytest.mark.parametrize(
        ("context", "expected"),
        [
            ("举证期限届满前提交证据", "evidence_deadline"),
            ("上诉期届满之日", "appeal_deadline"),
            ("解除对被申请人财产的查封、冻结", "asset_preservation_expires"),
            ("请于该日前缴纳诉讼费用", "payment_deadline"),
            ("按要求补正并提交材料", "submission_deadline"),
            ("诉讼时效届满", "statute_limitations"),
            ("本院第三审判庭开庭审理", "hearing"),
        ],
    )
    def test_context_keyword_mapping(self, context, expected):
        assert DatetimeExtractionMixin._guess_reminder_type(context) == expected

    def test_no_keyword_returns_none(self):
        assert DatetimeExtractionMixin._guess_reminder_type("无关文本") is None
        assert DatetimeExtractionMixin._guess_reminder_type("") is None


# ---------------------------------------------------------------------------
# document_analyzer 新字段
# ---------------------------------------------------------------------------


class TestCourtDocumentAnalysisFields:
    def test_defaults(self):
        from apps.document_recognition.services.document_analyzer import CourtDocumentAnalysis

        analysis = CourtDocumentAnalysis()
        assert analysis.key_events == []
        assert analysis.party_names == []
        assert analysis.court_name is None
        assert analysis.document_type == "other"
        assert analysis.case_number is None

    def test_analysis_prompt_covers_relative_deadline(self):
        """prompt 必须教 LLM 对相对期限表述做锚点推算，且禁止拿落款日当事件日。"""
        from apps.document_recognition.services.document_analyzer import ANALYSIS_PROMPT

        assert "相对表述" in ANALYSIS_PROMPT
        assert "起算当日不计入" in ANALYSIS_PROMPT
        assert "切勿把落款日期本身" in ANALYSIS_PROMPT
        assert "不要虚构日期" in ANALYSIS_PROMPT

    def test_new_fields_populated(self):
        from apps.document_recognition.services.document_analyzer import CourtDocumentAnalysis, ExtractedDateEvent

        analysis = CourtDocumentAnalysis(
            document_type="summons",
            key_events=[ExtractedDateEvent(datetime="2026-10-15 09:30", event_type="hearing")],
            party_names=["张三", "李四"],
            court_name="佛山市顺德区人民法院",
        )
        assert analysis.key_events[0].event_type == "hearing"
        assert analysis.party_names == ["张三", "李四"]
        assert analysis.court_name == "佛山市顺德区人民法院"

    def test_extracted_date_event_validation(self):
        import pydantic

        from apps.document_recognition.services.document_analyzer import ExtractedDateEvent

        # 非法 event_type 拒绝
        with pytest.raises(pydantic.ValidationError):
            ExtractedDateEvent(datetime="2026-10-15", event_type="bogus")  # type: ignore[arg-type]
        # 置信度越界拒绝
        with pytest.raises(pydantic.ValidationError):
            ExtractedDateEvent(datetime="2026-10-15", confidence=1.5)
        # 合法默认值
        event = ExtractedDateEvent(datetime="2026-10-15")
        assert event.event_type == "other"
        assert event.context == ""
        assert event.confidence == 0.7


# ---------------------------------------------------------------------------
# 纯逻辑：_build_reminder_content / _find_existing_reminder
# ---------------------------------------------------------------------------


class TestBuildReminderContent:
    def test_empty_context_returns_label_only(self):
        content = dcs._build_reminder_content("hearing", "")
        assert content == "开庭"

    def test_context_appended_after_label(self):
        content = dcs._build_reminder_content("hearing", "定于2026年11月5日开庭")
        assert content.startswith("开庭：")
        assert "定于2026年11月5日开庭" in content

    def test_context_truncated_to_60_chars(self):
        content = dcs._build_reminder_content("other", "x" * 100)
        assert content == f"其他：{'x' * 60}"

    def test_unknown_type_returns_raw_type(self):
        assert dcs._build_reminder_content("bogus", "") == "bogus"


class TestFindExistingReminder:
    def test_case_log_none_returns_none_without_query(self):
        reminder_service = MagicMock()
        task = SimpleNamespace(case_log_id=None)

        assert dcs._find_existing_reminder(reminder_service, task, datetime(2026, 10, 15)) is None
        reminder_service.list_reminders.assert_not_called()

    def test_same_due_at_reused(self):
        from django.utils.timezone import make_aware

        aware = make_aware(datetime(2026, 10, 15, 9, 30))
        existing = SimpleNamespace(due_at=aware, id=55)
        reminder_service = MagicMock()
        reminder_service.list_reminders.return_value = [SimpleNamespace(due_at=aware - timedelta(days=1)), existing]
        task = SimpleNamespace(case_log_id=7)

        found = dcs._find_existing_reminder(reminder_service, task, aware)

        assert found is existing
        reminder_service.list_reminders.assert_called_once_with(case_log_id=7)

    def test_no_matching_due_at_returns_none(self):
        from django.utils.timezone import make_aware

        aware = make_aware(datetime(2026, 10, 15, 9, 30))
        reminder_service = MagicMock()
        reminder_service.list_reminders.return_value = [SimpleNamespace(due_at=aware - timedelta(hours=1))]
        task = SimpleNamespace(case_log_id=7)

        assert dcs._find_existing_reminder(reminder_service, task, aware) is None


# ---------------------------------------------------------------------------
# _confirm_single_item（confirm_candidates 的逐项纯逻辑）
# ---------------------------------------------------------------------------


def _pending_row(row_id: int = 11, reminder_type: str = "hearing", context: str = "开庭") -> MagicMock:
    row = MagicMock()
    row.id = row_id
    row.status = "pending"
    row.reminder_type = reminder_type
    row.context_text = context
    row.reminder_id = None
    row.due_at = datetime(2026, 10, 15, 9, 30)
    return row


def _task(case_log_id: int | None = 5) -> MagicMock:
    task = MagicMock()
    task.id = 1
    task.case_log_id = case_log_id
    return task


class TestConfirmSingleItem:
    def _call(self, task, item, row, reminder_service=None, user_id=9):
        return dcs._confirm_single_item(
            task=task,
            item=item,
            row=row,
            reminder_service=reminder_service or MagicMock(),
            user_id=user_id,
            now=datetime(2026, 9, 28, 12, 0),
        )

    def test_confirmed_row_is_idempotent(self):
        row = _pending_row()
        row.status = "confirmed"
        row.reminder_id = 77
        reminder_service = MagicMock()

        result = self._call(_task(), {"candidate_id": 11, "action": "confirm"}, row, reminder_service)

        assert result["status"] == "confirmed"
        assert result["reminder_id"] == 77
        assert "幂等" in result["message"]
        reminder_service.create_reminder.assert_not_called()

    def test_missing_candidate_returns_error(self):
        result = self._call(_task(), {"candidate_id": 99, "action": "confirm"}, None)

        assert result["status"] == "error"
        assert result["error_code"] == "CANDIDATE_NOT_FOUND"

    def test_skip_pending_row(self):
        row = _pending_row()

        result = self._call(_task(), {"candidate_id": 11, "action": "skip"}, row)

        assert result["status"] == "skipped"
        assert row.status == "skipped"
        row.save.assert_called_once()

    def test_skip_on_confirmed_row_is_noop(self):
        row = _pending_row()
        row.status = "confirmed"
        row.reminder_id = 77

        result = self._call(_task(), {"candidate_id": 11, "action": "skip"}, row)

        assert result["status"] == "confirmed"
        assert result["reminder_id"] == 77
        row.save.assert_not_called()

    def test_invalid_reminder_type(self):
        row = _pending_row()

        result = self._call(_task(), {"candidate_id": 11, "action": "confirm", "reminder_type": "bogus"}, row)

        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_REMINDER_TYPE"

    def test_invalid_time_format(self):
        row = _pending_row()

        result = self._call(_task(), {"candidate_id": 11, "action": "confirm", "due_at": "garbage"}, row)

        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_TIME_FORMAT"

    def test_confirm_creates_reminder_and_updates_row(self):
        row = _pending_row()
        reminder_service = MagicMock()
        reminder_service.list_reminders.return_value = []
        created = MagicMock()
        created.id = 123
        reminder_service.create_reminder.return_value = created

        result = self._call(_task(case_log_id=5), {"candidate_id": 11, "action": "confirm"}, row, reminder_service)

        assert result["status"] == "confirmed"
        assert result["reminder_id"] == 123
        create_kwargs = reminder_service.create_reminder.call_args[1]
        assert create_kwargs["case_log_id"] == 5
        assert create_kwargs["reminder_type"] == "hearing"
        assert create_kwargs["content"] == "开庭：开庭"
        assert create_kwargs["due_at"].tzinfo is not None  # naive → aware
        assert create_kwargs["metadata"]["source"] == dcs.REMINDER_SOURCE
        assert create_kwargs["metadata"]["source_id"] == "task:1:candidate:11"
        # 确认过的重要日期列入案件「重要时间」视图
        assert created.include_in_important_time is True
        created.save.assert_called_once_with(update_fields=["include_in_important_time"])
        # 候选行状态机推进
        assert row.status == "confirmed"
        assert row.reminder_id == 123
        assert row.confirmed_by_id == 9
        row.save.assert_called_once()

    def test_confirm_reuses_existing_reminder_with_same_due_at(self):
        from django.utils.timezone import make_aware

        row = _pending_row()
        aware = make_aware(datetime(2026, 10, 15, 9, 30))
        existing = SimpleNamespace(id=55, due_at=aware)
        reminder_service = MagicMock()
        reminder_service.list_reminders.return_value = [existing]

        result = self._call(_task(case_log_id=5), {"candidate_id": 11, "action": "confirm"}, row, reminder_service)

        assert result["reminder_id"] == 55
        assert "复用" in result["message"]
        reminder_service.create_reminder.assert_not_called()
        assert row.reminder_id == 55

    def test_standalone_task_skips_reuse_lookup(self):
        """未绑定案件（case_log 为空）的任务：不查重，直接建独立提醒。"""
        row = _pending_row()
        reminder_service = MagicMock()

        self._call(_task(case_log_id=None), {"candidate_id": 11, "action": "confirm"}, row, reminder_service)

        reminder_service.list_reminders.assert_not_called()
        reminder_service.create_reminder.assert_called_once()
        create_kwargs = reminder_service.create_reminder.call_args[1]
        assert create_kwargs["case_log_id"] is None
        assert create_kwargs["metadata"]["task_id"] == 1


# ---------------------------------------------------------------------------
# confirm_candidates / revoke_confirmation / persist / refresh（mock 模型层）
# ---------------------------------------------------------------------------


class TestConfirmCandidatesWrapped:
    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_task_not_ready_raises(self, MockTask):
        MockTask.objects.select_for_update.return_value.get.return_value = SimpleNamespace(status="failed")

        with pytest.raises(Exception) as exc_info:
            dcs.confirm_candidates.__wrapped__(1, [{"candidate_id": 1}])  # type: ignore[attr-defined]
        assert getattr(exc_info.value, "code", None) == "TASK_NOT_READY"

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_skip_item_flow(self, MockTask):
        task = _task()
        task.status = "success"
        row = _pending_row()
        task.date_candidates.select_for_update.return_value.filter.return_value = [row]
        task.date_candidates.values_list.return_value = ["skipped"]
        MockTask.objects.select_for_update.return_value.get.return_value = task

        with patch.object(dcs, "_resolve_reminder_service", return_value=MagicMock()):
            results = dcs.confirm_candidates.__wrapped__(1, [{"candidate_id": 11, "action": "skip"}])  # type: ignore[attr-defined]

        assert results[0]["status"] == "skipped"
        task.save.assert_called_once_with(update_fields=["date_confirmation_status"])


class TestRevokeConfirmation:
    def _row(self, status: str = "confirmed", reminder_id: int | None = 88) -> MagicMock:
        row = _pending_row()
        row.status = status
        row.reminder_id = reminder_id
        return row

    def _task_with(self, row) -> MagicMock:
        task = _task()
        task.date_candidates.select_for_update.return_value.get.return_value = row
        task.date_candidates.values_list.return_value = ["pending"]
        return task

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_not_confirmed_raises(self, MockTask):
        MockTask.objects.select_for_update.return_value.get.return_value = self._task_with(self._row(status="pending"))

        with pytest.raises(Exception) as exc_info:
            dcs.revoke_confirmation.__wrapped__(1, 11)  # type: ignore[attr-defined]
        assert getattr(exc_info.value, "code", None) == "NOT_CONFIRMED"

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_foreign_reminder_not_revokable(self, MockTask):
        row = self._row(reminder_id=88)
        MockTask.objects.select_for_update.return_value.get.return_value = self._task_with(row)
        reminder_service = MagicMock()
        reminder_service.get_reminder.return_value = SimpleNamespace(id=88, metadata={"source": "other_module"})

        with patch.object(dcs, "_resolve_reminder_service", return_value=reminder_service):
            with pytest.raises(Exception) as exc_info:
                dcs.revoke_confirmation.__wrapped__(1, 11)  # type: ignore[attr-defined]
        assert getattr(exc_info.value, "code", None) == "NOT_REVOKABLE"
        reminder_service.delete_reminder.assert_not_called()

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_own_reminder_deleted_and_row_reset(self, MockTask):
        row = self._row(reminder_id=88)
        MockTask.objects.select_for_update.return_value.get.return_value = self._task_with(row)
        reminder_service = MagicMock()
        reminder_service.get_reminder.return_value = SimpleNamespace(id=88, metadata={"source": dcs.REMINDER_SOURCE})

        with patch.object(dcs, "_resolve_reminder_service", return_value=reminder_service):
            result = dcs.revoke_confirmation.__wrapped__(1, 11)  # type: ignore[attr-defined]

        reminder_service.delete_reminder.assert_called_once_with(88)
        assert row.status == "pending"
        assert row.reminder_id is None
        assert result["status"] == "pending"

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_without_reminder_just_resets_row(self, MockTask):
        row = self._row(reminder_id=None)
        MockTask.objects.select_for_update.return_value.get.return_value = self._task_with(row)

        with patch.object(dcs, "_resolve_reminder_service", return_value=MagicMock()) as mock_resolve:
            dcs.revoke_confirmation.__wrapped__(1, 11)  # type: ignore[attr-defined]

        mock_resolve.return_value.get_reminder.assert_not_called()
        assert row.status == "pending"


class TestPersistAndRefreshStatus:
    @patch("apps.document_recognition.models.DocumentRecognitionDateCandidate")
    def test_persist_skips_when_candidates_exist(self, MockCandidate):
        task = MagicMock()
        task.date_candidates.exists.return_value = True

        assert dcs.persist_candidates(task, []) == 0
        MockCandidate.objects.bulk_create.assert_not_called()

    @patch("apps.document_recognition.models.DocumentRecognitionDateCandidate")
    def test_persist_bulk_creates_rows(self, MockCandidate):
        task = MagicMock()
        task.id = 1
        task.date_candidates.exists.return_value = False
        drafts = [
            dcs.DateCandidateDraft(
                due_at=datetime(2026, 10, 15, 9, 30),
                reminder_type="hearing",
                context_text="开庭",
                source="llm",
                confidence=0.9,
            )
        ]

        with patch.object(dcs, "refresh_task_confirmation_status"):
            count = dcs.persist_candidates(task, drafts)

        assert count == 1
        MockCandidate.objects.bulk_create.assert_called_once()
        construct_kwargs = MockCandidate.call_args[1]
        assert construct_kwargs["reminder_type"] == "hearing"
        assert construct_kwargs["task"] is task
        assert construct_kwargs["source"] == "llm"

    def test_refresh_status_transitions(self):
        cases = [
            ([], "none"),
            (["pending"], "pending"),
            (["confirmed"], "complete"),
            (["pending", "confirmed"], "partial"),
            (["pending", "skipped"], "partial"),
            (["confirmed", "skipped"], "complete"),
        ]
        for statuses, expected in cases:
            task = MagicMock()
            task.date_candidates.values_list.return_value = statuses
            task.date_confirmation_status = "stale"
            dcs.refresh_task_confirmation_status(task)
            assert task.date_confirmation_status == expected, f"{statuses} → {expected}"
            task.save.assert_called_once_with(update_fields=["date_confirmation_status"])

    def test_refresh_status_no_save_when_unchanged(self):
        task = MagicMock()
        task.date_candidates.values_list.return_value = []
        task.date_confirmation_status = "none"
        dcs.refresh_task_confirmation_status(task)
        task.save.assert_not_called()

    def test_date_candidate_draft_to_dict(self):
        draft = dcs.DateCandidateDraft(
            due_at=datetime(2026, 10, 15, 9, 30),
            reminder_type="hearing",
            context_text="开庭",
            source="llm",
            confidence=0.9,
        )
        payload = draft.to_dict()
        assert payload == {
            "due_at": "2026-10-15T09:30:00",
            "reminder_type": "hearing",
            "context_text": "开庭",
            "source": "llm",
            "confidence": 0.9,
        }
