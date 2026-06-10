"""Tests for query_mixin module-level pure functions."""

from __future__ import annotations

import json

from apps.legal_research.services.executor_components.query_mixin import (
    build_element_based_queries,
    build_field_queries_from_elements,
    merge_query_candidates,
    parse_llm_variant_json,
    sanitize_elements,
)


class TestSanitizeElements:
    def test_removes_parenthetical_placeholder(self) -> None:
        result = sanitize_elements({"cause_of_action": "案由（如：买卖合同纠纷）"})
        assert result["cause_of_action"] == ""

    def test_removes_numbered_placeholder(self) -> None:
        result = sanitize_elements({"dispute_focus": ["争议焦点1", "未缴社保"]})
        assert "未缴社保" in result["dispute_focus"]
        assert len(result["dispute_focus"]) == 1

    def test_removes_generic_labels(self) -> None:
        result = sanitize_elements({"cause_of_action": "案由", "legal_relation": "法律关系"})
        assert result["cause_of_action"] == ""
        assert result["legal_relation"] == ""

    def test_keeps_valid_content(self) -> None:
        result = sanitize_elements({"cause_of_action": "买卖合同纠纷", "damage_type": ["价差损失"]})
        assert result["cause_of_action"] == "买卖合同纠纷"
        assert result["damage_type"] == ["价差损失"]

    def test_removes_colon_placeholder(self) -> None:
        result = sanitize_elements({"cause_of_action": "如：劳动争议"})
        assert result["cause_of_action"] == ""

    def test_passes_non_string_values(self) -> None:
        result = sanitize_elements({"count": 42})
        assert result["count"] == 42

    def test_empty_elements(self) -> None:
        result = sanitize_elements({})
        assert result == {}

    def test_cleans_list_values(self) -> None:
        result = sanitize_elements({"items": ["有效内容", "案由", "另一个有效"]})
        assert len(result["items"]) == 2


class TestBuildElementBasedQueries:
    def test_full_elements(self) -> None:
        elements = {
            "cause_of_action": "买卖合同纠纷",
            "legal_relation": "买卖合同",
            "dispute_focus": ["逾期交货", "价差损失"],
            "damage_type": ["价差损失"],
            "key_facts": ["未按时交货"],
        }
        result = build_element_based_queries(elements)
        assert len(result) >= 3
        assert any("买卖合同纠纷" in q for q in result)

    def test_empty_elements(self) -> None:
        assert build_element_based_queries({}) == []

    def test_only_cause(self) -> None:
        result = build_element_based_queries({"cause_of_action": "买卖合同纠纷"})
        assert result == []

    def test_cause_and_disputes(self) -> None:
        result = build_element_based_queries({
            "cause_of_action": "买卖合同纠纷",
            "dispute_focus": ["逾期交货"],
        })
        assert len(result) >= 1
        assert any("买卖合同纠纷" in q for q in result)

    def test_relation_and_damages(self) -> None:
        result = build_element_based_queries({
            "legal_relation": "买卖合同",
            "damage_type": ["价差损失"],
        })
        assert len(result) >= 1


class TestBuildFieldQueriesFromElements:
    def test_full_elements(self) -> None:
        elements = {
            "cause_of_action": "买卖合同纠纷",
            "dispute_focus": ["逾期交货"],
            "damage_type": ["价差损失"],
            "key_facts": ["未交货"],
        }
        result = build_field_queries_from_elements(elements)
        assert len(result) == 4
        fields = {q["field"] for q in result}
        assert fields == {"causeOfAction", "disputeFocus", "courtOpinion", "fullText"}

    def test_empty_elements(self) -> None:
        assert build_field_queries_from_elements({}) == []

    def test_partial_elements(self) -> None:
        result = build_field_queries_from_elements({"cause_of_action": "合同纠纷"})
        assert len(result) == 1
        assert result[0]["field"] == "causeOfAction"

    def test_all_op_and(self) -> None:
        result = build_field_queries_from_elements({
            "cause_of_action": "纠纷",
            "dispute_focus": ["焦点"],
        })
        for q in result:
            assert q["op"] == "AND"


class TestMergeQueryCandidates:
    def test_deduplicates(self) -> None:
        result = merge_query_candidates(["query a", "query b"], ["query b", "query c"])
        assert len(result) == 3

    def test_max_queries(self) -> None:
        result = merge_query_candidates(["q1", "q2", "q3"], ["q4", "q5"], max_queries=2)
        assert len(result) == 2

    def test_strips_whitespace(self) -> None:
        result = merge_query_candidates(["  a  "], [])
        assert result[0] == "a"

    def test_empty_filtered(self) -> None:
        result = merge_query_candidates(["", "  ", "valid"], [])
        assert result == ["valid"]

    def test_normalizes_multi_space(self) -> None:
        result = merge_query_candidates(["a  b  c"], [])
        assert result[0] == "a b c"


class TestParseLlmVariantJson:
    def test_valid_json(self) -> None:
        content = json.dumps({"queries": ["买卖合同 违约", "货物买卖纠纷"]})
        result = parse_llm_variant_json(content)
        assert len(result) == 2

    def test_empty_content(self) -> None:
        assert parse_llm_variant_json("") == []

    def test_json_in_code_block(self) -> None:
        content = '```json\n{"queries": ["违约 损失"]}\n```'
        result = parse_llm_variant_json(content)
        assert len(result) >= 1

    def test_string_value(self) -> None:
        content = json.dumps({"queries": "single query"})
        result = parse_llm_variant_json(content)
        assert len(result) == 1

    def test_non_json_fallback(self) -> None:
        content = "买卖合同 违约\n价差损失 赔偿"
        result = parse_llm_variant_json(content)
        assert len(result) >= 1

    def test_strips_numbered_prefixes(self) -> None:
        content = "1. 买卖合同 违约\n2. 价差损失"
        result = parse_llm_variant_json(content)
        assert all("1." not in q and "2." not in q for q in result)
