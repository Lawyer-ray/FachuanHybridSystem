"""ExecutorQueryMixin / ExecutorScoringMixin / ExecutorIntentMixin deeper coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.legal_research.services.executor_components.intent_mixin import ExecutorIntentMixin
from apps.legal_research.services.executor_components.query_mixin import ExecutorQueryMixin
from apps.legal_research.services.executor_components.scoring_mixin import ExecutorScoringMixin


# Combined class for tests that need methods from multiple mixins
class _FullExecutor(ExecutorQueryMixin, ExecutorIntentMixin, ExecutorScoringMixin):
    pass


# ── _FullExecutor ─────────────────────────────────────────


@pytest.mark.django_db
class TestQueryMixinBuildKeywords:
    """_build_search_keywords and related builder methods."""

    def test_build_search_keywords_returns_list(self):
        result = _FullExecutor._build_search_keywords("买卖合同纠纷", "原告起诉被告要求赔偿")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_build_search_keywords_deduplicates(self):
        result = _FullExecutor._build_search_keywords("买卖合同", "买卖合同纠纷")
        lower_set = {q.lower() for q in result}
        assert len(lower_set) == len(result)

    def test_build_search_keyword_with_empty(self):
        result = _FullExecutor._build_search_keyword("", "")
        # Should still return something (synonym expansion of tokens)
        assert isinstance(result, str)

    def test_build_fallback_search_keyword(self):
        result = _FullExecutor._build_fallback_search_keyword("违约 朝阳区法院", "合同违约纠纷")
        assert isinstance(result, str)
        # Location tokens should be filtered
        assert "朝阳区" not in result or "法院" not in result

    def test_build_scoring_keyword(self):
        result = _FullExecutor._build_scoring_keyword("买卖合同纠纷", "原告要求赔偿损失")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_summary_search_keyword(self):
        result = _FullExecutor._build_summary_search_keyword("买卖合同纠纷，原告要求被告赔偿价差损失")
        assert isinstance(result, str)

    def test_build_feedback_search_keyword(self):
        result = _FullExecutor._build_feedback_search_keyword(
            "买卖合同", "纠纷案", ["价差损失", "违约金"]
        )
        assert isinstance(result, str)
        assert len(result) > 0


class TestQueryMixinLLMVariants:
    """_generate_llm_query_variants and _parse_query_variants."""

    def test_parse_query_variants_valid_json(self):
        content = '{"queries": ["买卖合同纠纷 赔偿", "借款合同 利息"]}'
        result = _FullExecutor._parse_query_variants(content=content, max_variants=5)
        assert isinstance(result, list)
        assert len(result) <= 5

    def test_parse_query_variants_empty(self):
        result = _FullExecutor._parse_query_variants(content="", max_variants=5)
        assert result == []

    def test_parse_query_variants_invalid_json(self):
        result = _FullExecutor._parse_query_variants(content="not json at all", max_variants=3)
        assert isinstance(result, list)

    def test_parse_query_variants_malformed_json_with_embedded(self):
        content = 'some text {"queries": ["买卖合同 纠纷"]} more text'
        result = _FullExecutor._parse_query_variants(content=content, max_variants=5)
        assert isinstance(result, list)

    def test_parse_query_variants_string_value(self):
        content = '{"queries": "买卖合同纠纷"}'
        result = _FullExecutor._parse_query_variants(content=content, max_variants=5)
        assert isinstance(result, list)

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_generate_llm_query_variants_success(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"queries": ["买卖合同 赔偿损失", "货物买卖 违约"]}'
        mock_llm.chat.return_value = mock_response
        mock_llm_factory.return_value = mock_llm

        result = _FullExecutor._generate_llm_query_variants(
            keyword="买卖合同纠纷",
            case_summary="原告起诉被告要求赔偿价差损失",
            model=None,
            max_variants=2,
        )
        assert isinstance(result, list)

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_generate_llm_query_variants_llm_error(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = RuntimeError("LLM unavailable")
        mock_llm_factory.return_value = mock_llm

        result = _FullExecutor._generate_llm_query_variants(
            keyword="买卖合同纠纷",
            case_summary="原告起诉被告要求赔偿",
            model=None,
            max_variants=2,
        )
        assert result == []

    def test_generate_llm_query_variants_zero_limit(self):
        result = _FullExecutor._generate_llm_query_variants(
            keyword="test", case_summary="test", model=None, max_variants=0
        )
        assert result == []

    def test_generate_llm_query_variants_short_context(self):
        result = _FullExecutor._generate_llm_query_variants(
            keyword="ab", case_summary="cd", model=None, max_variants=2
        )
        assert result == []


class TestQueryMixinLegalElements:
    """_extract_legal_elements and related methods."""

    def test_extract_legal_elements_short_summary(self):
        result = _FullExecutor._extract_legal_elements(case_summary="短")
        assert result == {}

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_extract_legal_elements_success(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"cause_of_action": "买卖合同纠纷", "legal_relation": "买卖合同", "dispute_focus": ["价差损失"], "damage_type": ["损失赔偿"], "key_facts": ["未交货"]}'
        mock_llm.chat.return_value = mock_response
        mock_llm_factory.return_value = mock_llm

        result = _FullExecutor._extract_legal_elements(
            case_summary="原告与被告签订买卖合同，被告未交货，原告要求赔偿价差损失"
        )
        assert isinstance(result, dict)

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_extract_legal_elements_llm_error(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = RuntimeError("fail")
        mock_llm_factory.return_value = mock_llm

        result = _FullExecutor._extract_legal_elements(case_summary="足够长的案情描述用于测试")
        assert result == {}

    def test_sanitize_elements_filters_placeholders(self):
        raw = {
            "cause_of_action": "案由（如：买卖合同纠纷）",
            "dispute_focus": ["争议焦点1", "真实争议"],
            "damage_type": ["如：xxx", "实际损失"],
        }
        result = _FullExecutor._sanitize_elements(raw)
        assert result["cause_of_action"] == ""
        assert "真实争议" in result["dispute_focus"]
        assert "实际损失" in result["damage_type"]

    def test_build_element_based_queries(self):
        elements = {
            "cause_of_action": "买卖合同纠纷",
            "legal_relation": "买卖合同",
            "dispute_focus": ["价差损失"],
            "damage_type": ["赔偿"],
            "key_facts": ["未交货"],
        }
        queries = _FullExecutor._build_element_based_queries(elements)
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_build_element_based_queries_empty(self):
        assert _FullExecutor._build_element_based_queries({}) == []

    def test_build_field_queries_from_elements(self):
        elements = {
            "cause_of_action": "买卖合同纠纷",
            "dispute_focus": ["价差损失", "违约金"],
            "damage_type": ["赔偿损失"],
            "key_facts": ["未交货"],
        }
        result = _FullExecutor._build_field_queries_from_elements(elements)
        assert isinstance(result, list)
        assert any(q["field"] == "causeOfAction" for q in result)

    def test_build_field_queries_from_elements_empty(self):
        assert _FullExecutor._build_field_queries_from_elements({}) == []


class TestQueryMixinMergeAndPrefilter:
    """_merge_query_candidates and _title_prefilter."""

    def test_merge_query_candidates_deduplicates(self):
        base = ["买卖合同 赔偿", "借款合同"]
        extra = ["买卖合同 赔偿", "新查询"]
        result = _FullExecutor._merge_query_candidates(base, extra, max_queries=10)
        assert len(result) == 3

    def test_merge_query_candidates_respects_max(self):
        base = ["q1", "q2", "q3"]
        result = _FullExecutor._merge_query_candidates(base, [], max_queries=2)
        assert len(result) <= 2

    def test_title_prefilter_empty_hint(self):
        assert _FullExecutor._title_prefilter(
            keyword="test", case_summary="test", title_hint="", min_overlap=0.15
        ) is True

    def test_title_prefilter_good_overlap(self):
        assert _FullExecutor._title_prefilter(
            keyword="买卖合同纠纷",
            case_summary="赔偿损失",
            title_hint="买卖合同纠纷一案",
            min_overlap=0.1,
        ) is True

    def test_title_prefilter_low_overlap(self):
        result = _FullExecutor._title_prefilter(
            keyword="买卖合同纠纷 赔偿",
            case_summary="原告要求被告赔偿价差损失",
            title_hint="完全无关的标题",
            min_overlap=0.5,
        )
        assert isinstance(result, bool)


# ── ExecutorScoringMixin ───────────────────────────────────────


class TestScoringMixinNormalization:
    """Score normalization and keyword overlap."""

    def test_normalize_score_clamps_high(self):
        assert ExecutorScoringMixin._normalize_score(1.5) == 1.0

    def test_normalize_score_clamps_low(self):
        assert ExecutorScoringMixin._normalize_score(-0.5) == 0.0

    def test_normalize_score_invalid(self):
        assert ExecutorScoringMixin._normalize_score(None) == 0.0
        assert ExecutorScoringMixin._normalize_score("abc") == 0.0

    def test_keyword_overlap_basic(self):
        detail = MagicMock()
        detail.title = "买卖合同纠纷判决书"
        detail.case_digest = "原告起诉被告要求赔偿"
        detail.content_text = "本案系买卖合同纠纷"
        score = ExecutorScoringMixin._keyword_overlap(keyword="买卖合同 纠纷", detail=detail)
        assert score > 0

    def test_keyword_overlap_no_match(self):
        detail = MagicMock()
        detail.title = "无关标题"
        detail.case_digest = "无关内容"
        detail.content_text = ""
        score = ExecutorScoringMixin._keyword_overlap(keyword="xyz 买卖", detail=detail)
        assert isinstance(score, float)


class TestScoringMixinThresholds:
    """Threshold and budget calculations."""

    def test_coarse_threshold(self):
        threshold = ExecutorScoringMixin._coarse_threshold(0.8)
        assert 0 < threshold <= ExecutorScoringMixin.COARSE_RECALL_THRESHOLD_CEIL

    def test_should_rerank_below_minimum(self):
        assert ExecutorScoringMixin._should_rerank(
            coarse_score=0.15, threshold=0.3, rerank_used=0, rerank_budget=10
        ) is False

    def test_should_rerank_above_threshold(self):
        assert ExecutorScoringMixin._should_rerank(
            coarse_score=0.5, threshold=0.3, rerank_used=0, rerank_budget=10
        ) is True

    def test_should_rerank_within_budget(self):
        assert ExecutorScoringMixin._should_rerank(
            coarse_score=0.25, threshold=0.3, rerank_used=0, rerank_budget=10
        ) is True

    def test_should_rerank_over_budget(self):
        assert ExecutorScoringMixin._should_rerank(
            coarse_score=0.25, threshold=0.3, rerank_used=10, rerank_budget=10
        ) is False


class TestScoringMixinDualReview:
    """_merge_dual_review_scores."""

    def test_merge_dual_review_scores_basic(self):
        primary = MagicMock()
        primary.score = 0.8
        primary.reason = "主判理由"
        primary.model = "model-a"

        reviewed = MagicMock()
        reviewed.score = 0.75
        reviewed.reason = "复核理由"
        reviewed.model = "model-b"

        from apps.legal_research.services.executor_components.policy_mixin import DualReviewPolicy

        policy = DualReviewPolicy(
            enabled=True,
            review_model="model-b",
            trigger_floor=0.6,
            primary_weight=0.6,
            secondary_weight=0.4,
            gap_tolerance=0.2,
            required_min=0.3,
        )
        score, reason, model, metadata = ExecutorScoringMixin._merge_dual_review_scores(
            primary=primary, reviewed=reviewed, dual_review_policy=policy
        )
        assert 0 <= score <= 1
        assert isinstance(reason, str)
        assert "review:" in model
        assert "dual_review" in metadata


class TestScoringMixinCoarseRecall:
    """_coarse_recall with mocked similarity."""

    def test_coarse_recall_with_scorer(self):
        similarity = MagicMock()
        coarse_result = MagicMock()
        coarse_result.score = 0.6
        coarse_result.reason = "测试理由"
        similarity.coarse_recall_score.return_value = coarse_result

        detail = MagicMock()
        detail.title = "买卖合同纠纷"
        detail.case_digest = "赔偿损失"
        detail.content_text = "案件内容"
        detail.doc_id_unquoted = "doc1"
        detail.doc_id_raw = "doc1"

        score, reason = ExecutorScoringMixin._coarse_recall(
            similarity=similarity, keyword="买卖合同", case_summary="纠纷", detail=detail
        )
        assert 0 <= score <= 1
        assert isinstance(reason, str)

    def test_coarse_recall_fallback(self):
        similarity = MagicMock()
        del similarity.coarse_recall_score  # No scorer method

        detail = MagicMock()
        detail.title = "买卖合同纠纷判决书"
        detail.case_digest = ""
        detail.content_text = ""
        detail.doc_id_unquoted = "doc1"
        detail.doc_id_raw = "doc1"

        score, reason = ExecutorScoringMixin._coarse_recall(
            similarity=similarity, keyword="买卖合同", case_summary="纠纷", detail=detail
        )
        assert isinstance(score, float)
        assert "fallback" in reason


# ── ExecutorIntentMixin ────────────────────────────────────────


@pytest.mark.django_db
class TestIntentMixinExtraction:
    """Intent slot extraction."""

    def test_extract_intent_slots_basic(self):
        text = "买卖合同纠纷，被告未交货，原告要求赔偿价差损失"
        relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
        assert isinstance(relation, list)
        assert isinstance(breach, list)
        assert isinstance(damage, list)
        assert isinstance(remedy, list)

    def test_extract_intent_slots_empty(self):
        relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots("")
        assert relation == []
        assert breach == []
        assert damage == []
        assert remedy == []

    def test_extract_intent_slots_with_confidence_returns_dict(self):
        text = "借款合同纠纷，被告逾期未还款，原告主张违约金"
        result = ExecutorIntentMixin._extract_intent_slots_with_confidence(text)
        assert "relation_high" in result
        assert "breach_high" in result
        assert "damage_high" in result
        assert "remedy_high" in result
        assert "low_conf_limit" in result

    def test_extract_intent_slots_with_confidence_empty(self):
        result = ExecutorIntentMixin._extract_intent_slots_with_confidence("")
        assert result["relation_high"] == []
        assert result["breach_high"] == []


class TestIntentMixinHelpers:
    """Helper methods."""

    def test_collect_intent_terms_match(self):
        mapping = (
            (("买卖", "买卖合同"), "买卖合同纠纷"),
            (("借款",), "借款合同纠纷"),
        )
        result = ExecutorIntentMixin._collect_intent_terms("原告与被告签订买卖合同", mapping)
        assert "买卖合同纠纷" in result

    def test_collect_intent_terms_no_match(self):
        mapping = ((("不存在的词",), "test"),)
        result = ExecutorIntentMixin._collect_intent_terms("普通文本", mapping)
        assert result == []

    def test_extract_relation_terms_dynamic(self):
        text = "买卖合同纠纷一案"
        result = ExecutorIntentMixin._extract_relation_terms_dynamic(text)
        assert isinstance(result, list)
        assert any("买卖合同" in t for t in result)

    def test_normalize_relation_term(self):
        assert ExecutorIntentMixin._normalize_relation_term("买卖合同") == "买卖合同纠纷"
        assert ExecutorIntentMixin._normalize_relation_term("劳动") == "劳动争议"
        assert ExecutorIntentMixin._normalize_relation_term("买卖合同纠纷") == "买卖合同纠纷"

    def test_looks_like_relation_term(self):
        assert ExecutorIntentMixin._looks_like_relation_term("买卖合同纠纷") is True
        assert ExecutorIntentMixin._looks_like_relation_term("劳动争议") is True
        assert ExecutorIntentMixin._looks_like_relation_term("赔偿") is False

    def test_contains_any_hint(self):
        assert ExecutorIntentMixin._contains_any_hint("被告违约", ("违约", "逾期")) is True
        assert ExecutorIntentMixin._contains_any_hint("正常文本", ("违约",)) is False

    def test_split_intent_clauses(self):
        clauses = ExecutorIntentMixin._split_intent_clauses("原告起诉，被告违约。要求赔偿损失")
        assert isinstance(clauses, list)
        assert len(clauses) > 0

    def test_compact_clause_by_hints(self):
        result = ExecutorIntentMixin._compact_clause_by_hints(
            "被告逾期未交货导致原告停工损失", hints=("逾期", "停工"), max_chars=16
        )
        assert isinstance(result, str)
        assert len(result) <= 16

    def test_is_location_or_court_token(self):
        assert ExecutorIntentMixin._is_location_or_court_token("朝阳区法院") is True
        assert ExecutorIntentMixin._is_location_or_court_token("北京市") is True
        assert ExecutorIntentMixin._is_location_or_court_token("买卖合同") is False

    def test_dedupe_tokens(self):
        result = ExecutorIntentMixin._dedupe_tokens(["a", "b", "a", "c"], max_tokens=10)
        assert result == ["a", "b", "c"]

    def test_dedupe_tokens_max(self):
        result = ExecutorIntentMixin._dedupe_tokens(["a", "b", "c"], max_tokens=2)
        assert len(result) == 2


class TestIntentMixinRuleOverrides:
    """Rule override loading and parsing."""

    def test_parse_rule_items_basic(self):
        result = ExecutorIntentMixin._parse_rule_items("a|b|c", max_items=10, max_len=20)
        assert result == ["a", "b", "c"]

    def test_parse_rule_items_empty(self):
        assert ExecutorIntentMixin._parse_rule_items("", max_items=10, max_len=20) == []

    def test_parse_rule_items_dedup(self):
        result = ExecutorIntentMixin._parse_rule_items("a|a|b", max_items=10, max_len=20)
        assert result == ["a", "b"]

    def test_parse_int_with_bounds(self):
        assert ExecutorIntentMixin._parse_int_with_bounds("5", default=2, min_value=1, max_value=10) == 5
        assert ExecutorIntentMixin._parse_int_with_bounds("", default=2, min_value=1, max_value=10) == 2
        assert ExecutorIntentMixin._parse_int_with_bounds("0", default=2, min_value=1, max_value=10) == 1
        assert ExecutorIntentMixin._parse_int_with_bounds("100", default=2, min_value=1, max_value=10) == 10

    def test_merge_hint_overrides(self):
        result = ExecutorIntentMixin._merge_hint_overrides(("违约", "逾期"), ["拖欠", "违约"])
        assert "违约" in result
        assert "逾期" in result
        assert "拖欠" in result

    @patch("apps.core.interfaces.ServiceLocator.get_system_config_service")
    def test_load_intent_rule_overrides_success(self, mock_config_factory):
        mock_config = MagicMock()
        mock_config.get_value.return_value = ""
        mock_config_factory.return_value = mock_config

        result = ExecutorIntentMixin._load_intent_rule_overrides()
        assert "relation_regex_extra" in result
        assert "low_conf_limit" in result

    @patch("apps.core.interfaces.ServiceLocator.get_system_config_service")
    def test_load_intent_rule_overrides_error(self, mock_config_factory):
        mock_config_factory.side_effect = RuntimeError("no config")

        result = ExecutorIntentMixin._load_intent_rule_overrides()
        assert result["low_conf_limit"] == 2


class TestIntentMixinSummaryTerms:
    """_extract_summary_terms."""

    def test_extract_summary_terms_basic(self):
        terms = ExecutorIntentMixin._extract_summary_terms("买卖合同纠纷，被告未交货，原告要求赔偿价差损失")
        assert isinstance(terms, list)
        assert len(terms) > 0

    def test_extract_summary_terms_empty(self):
        assert ExecutorIntentMixin._extract_summary_terms("") == []

    def test_extract_summary_terms_filters_stopwords(self):
        terms = ExecutorIntentMixin._extract_summary_terms("原告在法院起诉被告要求赔偿")
        # "原告", "被告", "法院" should be filtered as stopwords
        assert "原告" not in terms
        assert "被告" not in terms
