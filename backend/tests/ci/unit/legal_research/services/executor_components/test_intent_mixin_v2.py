"""Tests for apps.legal_research.services.executor_components.intent_mixin.ExecutorIntentMixin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from apps.legal_research.services.executor_components.intent_mixin import ExecutorIntentMixin


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractIntentSlots:

    def test_empty_text(self) -> None:
        relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots("")
        assert relation == []
        assert breach == []
        assert damage == []
        assert remedy == []

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test买卖合同纠纷_detected(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        text = "原告与被告签订买卖合同，被告违约导致价差损失"
        relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
        assert any("买卖合同" in r for r in relation)

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_breach_detected(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        text = "被告逾期交货，拒绝履行合同义务"
        relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
        assert len(breach) > 0

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_damage_detected(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        text = "原告主张价差损失和违约金赔偿"
        relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
        assert len(damage) > 0

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_remedy_detected(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        text = "原告请求继续履行合同并赔偿损失"
        relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
        assert len(remedy) > 0

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_whitespace_normalized(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        text = "  原告   与   被告  签订   买卖合同  "
        relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
        assert isinstance(relation, list)


class TestExtractIntentSlotsWithConfidence:

    def test_empty_text_returns_empty_slots(self) -> None:
        result = ExecutorIntentMixin._extract_intent_slots_with_confidence("")
        assert result["relation_high"] == []
        assert result["breach_high"] == []
        assert result["low_conf_limit"] >= 1

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_with_relation_mapping(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        text = "买卖合同纠纷案，被告违约未交货"
        result = ExecutorIntentMixin._extract_intent_slots_with_confidence(text)
        assert len(result["relation_high"]) > 0

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_damage_mapping(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        text = "原告主张价差损失和违约金"
        result = ExecutorIntentMixin._extract_intent_slots_with_confidence(text)
        assert len(result["damage_high"]) > 0


class TestCollectIntentTerms:

    def test_basic_mapping(self) -> None:
        mapping = ((("违约",), "违约责任"), (("转卖",), "转卖违约"))
        terms = ExecutorIntentMixin._collect_intent_terms("被告违约并转卖货物", mapping)
        assert "违约责任" in terms
        assert "转卖违约" in terms

    def test_no_match(self) -> None:
        mapping = ((("劳动",), "劳动争议"),)
        terms = ExecutorIntentMixin._collect_intent_terms("买卖合同纠纷", mapping)
        assert terms == []

    def test_deduplication(self) -> None:
        mapping = ((("违约",), "违约责任"),)
        terms = ExecutorIntentMixin._collect_intent_terms("被告违约违约多次违约", mapping)
        # Should only appear once
        assert terms.count("违约责任") == 1


class TestExtractRelationTermsDynamic:

    def test_basic(self) -> None:
        terms = ExecutorIntentMixin._extract_relation_terms_dynamic("买卖合同纠纷案")
        assert len(terms) > 0

    def test_empty_text(self) -> None:
        terms = ExecutorIntentMixin._extract_relation_terms_dynamic("")
        assert terms == []

    def test_with_extra_regexes(self) -> None:
        text = "股权转让合同纠纷案"
        terms = ExecutorIntentMixin._extract_relation_terms_dynamic(
            text, extra_regexes=[r"股权转让[合同纠纷]*"]
        )
        assert len(terms) > 0


class TestSplitIntentClauses:

    def test_chinese_punctuation(self) -> None:
        clauses = ExecutorIntentMixin._split_intent_clauses("原告主张违约金，被告拒绝赔偿。法院判决")
        assert len(clauses) >= 2

    def test_empty_text(self) -> None:
        clauses = ExecutorIntentMixin._split_intent_clauses("")
        assert clauses == []

    def test_short_segments_filtered(self) -> None:
        clauses = ExecutorIntentMixin._split_intent_clauses("a，b。正常长度的文本句子")
        # "a" and "b" are too short (len < 2 after stripping)
        for clause in clauses:
            assert len(clause) >= 2


class TestCompactClauseByHints:

    def test_with_matching_hint(self) -> None:
        clause = "被告逾期交货导致原告损失"
        result = ExecutorIntentMixin._compact_clause_by_hints(
            clause, hints=("逾期", "交货"), max_chars=16,
        )
        assert len(result) > 0
        assert len(result) <= 16

    def test_no_matching_hint(self) -> None:
        clause = "正常文本无匹配提示"
        result = ExecutorIntentMixin._compact_clause_by_hints(
            clause, hints=("违约",), max_chars=16,
        )
        assert result == "正常文本无匹配提示"

    def test_empty_clause(self) -> None:
        result = ExecutorIntentMixin._compact_clause_by_hints(
            "", hints=("违约",), max_chars=16,
        )
        assert result == ""

    def test_strips_leading_labels(self) -> None:
        clause = "原告主张被告违约"
        result = ExecutorIntentMixin._compact_clause_by_hints(
            clause, hints=("违约",), max_chars=20,
        )
        # Should strip "原告" prefix
        assert not result.startswith("原告")


class TestNormalizeRelationTerm:

    def test_basic(self) -> None:
        assert ExecutorIntentMixin._normalize_relation_term("买卖合同纠纷") == "买卖合同纠纷"

    def test_adds纠纷_suffix(self) -> None:
        result = ExecutorIntentMixin._normalize_relation_term("劳动合同")
        assert result == "劳动合同纠纷"

    def test_labor_dispute_normalization(self) -> None:
        assert ExecutorIntentMixin._normalize_relation_term("劳动") == "劳动争议"
        assert ExecutorIntentMixin._normalize_relation_term("劳动纠纷") == "劳动争议"

    def test_removes案_suffix(self) -> None:
        result = ExecutorIntentMixin._normalize_relation_term("买卖合同纠纷案")
        assert result == "买卖合同纠纷"

    def test_empty(self) -> None:
        assert ExecutorIntentMixin._normalize_relation_term("") == ""

    def test_strips_punctuation(self) -> None:
        result = ExecutorIntentMixin._normalize_relation_term("  买卖合同  ")
        assert result == "买卖合同纠纷"


class TestLooksLikeRelationTerm:

    def test_ends_with纠纷(self) -> None:
        assert ExecutorIntentMixin._looks_like_relation_term("买卖合同纠纷") is True

    def test_ends_with争议(self) -> None:
        assert ExecutorIntentMixin._looks_like_relation_term("劳动争议") is True

    def test_ends_with之诉(self) -> None:
        assert ExecutorIntentMixin._looks_like_relation_term("侵权之诉") is True

    def test_contains合同(self) -> None:
        assert ExecutorIntentMixin._looks_like_relation_term("买卖合同") is True

    def test_no_match(self) -> None:
        assert ExecutorIntentMixin._looks_like_relation_term("违约金") is False

    def test_empty(self) -> None:
        assert ExecutorIntentMixin._looks_like_relation_term("") is False


class TestContainsAnyHint:

    def test_matches(self) -> None:
        assert ExecutorIntentMixin._contains_any_hint("被告逾期交货", ("逾期", "迟延")) is True

    def test_no_match(self) -> None:
        assert ExecutorIntentMixin._contains_any_hint("正常文本", ("违约", "损失")) is False

    def test_empty_text(self) -> None:
        assert ExecutorIntentMixin._contains_any_hint("", ("违约",)) is False


class TestParseRuleItems:

    def test_basic(self) -> None:
        result = ExecutorIntentMixin._parse_rule_items(
            "违约金,滞纳金;赔偿损失", max_items=10, max_len=20,
        )
        assert len(result) == 3

    def test_empty(self) -> None:
        result = ExecutorIntentMixin._parse_rule_items("", max_items=10, max_len=20)
        assert result == []

    def test_deduplication(self) -> None:
        result = ExecutorIntentMixin._parse_rule_items(
            "违约金,违约金,违约金", max_items=10, max_len=20,
        )
        assert len(result) == 1

    def test_max_items_limit(self) -> None:
        result = ExecutorIntentMixin._parse_rule_items(
            "a,b,c,d,e,f", max_items=3, max_len=20,
        )
        assert len(result) == 3

    def test_max_len_truncation(self) -> None:
        result = ExecutorIntentMixin._parse_rule_items(
            "这是一个很长的文本", max_items=10, max_len=4,
        )
        assert len(result[0]) <= 4


class TestParseIntWithBounds:

    def test_valid_int(self) -> None:
        assert ExecutorIntentMixin._parse_int_with_bounds("3", default=2, min_value=1, max_value=6) == 3

    def test_below_min(self) -> None:
        assert ExecutorIntentMixin._parse_int_with_bounds("0", default=2, min_value=1, max_value=6) == 1

    def test_above_max(self) -> None:
        assert ExecutorIntentMixin._parse_int_with_bounds("10", default=2, min_value=1, max_value=6) == 6

    def test_invalid(self) -> None:
        assert ExecutorIntentMixin._parse_int_with_bounds("abc", default=2, min_value=1, max_value=6) == 2

    def test_empty(self) -> None:
        assert ExecutorIntentMixin._parse_int_with_bounds("", default=2, min_value=1, max_value=6) == 2


class TestMergeHintOverrides:

    def test_basic(self) -> None:
        defaults = ("违约", "逾期")
        extras = ["迟延", "拒绝"]
        result = ExecutorIntentMixin._merge_hint_overrides(defaults, extras)
        assert len(result) == 4
        assert "违约" in result
        assert "迟延" in result

    def test_deduplication(self) -> None:
        defaults = ("违约", "逾期")
        extras = ["违约"]  # duplicate
        result = ExecutorIntentMixin._merge_hint_overrides(defaults, extras)
        assert len(result) == 2

    def test_empty_extras(self) -> None:
        defaults = ("违约", "逾期")
        result = ExecutorIntentMixin._merge_hint_overrides(defaults, [])
        assert result == ("违约", "逾期")


class TestSplitTokens:

    def test_basic(self) -> None:
        result = ExecutorIntentMixin._split_tokens("买卖合同 违约 价差")
        assert result == ["买卖合同", "违约", "价差"]

    def test_chinese_separators(self) -> None:
        result = ExecutorIntentMixin._split_tokens("买卖合同，违约；价差、损失")
        assert "买卖合同" in result
        assert "违约" in result

    def test_short_tokens_filtered(self) -> None:
        result = ExecutorIntentMixin._split_tokens("ab c def")
        assert "c" not in result  # single char filtered
        assert "ab" in result
        assert "def" in result

    def test_empty(self) -> None:
        result = ExecutorIntentMixin._split_tokens("")
        assert result == []


class TestIsLocationOrCourtToken:

    def test_court_token(self) -> None:
        assert ExecutorIntentMixin._is_location_or_court_token("北京市朝阳区人民法院") is True

    def test_province_city(self) -> None:
        assert ExecutorIntentMixin._is_location_or_court_token("北京市") is True

    def test_regular_token(self) -> None:
        assert ExecutorIntentMixin._is_location_or_court_token("买卖合同") is False

    def test_empty(self) -> None:
        assert ExecutorIntentMixin._is_location_or_court_token("") is False


class TestExtractSummaryTerms:

    def test_basic(self) -> None:
        with patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator") as mock_sl:
            mock_sl.get_system_config_service.side_effect = Exception("no db")
            result = ExecutorIntentMixin._extract_summary_terms(
                "原告与被告签订买卖合同，被告违约导致价差损失"
            )
            assert isinstance(result, list)
            assert len(result) > 0

    def test_empty_summary(self) -> None:
        result = ExecutorIntentMixin._extract_summary_terms("")
        assert result == []


class TestDedupeTokens:

    def test_basic(self) -> None:
        result = ExecutorIntentMixin._dedupe_tokens(["a", "b", "a", "c"], max_tokens=10)
        assert result == ["a", "b", "c"]

    def test_max_tokens(self) -> None:
        result = ExecutorIntentMixin._dedupe_tokens(["a", "b", "c", "d"], max_tokens=2)
        assert len(result) == 2

    def test_case_insensitive(self) -> None:
        result = ExecutorIntentMixin._dedupe_tokens(["Hello", "hello"], max_tokens=10)
        assert len(result) == 1

    def test_empty(self) -> None:
        result = ExecutorIntentMixin._dedupe_tokens([], max_tokens=10)
        assert result == []


class TestLoadIntentRuleOverrides:

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_service_unavailable_returns_defaults(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no config")
        result = ExecutorIntentMixin._load_intent_rule_overrides()
        assert result["relation_regex_extra"] == []
        assert result["low_conf_limit"] == 2

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_service_available_parses_config(self, mock_sl: MagicMock) -> None:
        mock_config = MagicMock()
        mock_config.get_value.return_value = "违约金\n滞纳金|罚金"
        mock_sl.get_system_config_service.return_value = mock_config
        result = ExecutorIntentMixin._load_intent_rule_overrides()
        assert isinstance(result["breach_hint_extra"], list)


class TestIntentMappingIntegration:

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_breach_and_damage_combined(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        text = "被告违约未交货，原告主张价差损失和违约金赔偿"
        result = ExecutorIntentMixin._extract_intent_slots_with_confidence(text)
        assert len(result["breach_high"]) > 0
        assert len(result["damage_high"]) > 0

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_remedy_mapping(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        text = "原告请求继续履行合同并返还款项"
        result = ExecutorIntentMixin._extract_intent_slots_with_confidence(text)
        assert len(result["remedy_high"]) > 0
