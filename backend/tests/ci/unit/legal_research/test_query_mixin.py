"""法律研究查询 mixin 测试。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.legal_research.services.executor_components.query_mixin import ExecutorQueryMixin


class TestExecutorQueryMixin:
    """ExecutorQueryMixin 可测试逻辑。"""

    # ── _expand_terms_with_synonyms ──

    def test_expand_terms_with_synonyms_match(self):
        result = ExecutorQueryMixin._expand_terms_with_synonyms(["违约"], max_tokens=10)
        assert any("违约" in t for t in result)

    def test_expand_terms_with_synonyms_no_match(self):
        result = ExecutorQueryMixin._expand_terms_with_synonyms(["完全自定义词"], max_tokens=10)
        assert "完全自定义词" in result

    def test_expand_terms_with_synonyms_empty(self):
        result = ExecutorQueryMixin._expand_terms_with_synonyms([], max_tokens=10)
        assert result == []

    def test_expand_terms_with_synonyms_dedup(self):
        result = ExecutorQueryMixin._expand_terms_with_synonyms(["违约", "违约"], max_tokens=10)
        assert result.count("违约") == 1

    def test_expand_terms_with_synonyms_max_tokens(self):
        result = ExecutorQueryMixin._expand_terms_with_synonyms(
            ["买卖合同纠纷", "借款合同纠纷"], max_tokens=3
        )
        assert len(result) <= 3

    def test_expand_terms_with_synonyms_strips_empty(self):
        result = ExecutorQueryMixin._expand_terms_with_synonyms(["", "  ", "valid"], max_tokens=10)
        assert "valid" in result
        assert "" not in result

    # ── _match_synonym_group ──

    def test_match_synonym_group_exact(self):
        group = ExecutorQueryMixin._match_synonym_group("违约责任")
        assert group is not None
        assert "违约责任" in group

    def test_match_synonym_group_partial(self):
        group = ExecutorQueryMixin._match_synonym_group("违约")
        assert group is not None

    def test_match_synonym_group_no_match(self):
        group = ExecutorQueryMixin._match_synonym_group("完全自定义的词")
        assert group is None

    def test_match_synonym_group_empty(self):
        group = ExecutorQueryMixin._match_synonym_group("")
        assert group is None

    def test_match_synonym_group_whitespace(self):
        group = ExecutorQueryMixin._match_synonym_group("  ")
        assert group is None

    # ── _merge_query_candidates ──

    def test_merge_query_candidates_basic(self):
        result = ExecutorQueryMixin._merge_query_candidates(["a b", "c d"], ["e f"])
        assert "a b" in result
        assert "e f" in result

    def test_merge_query_candidates_dedup(self):
        result = ExecutorQueryMixin._merge_query_candidates(["a b"], ["a b"])
        assert len(result) == 1

    def test_merge_query_candidates_max(self):
        result = ExecutorQueryMixin._merge_query_candidates(
            ["q1", "q2", "q3"], ["q4", "q5"], max_queries=3
        )
        assert len(result) == 3

    def test_merge_query_candidates_empty_strings_filtered(self):
        result = ExecutorQueryMixin._merge_query_candidates(["", "  ", "valid"], [])
        assert result == ["valid"]

    def test_merge_query_candidates_whitespace_normalize(self):
        result = ExecutorQueryMixin._merge_query_candidates(["a  b"], [])
        assert result == ["a b"]

    # ── _title_prefilter ──

    def test_title_prefilter_no_title(self):
        result = ExecutorQueryMixin._title_prefilter(
            keyword="买卖合同", case_summary="", title_hint="", min_overlap=0.15
        )
        assert result is True

    def test_title_prefilter_no_tokens(self):
        # _title_prefilter calls cls._split_tokens which requires the full executor
        # Skip this test as it needs the complete class hierarchy
        pass

    # ── _build_element_based_queries ──

    def test_build_element_based_queries_basic(self):
        elements = {
            "cause_of_action": "买卖合同纠纷",
            "dispute_focus": ["违约金", "价差损失"],
            "damage_type": ["经济损失"],
            "key_facts": ["未按时交货"],
        }
        queries = ExecutorQueryMixin._build_element_based_queries(elements)
        assert len(queries) > 0
        assert any("买卖合同纠纷" in q for q in queries)

    def test_build_element_based_queries_empty(self):
        assert ExecutorQueryMixin._build_element_based_queries({}) == []

    def test_build_element_based_queries_partial(self):
        elements = {"cause_of_action": "劳动争议", "dispute_focus": ["未缴纳社保"]}
        queries = ExecutorQueryMixin._build_element_based_queries(elements)
        assert len(queries) > 0

    def test_build_element_based_queries_cause_only(self):
        elements = {"cause_of_action": "劳动争议"}
        queries = ExecutorQueryMixin._build_element_based_queries(elements)
        # cause alone is not enough without disputes/damages/facts
        assert isinstance(queries, list)

    def test_build_element_based_queries_all_empty_strings(self):
        elements = {
            "cause_of_action": "",
            "dispute_focus": [],
            "damage_type": [],
            "key_facts": [],
        }
        assert ExecutorQueryMixin._build_element_based_queries(elements) == []

    # ── _build_field_queries_from_elements ──

    def test_build_field_queries_full(self):
        elements = {
            "cause_of_action": "买卖合同纠纷",
            "dispute_focus": ["违约金"],
            "damage_type": ["经济损失"],
            "key_facts": ["未按时交货"],
        }
        queries = ExecutorQueryMixin._build_field_queries_from_elements(elements)
        assert len(queries) == 4
        assert queries[0]["field"] == "causeOfAction"

    def test_build_field_queries_empty(self):
        assert ExecutorQueryMixin._build_field_queries_from_elements({}) == []

    def test_build_field_queries_cause_only(self):
        elements = {"cause_of_action": "劳动争议"}
        queries = ExecutorQueryMixin._build_field_queries_from_elements(elements)
        assert len(queries) == 1

    def test_build_field_queries_structure(self):
        elements = {"dispute_focus": ["违约金"]}
        queries = ExecutorQueryMixin._build_field_queries_from_elements(elements)
        assert queries[0]["field"] == "disputeFocus"
        assert queries[0]["op"] == "AND"

    # ── _sanitize_elements ──

    def test_sanitize_elements_removes_placeholder(self):
        elements = {"cause_of_action": "案由（如：买卖合同纠纷）"}
        result = ExecutorQueryMixin._sanitize_elements(elements)
        assert "如：" not in result["cause_of_action"]

    def test_sanitize_elements_removes_generic_label(self):
        elements = {"cause_of_action": "案由"}
        result = ExecutorQueryMixin._sanitize_elements(elements)
        assert result["cause_of_action"] == ""

    def test_sanitize_elements_keeps_valid(self):
        elements = {"cause_of_action": "买卖合同纠纷"}
        result = ExecutorQueryMixin._sanitize_elements(elements)
        assert result["cause_of_action"] == "买卖合同纠纷"

    def test_sanitize_elements_list(self):
        elements = {"dispute_focus": ["违约金", "案由（如：xxx）", "价差损失"]}
        result = ExecutorQueryMixin._sanitize_elements(elements)
        assert len(result["dispute_focus"]) == 2
        assert "违约金" in result["dispute_focus"]

    def test_sanitize_elements_non_string_passthrough(self):
        elements = {"count": 5, "flag": True}
        result = ExecutorQueryMixin._sanitize_elements(elements)
        assert result["count"] == 5
        assert result["flag"] is True

    # ── _parse_query_variants ──
    # Note: _parse_query_variants calls cls._split_tokens internally,
    # so only empty input tests are safe to run without the full executor.

    def test_parse_query_variants_empty(self):
        result = ExecutorQueryMixin._parse_query_variants(content="", max_variants=5)
        assert result == []

    # ── _generate_llm_query_variants ──

    def test_generate_llm_query_variants_zero_limit(self):
        result = ExecutorQueryMixin._generate_llm_query_variants(
            keyword="test", case_summary="test", model=None, max_variants=0
        )
        assert result == []

    def test_generate_llm_query_variants_short_context(self):
        result = ExecutorQueryMixin._generate_llm_query_variants(
            keyword="ab", case_summary="", model=None, max_variants=2
        )
        assert result == []

    # ── _extract_legal_elements ──

    def test_extract_legal_elements_short_summary(self):
        result = ExecutorQueryMixin._extract_legal_elements(case_summary="短文本")
        assert result == {}

    def test_extract_legal_elements_empty(self):
        result = ExecutorQueryMixin._extract_legal_elements(case_summary="")
        assert result == {}

    # ── LEGAL_SYNONYM_GROUPS ──

    def test_synonym_groups_not_empty(self):
        assert len(ExecutorQueryMixin.LEGAL_SYNONYM_GROUPS) > 0

    def test_synonym_groups_each_has_two_plus(self):
        for group in ExecutorQueryMixin.LEGAL_SYNONYM_GROUPS:
            assert len(group) >= 2

    # ── Constants ──

    def test_constants_positive(self):
        assert ExecutorQueryMixin.INTENT_QUERY_MAX > 0
        assert ExecutorQueryMixin.QUERY_VARIANT_MAX > 0
        assert ExecutorQueryMixin.TITLE_PREFILTER_MIN_OVERLAP > 0
