"""Tests for workflow/api/step_registry.py (75% coverage).

Covers: get_step_registry, get_flat_step_list, find_step — all branches.
"""
from __future__ import annotations

from apps.workflow.api.step_registry import (
    STEP_CATEGORIES,
    find_step,
    get_flat_step_list,
    get_step_registry,
)


class TestGetStepRegistry:
    def test_returns_step_categories(self):
        result = get_step_registry()
        assert result is STEP_CATEGORIES

    def test_has_expected_category_ids(self):
        ids = {cat["id"] for cat in STEP_CATEGORIES}
        assert "flow" in ids
        assert "cases" in ids
        assert "evidence" in ids
        assert "documents" in ids
        assert "litigation" in ids

    def test_each_category_has_steps(self):
        for cat in STEP_CATEGORIES:
            assert "steps" in cat
            assert len(cat["steps"]) > 0

    def test_each_step_has_required_fields(self):
        for cat in STEP_CATEGORIES:
            for step in cat["steps"]:
                assert "id" in step
                assert "name" in step
                assert "type" in step
                assert "description" in step


class TestGetFlatStepList:
    def test_flat_list_contains_all_steps(self):
        flat = get_flat_step_list()
        total = sum(len(cat["steps"]) for cat in STEP_CATEGORIES)
        assert len(flat) == total

    def test_each_flat_step_has_category_info(self):
        flat = get_flat_step_list()
        for step in flat:
            assert "category_id" in step
            assert "category_name" in step

    def test_flat_step_ids_unique(self):
        flat = get_flat_step_list()
        ids = [s["id"] for s in flat]
        assert len(ids) == len(set(ids))


class TestFindStep:
    def test_find_existing_step(self):
        step = find_step("gate")
        assert step is not None
        assert step["id"] == "gate"
        assert step["category_id"] == "flow"

    def test_find_nonexistent_step(self):
        step = find_step("nonexistent_step_xyz")
        assert step is None

    def test_find_step_in_non_first_category(self):
        step = find_step("generate_complaint")
        assert step is not None
        assert step["category_id"] == "documents"

    def test_find_step_with_mcp_tool(self):
        step = find_step("execute_court_filing")
        assert step is not None
        assert step.get("mcp_tool") == "execute_court_filing"
