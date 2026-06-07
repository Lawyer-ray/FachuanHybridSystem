"""Tests for apps.legal_research.services.executor_components.query_mixin._TestQuery."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


from apps.legal_research.services.executor_components.query_mixin import ExecutorQueryMixin
from apps.legal_research.services.executor_components.intent_mixin import ExecutorIntentMixin


# Combined class so cls._split_tokens, cls._dedupe_tokens etc. resolve via MRO
class _TestQuery(ExecutorQueryMixin, ExecutorIntentMixin):
    """Minimal combined class for testing query methods that rely on intent_mixin utilities."""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildSearchKeyword:

    def test_with_keyword(self) -> None:
        result = _TestQuery._build_search_keyword("买卖合同 违约", "纠纷描述")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_keyword_falls_back_to_summary(self) -> None:
        result = _TestQuery._build_search_keyword("", "原告与被告纠纷")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_both_empty(self) -> None:
        result = _TestQuery._build_search_keyword("", "")
        assert isinstance(result, str)


class TestBuildFallbackSearchKeyword:

    def test_filters_location_tokens(self) -> None:
        result = _TestQuery._build_fallback_search_keyword(
            "北京 买卖合同 违约", "纠纷描述"
        )
        # "北京" should be filtered out
        assert "北京" not in result or "买卖" in result

    def test_includes_summary_terms(self) -> None:
        result = _TestQuery._build_fallback_search_keyword(
            "违约", "价差损失合同纠纷"
        )
        assert isinstance(result, str)
        assert len(result) > 0


class TestBuildScoringKeyword:

    def test_filters_court_tokens(self) -> None:
        result = _TestQuery._build_scoring_keyword(
            "北京市朝阳区人民法院 买卖合同 违约", "合同纠纷"
        )
        # Court token should be filtered
        assert "朝阳区人民法院" not in result

    def test_empty_keyword_uses_summary(self) -> None:
        result = _TestQuery._build_scoring_keyword("", "买卖合同纠纷")
        assert isinstance(result, str)
        assert len(result) > 0


class TestBuildSummarySearchKeyword:

    def test_basic(self) -> None:
        result = _TestQuery._build_summary_search_keyword(
            "原告与被告签订买卖合同，被告逾期交货导致价差损失"
        )
        assert isinstance(result, str)

    def test_empty_summary(self) -> None:
        result = _TestQuery._build_summary_search_keyword("")
        assert result == ""


class TestBuildFeedbackSearchKeyword:

    def test_includes_feedback_terms(self) -> None:
        result = _TestQuery._build_feedback_search_keyword(
            "买卖合同", "纠纷摘要", ["价差损失", "违约金"]
        )
        assert isinstance(result, str)
        assert len(result) > 0


class TestBuildSearchKeywords:

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_returns_deduped_list(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        result = _TestQuery._build_search_keywords(
            "买卖合同 违约", "原告与被告纠纷"
        )
        assert isinstance(result, list)
        assert len(result) >= 1
        # Check deduplication
        seen: set[str] = set()
        for q in result:
            assert q.lower() not in seen
            seen.add(q.lower())

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_empty_inputs(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        result = _TestQuery._build_search_keywords("", "")
        assert isinstance(result, list)


class TestBuildIntentSearchKeywords:

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_with_relation_and_breach(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        result = _TestQuery._build_intent_search_keywords(
            "买卖合同 违约 价差损失", "原告与被告签订买卖合同，被告违约导致价差损失"
        )
        assert isinstance(result, list)

    def test_empty_context(self) -> None:
        result = _TestQuery._build_intent_search_keywords("", "")
        assert result == []

    @patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
    def test_max_queries_limited(self, mock_sl: MagicMock) -> None:
        mock_sl.get_system_config_service.side_effect = Exception("no db")
        result = _TestQuery._build_intent_search_keywords(
            "买卖合同 违约 损失 赔偿 逾期", "买卖合同纠纷案违约价差损失赔偿"
        )
        assert len(result) <= _TestQuery.INTENT_QUERY_MAX


class TestMergeQueryCandidates:

    def test_deduplicates(self) -> None:
        result = _TestQuery._merge_query_candidates(
            ["query a", "query b"], ["query b", "query c"]
        )
        assert len(result) == 3  # a, b, c

    def test_max_queries(self) -> None:
        result = _TestQuery._merge_query_candidates(
            ["q1", "q2", "q3", "q4", "q5"],
            ["q6", "q7", "q8"],
            max_queries=3,
        )
        assert len(result) == 3

    def test_strips_whitespace(self) -> None:
        result = _TestQuery._merge_query_candidates(
            ["  query a  ", " query b "], []
        )
        assert result[0] == "query a"
        assert result[1] == "query b"

    def test_empty_queries_filtered(self) -> None:
        result = _TestQuery._merge_query_candidates(
            ["", "  ", "valid"], []
        )
        assert result == ["valid"]


class TestExpandTermsWithSynonyms:

    def test_empty_tokens(self) -> None:
        result = _TestQuery._expand_terms_with_synonyms([], max_tokens=12)
        assert result == []

    def test_known_synonym_expands(self) -> None:
        # "违约责任" is in LEGAL_SYNONYM_GROUPS
        result = _TestQuery._expand_terms_with_synonyms(
            ["违约责任"], max_tokens=12,
        )
        assert len(result) >= 1
        assert "违约责任" in result

    def test_max_tokens_respected(self) -> None:
        result = _TestQuery._expand_terms_with_synonyms(
            ["违约责任", "赔偿损失", "买卖合同纠纷"], max_tokens=4,
        )
        assert len(result) <= 4

    def test_deduplication(self) -> None:
        result = _TestQuery._expand_terms_with_synonyms(
            ["违约", "违约"], max_tokens=12,
        )
        # "违约" should appear only once
        assert result.count("违约") == 1


class TestMatchSynonymGroup:

    def test_exact_match(self) -> None:
        group = _TestQuery._match_synonym_group("违约责任")
        assert group is not None
        assert "违约责任" in group

    def test_partial_match(self) -> None:
        # "未履行" is a member of the breach synonym group
        group = _TestQuery._match_synonym_group("未履行")
        assert group is not None

    def test_no_match(self) -> None:
        group = _TestQuery._match_synonym_group("完全不相关的词")
        assert group is None

    def test_empty_token(self) -> None:
        group = _TestQuery._match_synonym_group("")
        assert group is None


class TestLoadSynonymGroups:

    def test_returns_tuple(self) -> None:
        result = _TestQuery._load_synonym_groups()
        assert isinstance(result, tuple)
        assert len(result) > 0

    def test_caching(self) -> None:
        # Reset cache
        _TestQuery._synonym_groups_cache = None
        _TestQuery._synonym_groups_cache_ts = 0.0
        with patch("apps.legal_research.services.executor_components.query_mixin.ServiceLocator") as mock_sl:
            mock_sl.get_system_config_service.return_value = MagicMock()
            result1 = _TestQuery._load_synonym_groups()
            result2 = _TestQuery._load_synonym_groups()
        assert result1 is result2


class TestTitlePrefilter:

    def test_empty_title_passes(self) -> None:
        assert _TestQuery._title_prefilter(
            keyword="违约", case_summary="纠纷", title_hint="", min_overlap=0.15,
        ) is True

    def test_matching_title_passes(self) -> None:
        assert _TestQuery._title_prefilter(
            keyword="买卖合同 违约", case_summary="纠纷",
            title_hint="买卖合同违约纠纷案", min_overlap=0.15,
        ) is True

    def test_no_overlap_fails(self) -> None:
        assert _TestQuery._title_prefilter(
            keyword="劳动争议", case_summary="工伤",
            title_hint="房屋租赁纠纷", min_overlap=0.15,
        ) is False

    def test_low_min_overlap_always_pass(self) -> None:
        assert _TestQuery._title_prefilter(
            keyword="x", case_summary="y",
            title_hint="unrelated", min_overlap=0.0,
        ) is True


class TestParseQueryVariants:

    def test_valid_json(self) -> None:
        content = json.dumps({"queries": ["买卖合同 违约", "货物买卖纠纷"]})
        result = _TestQuery._parse_query_variants(content=content, max_variants=5)
        assert len(result) == 2

    def test_json_in_markdown(self) -> None:
        content = '```json\n{"queries": ["违约 损失"]}\n```'
        result = _TestQuery._parse_query_variants(content=content, max_variants=5)
        assert len(result) >= 1

    def test_empty_content(self) -> None:
        result = _TestQuery._parse_query_variants(content="", max_variants=5)
        assert result == []

    def test_non_json_fallback(self) -> None:
        content = "买卖合同 违约\n价差损失 赔偿"
        result = _TestQuery._parse_query_variants(content=content, max_variants=5)
        assert len(result) >= 1

    def test_max_variants_limit(self) -> None:
        content = json.dumps({"queries": ["q1", "q2", "q3", "q4", "q5"]})
        result = _TestQuery._parse_query_variants(content=content, max_variants=2)
        assert len(result) == 2


class TestBuildElementBasedQueries:

    def test_full_elements(self) -> None:
        elements = {
            "cause_of_action": "买卖合同纠纷",
            "legal_relation": "买卖合同",
            "dispute_focus": ["逾期交货", "价差损失"],
            "damage_type": ["价差损失"],
            "key_facts": ["未按时交货"],
        }
        result = _TestQuery._build_element_based_queries(elements)
        assert len(result) >= 1

    def test_empty_elements(self) -> None:
        result = _TestQuery._build_element_based_queries({})
        assert result == []

    def test_partial_elements(self) -> None:
        elements = {"cause_of_action": "买卖合同纠纷"}
        result = _TestQuery._build_element_based_queries(elements)
        assert isinstance(result, list)


class TestBuildFieldQueriesFromElements:

    def test_full_elements(self) -> None:
        elements = {
            "cause_of_action": "买卖合同纠纷",
            "dispute_focus": ["逾期交货"],
            "damage_type": ["价差损失"],
            "key_facts": ["未交货"],
        }
        result = _TestQuery._build_field_queries_from_elements(elements)
        assert len(result) == 4
        fields = {q["field"] for q in result}
        assert "causeOfAction" in fields
        assert "disputeFocus" in fields
        assert "courtOpinion" in fields
        assert "fullText" in fields

    def test_empty_elements(self) -> None:
        result = _TestQuery._build_field_queries_from_elements({})
        assert result == []

    def test_partial_elements(self) -> None:
        elements = {"cause_of_action": "合同纠纷", "damage_type": ["损失"]}
        result = _TestQuery._build_field_queries_from_elements(elements)
        assert len(result) == 2


class TestGenerateLlmQueryVariants:

    def test_zero_variants(self) -> None:
        with patch("apps.legal_research.services.executor_components.query_mixin.ServiceLocator") as mock_sl:
            result = _TestQuery._generate_llm_query_variants(
                keyword="违约", case_summary="纠纷", model=None, max_variants=0,
            )
            assert result == []

    def test_short_context_returns_empty(self) -> None:
        result = _TestQuery._generate_llm_query_variants(
            keyword="ab", case_summary="c", model=None, max_variants=2,
        )
        assert result == []

    def test_llm_failure_returns_empty(self) -> None:
        with patch("apps.legal_research.services.executor_components.query_mixin.ServiceLocator") as mock_sl:
            # The source catches (TypeError, ValueError) specifically
            mock_sl.get_llm_service.side_effect = TypeError("LLM unavailable")
            result = _TestQuery._generate_llm_query_variants(
                keyword="买卖合同 违约", case_summary="纠纷描述较长", model=None, max_variants=2,
            )
            assert result == []

    def test_llm_success(self) -> None:
        with patch("apps.legal_research.services.executor_components.query_mixin.ServiceLocator") as mock_sl:
            mock_llm = MagicMock()
            mock_sl.get_llm_service.return_value = mock_llm
            response = MagicMock()
            response.content = json.dumps({"queries": ["买卖合同违约", "货物买卖纠纷"]})
            mock_llm.chat.return_value = response
            result = _TestQuery._generate_llm_query_variants(
                keyword="买卖合同 违约", case_summary="原告与被告签订买卖合同，被告逾期交货",
                model="qwen", max_variants=2,
            )
            assert len(result) >= 1


class TestExtractLegalElements:

    def test_short_summary_returns_empty(self) -> None:
        result = _TestQuery._extract_legal_elements(
            case_summary="短文本", model=None,
        )
        assert result == {}

    def test_llm_failure_returns_empty(self) -> None:
        with patch("apps.legal_research.services.executor_components.query_mixin.ServiceLocator") as mock_sl:
            mock_sl.get_llm_service.side_effect = RuntimeError("fail")
            result = _TestQuery._extract_legal_elements(
                case_summary="原告与被告签订买卖合同，被告逾期交货导致损失",
                model=None,
            )
            assert result == {}

    def test_llm_success(self) -> None:
        with patch("apps.legal_research.services.executor_components.query_mixin.ServiceLocator") as mock_sl:
            mock_llm = MagicMock()
            mock_sl.get_llm_service.return_value = mock_llm
            response = MagicMock()
            response.content = json.dumps({
                "cause_of_action": "买卖合同纠纷",
                "legal_relation": "买卖合同",
                "dispute_focus": ["逾期交货"],
                "damage_type": ["价差损失"],
                "key_facts": ["未按时交货"],
            })
            mock_llm.chat.return_value = response
            result = _TestQuery._extract_legal_elements(
                case_summary="原告与被告签订买卖合同，被告逾期交货导致价差损失，原告要求赔偿",
                model=None,
            )
            assert "cause_of_action" in result


class TestSanitizeElements:

    def test_removes_placeholder_text(self) -> None:
        elements = {
            "cause_of_action": "案由（如：买卖合同纠纷）",
            "legal_relation": "劳动合同",
            "dispute_focus": ["争议焦点1", "未缴社保"],
        }
        result = _TestQuery._sanitize_elements(elements)
        assert result["cause_of_action"] == ""
        assert result["legal_relation"] == "劳动合同"
        assert "未缴社保" in result["dispute_focus"]

    def test_removes_generic_labels(self) -> None:
        elements = {"cause_of_action": "案由", "dispute_focus": ["争议焦点"]}
        result = _TestQuery._sanitize_elements(elements)
        assert result["cause_of_action"] == ""

    def test_keeps_valid_content(self) -> None:
        elements = {"cause_of_action": "买卖合同纠纷", "damage_type": ["价差损失"]}
        result = _TestQuery._sanitize_elements(elements)
        assert result["cause_of_action"] == "买卖合同纠纷"
        assert result["damage_type"] == ["价差损失"]


class TestDedupeTokens:

    def test_basic_dedup(self) -> None:
        result = _TestQuery._dedupe_tokens(["a", "b", "a", "c"], max_tokens=10)
        assert result == ["a", "b", "c"]

    def test_max_tokens(self) -> None:
        result = _TestQuery._dedupe_tokens(["a", "b", "c", "d"], max_tokens=2)
        assert len(result) == 2

    def test_case_insensitive_dedup(self) -> None:
        result = _TestQuery._dedupe_tokens(["Hello", "hello", "HELLO"], max_tokens=10)
        assert len(result) == 1

    def test_empty_tokens(self) -> None:
        result = _TestQuery._dedupe_tokens([], max_tokens=10)
        assert result == []

    def test_whitespace_stripped(self) -> None:
        result = _TestQuery._dedupe_tokens(["  a  ", " b "], max_tokens=10)
        assert result[0] == "a"
        assert result[1] == "b"
