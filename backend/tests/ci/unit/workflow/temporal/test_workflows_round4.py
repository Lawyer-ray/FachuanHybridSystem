"""Tests for workflow/temporal/workflows.py — Round 4: deeper branch coverage.

Covers: _eval_condition with nested dotted paths, _build_step_args default/http edge cases,
_build_mcp_kwargs with non-string config keys, INTERNAL_ACTIVITY_MAP full key set,
MCP_TOOL_MAP full key set, _resolve_dotted with list values,
GateResult signal/query behavior, SimpleWorkflowInput,
_build_step_args llm with empty config.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from apps.workflow.temporal.workflows import (
    INTERNAL_ACTIVITY_MAP,
    MCP_TOOL_MAP,
    GateResult,
    SimpleWorkflowInput,
    _build_mcp_kwargs,
    _build_step_args,
    _eval_condition,
    _resolve_dotted,
)
from apps.workflow.temporal.activities import _HAS_COURT_FILING


# ---------------------------------------------------------------------------
# _resolve_dotted — list at intermediate path
# ---------------------------------------------------------------------------


class TestResolveDottedListsAndEdge:
    def test_list_value_returned(self):
        ctx = {"items": [10, 20, 30]}
        assert _resolve_dotted(ctx, "items") == [10, 20, 30]

    def test_nested_none_then_key(self):
        ctx = {"a": {"b": None}}
        assert _resolve_dotted(ctx, "a.b.c") is None

    def test_integer_root(self):
        assert _resolve_dotted(42, "anything") is None

    def test_bool_value(self):
        ctx = {"flag": True}
        assert _resolve_dotted(ctx, "flag") is True

    def test_empty_string_key(self):
        ctx = {"": "empty_key_val"}
        assert _resolve_dotted(ctx, "") == "empty_key_val"  # empty path splits to [""], looks up key ""

    def test_multilevel_with_mixed_types(self):
        ctx = {"a": {"b": [1, 2], "c": {"d": "found"}}}
        assert _resolve_dotted(ctx, "a.b") == [1, 2]
        assert _resolve_dotted(ctx, "a.c.d") == "found"


# ---------------------------------------------------------------------------
# _eval_condition — nested dotted paths and edge cases
# ---------------------------------------------------------------------------


class TestEvalConditionNested:
    def test_nested_field_path_eq(self):
        step = {"config": {"field": "step_outputs.collect.need_complaint", "operator": "eq", "value": "true"}}
        ctx = {"step_outputs": {"collect": {"need_complaint": "true"}}}
        assert _eval_condition(step, ctx) is True

    def test_nested_field_missing(self):
        step = {"config": {"field": "step_outputs.missing.key", "operator": "exists", "value": ""}}
        ctx = {"step_outputs": {}}
        assert _eval_condition(step, ctx) is False

    def test_contains_with_none_actual(self):
        step = {"config": {"field": "data", "operator": "contains", "value": "x"}}
        ctx = {}
        # actual is None -> str(None) = "None" -> "x" not in "None"
        assert _eval_condition(step, ctx) is False

    def test_lt_with_none_actual(self):
        step = {"config": {"field": "count", "operator": "lt", "value": "5"}}
        ctx = {}
        # float(None or 0) = 0 < 5 = True
        assert _eval_condition(step, ctx) is True

    def test_eq_with_boolean_as_value(self):
        step = {"config": {"field": "flag", "operator": "eq", "value": "True"}}
        ctx = {"flag": True}
        assert _eval_condition(step, ctx) is True

    def test_exists_with_empty_string(self):
        step = {"config": {"field": "name", "operator": "exists", "value": ""}}
        ctx = {"name": ""}
        # empty string is not None, so exists=True
        assert _eval_condition(step, ctx) is True


# ---------------------------------------------------------------------------
# _build_step_args — edge cases
# ---------------------------------------------------------------------------


class TestBuildStepArgsEdgeCases:
    def test_llm_empty_config(self):
        step = {"type": "llm", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == ["", ""]

    def test_llm_system_prompt_with_template(self):
        step = {
            "type": "llm",
            "config": {
                "system_prompt": "Case {{case_id}} role {{role}}",
                "user_prompt_template": "Analyze",
            },
        }
        ctx = {"case_id": 5, "role": "lawyer"}
        args = _build_step_args(step, ctx, case_id=5, run_id=1)
        assert "5" in args[0]
        assert "lawyer" in args[0]
        assert args[1] == "Analyze"

    def test_delay_negative(self):
        step = {"type": "delay", "config": {"duration_minutes": -1}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == [-1.0]

    def test_http_empty_body(self):
        step = {
            "type": "http",
            "config": {"method": "DELETE", "url": "https://x.com/api"},
        }
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args[0] == "DELETE"
        assert args[1] == "https://x.com/api"
        assert args[2] == ""
        assert args[3] == ""

    def test_code_empty_config(self):
        step = {"type": "code", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args[0] == ""

    def test_activity_with_custom_config(self):
        step = {"type": "activity", "config": {"extra": "data"}}
        args = _build_step_args(step, {}, case_id=99, run_id=1)
        assert args == [99]


# ---------------------------------------------------------------------------
# _build_mcp_kwargs — more edge cases
# ---------------------------------------------------------------------------


class TestBuildMcpKwargsEdgeCases:
    def test_non_string_non_numeric_value(self):
        step = {"config": {"list_val": [1, 2, 3]}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
        # list is not str/int/float/bool, so it's skipped
        assert "list_val" not in kwargs
        assert kwargs["case_id"] == 1

    def test_dict_value_skipped(self):
        step = {"config": {"nested": {"key": "val"}}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
        assert "nested" not in kwargs

    def test_template_with_multiple_vars(self):
        step = {"config": {"info": "{{case_id}} - {{case_name}}"}}
        ctx = {"case_id": 42, "case_name": "Test Case"}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=42, run_id=1)
        assert "42" in kwargs["info"]
        assert "Test Case" in kwargs["info"]

    def test_previous_step_with_none_result(self):
        step = {"config": {"data": "{{previous_step.result}}"}}
        ctx = {"_last_output": {"result": None}}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
        # _resolve_dotted returns None, which becomes ""
        assert kwargs["data"] == ""


# ---------------------------------------------------------------------------
# INTERNAL_ACTIVITY_MAP completeness
# ---------------------------------------------------------------------------


class TestInternalActivityMapFull:
    def test_all_expected_keys(self):
        expected = {
            "collect_case_facts",
            "list_case_materials",
            "analyze_single_evidence",
            "summarize_evidence",
            "suggest_arrangement",
            "apply_arrangement",
            "build_litigation_context",
            "generate_complaint_simple",
            "generate_complaint",
            "review_complaint_quality",
            "download_litigation_document",
        }
        if _HAS_COURT_FILING:
            expected.add("execute_court_filing")
        assert set(INTERNAL_ACTIVITY_MAP.keys()) == expected

    def test_values_are_callable(self):
        for key, val in INTERNAL_ACTIVITY_MAP.items():
            assert callable(val), f"{key} value is not callable"


# ---------------------------------------------------------------------------
# MCP_TOOL_MAP completeness
# ---------------------------------------------------------------------------


class TestMcpToolMapFull:
    def test_all_expected_keys(self):
        expected = {
            "collect_case_facts",
            "list_case_materials",
            "create_case_log",
            "generate_complaint",
            "generate_defense",
            "download_litigation_document",
            "download_authorization_package",
            "download_preservation_docs",
            "execute_guarantee",
            "submit_court_sms",
            "search_companies",
            "get_company_profile",
            "get_company_risks",
            "create_research_task",
            "check_law_references",
            "create_reminder",
            "auto_namer",
            "process_document",
            "convert_document",
            "calculate_litigation_fee",
            "calculate_interest",
        }
        if _HAS_COURT_FILING:
            expected.add("execute_court_filing")
        assert set(MCP_TOOL_MAP.keys()) == expected

    def test_values_are_strings(self):
        for key, val in MCP_TOOL_MAP.items():
            assert isinstance(val, str), f"{key} value should be string tool name"


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------


class TestGateResultExtended:
    def test_dict_representation(self):
        g = GateResult(approved=True, comment="looks good")
        d = g.__dict__
        assert d == {"approved": True, "comment": "looks good"}

    def test_defaults_dict(self):
        g = GateResult()
        d = g.__dict__
        assert d == {"approved": False, "comment": ""}


# ---------------------------------------------------------------------------
# SimpleWorkflowInput
# ---------------------------------------------------------------------------


class TestSimpleWorkflowInputExtended:
    def test_attributes(self):
        inp = SimpleWorkflowInput(case_id=100, run_id=200)
        assert inp.case_id == 100
        assert inp.run_id == 200

    def test_equality(self):
        a = SimpleWorkflowInput(case_id=1, run_id=2)
        b = SimpleWorkflowInput(case_id=1, run_id=2)
        assert a == b
