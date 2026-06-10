"""Batch7 coverage tests for apps.story_viz."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.story_viz.schemas.extracted_facts import (
    ExtractedFacts,
    FactEvent,
    FactParty,
    FactRelationship,
)
from apps.story_viz.schemas.animation_script import (
    AnimationScript,
    ComparisonItem,
    GraphEdge,
    GraphNode,
    MotionPlan,
)


# ── FactParty ───────────────────────────────────────────────────────────────


class TestFactParty:
    def test_defaults(self) -> None:
        party = FactParty()
        assert party.name == ""
        assert party.role == ""
        assert party.aliases == []

    def test_with_values(self) -> None:
        party = FactParty(name="张三", role="原告", aliases=["张某"])
        assert party.name == "张三"
        assert party.role == "原告"
        assert party.aliases == ["张某"]


# ── FactEvent ───────────────────────────────────────────────────────────────


class TestFactEvent:
    def test_defaults(self) -> None:
        event = FactEvent()
        assert event.sequence == 0
        assert event.time_label == ""
        assert event.summary == ""
        assert event.participants == []
        assert event.amounts == []

    def test_with_values(self) -> None:
        event = FactEvent(
            sequence=1,
            time_label="2024年1月",
            summary="签订合同",
            participants=["张三", "李四"],
            amounts=["10000元"],
        )
        assert event.sequence == 1
        assert len(event.participants) == 2


# ── FactRelationship ────────────────────────────────────────────────────────


class TestFactRelationship:
    def test_defaults(self) -> None:
        rel = FactRelationship()
        assert rel.source == ""
        assert rel.target == ""
        assert rel.relation_type == ""

    def test_with_values(self) -> None:
        rel = FactRelationship(source="张三", target="李四", relation_type="借款")
        assert rel.source == "张三"


# ── ExtractedFacts ──────────────────────────────────────────────────────────


class TestExtractedFacts:
    def test_defaults(self) -> None:
        facts = ExtractedFacts()
        assert facts.case_title == ""
        assert facts.parties == []
        assert facts.events == []
        assert facts.relationships == []
        assert facts.judgment_result == ""
        assert facts.confidence_notes == ""

    def test_with_data(self) -> None:
        facts = ExtractedFacts(
            case_title="借款纠纷",
            parties=[FactParty(name="张三", role="原告")],
            events=[FactEvent(sequence=1, summary="签合同")],
            relationships=[FactRelationship(source="张三", target="李四", relation_type="借款")],
            judgment_result="胜诉",
        )
        assert facts.case_title == "借款纠纷"
        assert len(facts.parties) == 1
        assert len(facts.events) == 1
        assert len(facts.relationships) == 1


# ── Animation script schemas ────────────────────────────────────────────────


class TestAnimationScript:
    def test_defaults(self) -> None:
        script = AnimationScript()
        assert script.title == ""
        assert script.viz_type == "timeline"
        assert script.theme == "glass-dark"
        assert script.highlights == []
        assert script.annotations == []

    def test_graph_node_defaults(self) -> None:
        node = GraphNode()
        assert node.id == ""
        assert node.label == ""
        assert node.category == "person"

    def test_graph_edge_defaults(self) -> None:
        edge = GraphEdge()
        assert edge.source == ""
        assert edge.target == ""
        assert edge.relation == ""

    def test_motion_plan_defaults(self) -> None:
        plan = MotionPlan()
        assert plan.duration_ms == 1200
        assert plan.easing == "ease-in-out"

    def test_comparison_item_defaults(self) -> None:
        item = ComparisonItem()
        assert item.claim == ""
        assert item.judgment == ""
        assert item.supported is False
