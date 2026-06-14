"""
Extended unit tests for core/config/steering/dependency_manager.py

Covers:
  - DependencyType / LoadOrderStrategy enums
  - DependencyInfo / SpecificationMetadata / DependencyConflict / LoadOrderResult dataclasses
  - DependencyGraph: add_specification, get_dependencies, get_dependents,
    detect_circular_dependencies, topological_sort, validate_dependencies,
    get_dependency_levels
  - SteeringDependencyManager: __init__, resolve_load_order, _sort_by_priority,
    _resolve_missing_dependencies, get_dependency_info, export_dependency_graph,
    get_statistics, refresh_metadata, _normalize_dependency_list
  - create_dependency_manager_from_config
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.config.steering.dependency_manager import (
    DependencyConflict,
    DependencyGraph,
    DependencyInfo,
    DependencyType,
    LoadOrderResult,
    LoadOrderStrategy,
    SpecificationMetadata,
    SteeringDependencyManager,
    create_dependency_manager_from_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meta(
    path: str,
    *,
    inherits: list[str] | None = None,
    requires: list[str] | None = None,
    optional_deps: list[str] | None = None,
    conflicts: list[str] | None = None,
    priority: int = 0,
    **kwargs: Any,
) -> SpecificationMetadata:
    return SpecificationMetadata(
        path=path,
        name=kwargs.get("name", path),
        version=kwargs.get("version", "1.0.0"),
        priority=priority,
        inherits=inherits or [],
        requires=requires or [],
        optional_deps=optional_deps or [],
        conflicts=conflicts or [],
    )


# ===========================================================================
# Enums
# ===========================================================================


class TestEnums:
    def test_dependency_type_values(self) -> None:
        assert DependencyType.INHERITS.value == "inherits"
        assert DependencyType.REQUIRES.value == "requires"
        assert DependencyType.OPTIONAL.value == "optional"
        assert DependencyType.CONFLICTS.value == "conflicts"

    def test_load_order_strategy_values(self) -> None:
        assert LoadOrderStrategy.PRIORITY.value == "priority"
        assert LoadOrderStrategy.DEPENDENCY.value == "dependency"
        assert LoadOrderStrategy.ALPHABETICAL.value == "alphabetical"
        assert LoadOrderStrategy.TOPOLOGICAL.value == "topological"
        assert LoadOrderStrategy.CUSTOM.value == "custom"


# ===========================================================================
# Dataclasses
# ===========================================================================


class TestDataclasses:
    def test_dependency_info(self) -> None:
        info = DependencyInfo(
            source_spec="a.md",
            target_spec="b.md",
            dependency_type=DependencyType.REQUIRES,
        )
        assert info.source_spec == "a.md"
        assert info.version_constraint is None
        assert info.condition is None
        assert info.metadata == {}

    def test_specification_metadata_defaults(self) -> None:
        meta = SpecificationMetadata(path="x.md", name="x")
        assert meta.version == "1.0.0"
        assert meta.priority == 0
        assert meta.tags == []
        assert meta.inclusion == "manual"

    def test_dependency_conflict(self) -> None:
        c = DependencyConflict(
            conflict_type="circular",
            description="cycle",
            affected_specs=["a", "b"],
        )
        assert c.suggested_resolution is None

    def test_load_order_result_defaults(self) -> None:
        r = LoadOrderResult(
            ordered_specs=["a"],
            dependency_levels={"a": 0},
            warnings=[],
        )
        assert r.metadata == {}
        assert r.conflicts == []


# ===========================================================================
# DependencyGraph
# ===========================================================================


class TestDependencyGraph:
    def test_add_and_get_dependencies(self) -> None:
        g = DependencyGraph()
        meta = _make_meta("a.md", requires=["b.md"])
        g.add_specification(meta)
        deps = g.get_dependencies("a.md")
        assert len(deps) == 1
        assert deps[0].target_spec == "b.md"

    def test_get_dependencies_filter_by_type(self) -> None:
        g = DependencyGraph()
        meta = _make_meta("a.md", requires=["b.md"], optional_deps=["c.md"])
        g.add_specification(meta)
        req = g.get_dependencies("a.md", [DependencyType.REQUIRES])
        assert len(req) == 1
        opt = g.get_dependencies("a.md", [DependencyType.OPTIONAL])
        assert len(opt) == 1

    def test_get_dependencies_unknown_spec(self) -> None:
        g = DependencyGraph()
        assert g.get_dependencies("unknown") == []

    def test_get_dependents(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", requires=["b.md"]))
        g.add_specification(_make_meta("b.md"))
        dependents = g.get_dependents("b.md")
        assert len(dependents) == 1
        assert dependents[0].source_spec == "a.md"

    def test_get_dependents_unknown_spec(self) -> None:
        g = DependencyGraph()
        assert g.get_dependents("unknown") == []

    def test_detect_circular_dependencies_no_cycle(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", requires=["b.md"]))
        g.add_specification(_make_meta("b.md"))
        cycles = g.detect_circular_dependencies()
        assert cycles == []

    def test_detect_circular_dependencies_with_cycle(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", requires=["b.md"]))
        g.add_specification(_make_meta("b.md", requires=["a.md"]))
        cycles = g.detect_circular_dependencies()
        assert len(cycles) >= 1
        # Each cycle should contain both a.md and b.md
        cycle = cycles[0]
        assert "a.md" in cycle
        assert "b.md" in cycle

    def test_topological_sort_no_deps(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md"))
        g.add_specification(_make_meta("b.md"))
        result, conflicts = g.topological_sort(["a.md", "b.md"])
        assert set(result) == {"a.md", "b.md"}
        assert conflicts == []

    def test_topological_sort_with_deps(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", requires=["b.md"]))
        g.add_specification(_make_meta("b.md"))
        result, conflicts = g.topological_sort(["a.md", "b.md"])
        assert result.index("b.md") < result.index("a.md")
        assert conflicts == []

    def test_topological_sort_circular(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", requires=["b.md"]))
        g.add_specification(_make_meta("b.md", requires=["a.md"]))
        result, conflicts = g.topological_sort(["a.md", "b.md"])
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "circular"

    def test_validate_dependencies_missing(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", requires=["b.md"]))
        conflicts = g.validate_dependencies(["a.md"])
        assert len(conflicts) == 1
        assert "不存在" in conflicts[0].description

    def test_validate_dependencies_not_in_load_list(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", requires=["b.md"]))
        g.add_specification(_make_meta("b.md"))
        conflicts = g.validate_dependencies(["a.md"])
        assert len(conflicts) == 1
        assert "未包含" in conflicts[0].description

    def test_validate_dependencies_conflict(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", conflicts=["b.md"]))
        g.add_specification(_make_meta("b.md"))
        conflicts = g.validate_dependencies(["a.md", "b.md"])
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "conflict"

    def test_validate_dependencies_unknown_spec(self) -> None:
        g = DependencyGraph()
        # Unknown spec is silently skipped
        conflicts = g.validate_dependencies(["unknown.md"])
        assert conflicts == []

    def test_get_dependency_levels(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", requires=["b.md"]))
        g.add_specification(_make_meta("b.md"))
        levels = g.get_dependency_levels(["a.md", "b.md"])
        assert levels["b.md"] == 0
        assert levels["a.md"] == 1

    def test_get_dependency_levels_circular(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", requires=["b.md"]))
        g.add_specification(_make_meta("b.md", requires=["a.md"]))
        levels = g.get_dependency_levels(["a.md", "b.md"])
        # Should not infinite loop, returns 0 for circular
        assert "a.md" in levels
        assert "b.md" in levels

    def test_inherits_dependency(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("child.md", inherits=["parent.md"]))
        deps = g.get_dependencies("child.md", [DependencyType.INHERITS])
        assert len(deps) == 1
        assert deps[0].target_spec == "parent.md"

    def test_conflicts_only_in_forward_edges(self) -> None:
        g = DependencyGraph()
        g.add_specification(_make_meta("a.md", conflicts=["b.md"]))
        # Conflicts should NOT appear in reverse_edges
        reverse = g.get_dependents("b.md")
        assert len(reverse) == 0


# ===========================================================================
# SteeringDependencyManager
# ===========================================================================


class TestSteeringDependencyManager:
    def _make_manager(self, config: dict[str, Any] | None = None, steering_root: str = "/nonexistent") -> SteeringDependencyManager:
        return SteeringDependencyManager(config or {}, steering_root=steering_root)

    def test_init_nonexistent_root(self) -> None:
        m = self._make_manager()
        assert m.auto_resolve is True
        assert m.max_depth == 10
        assert m.circular_detection is True
        assert m.load_order_strategy == LoadOrderStrategy.DEPENDENCY

    def test_normalize_dependency_list_string(self) -> None:
        m = self._make_manager()
        assert m._normalize_dependency_list("dep.md") == ["dep.md"]

    def test_normalize_dependency_list_list(self) -> None:
        m = self._make_manager()
        assert m._normalize_dependency_list(["a.md", "b.md"]) == ["a.md", "b.md"]

    def test_normalize_dependency_list_other(self) -> None:
        m = self._make_manager()
        assert m._normalize_dependency_list(123) == []

    def test_resolve_load_order_dependency_strategy(self) -> None:
        m = self._make_manager({"load_order_strategy": "dependency"})
        meta_a = _make_meta("a.md", requires=["b.md"])
        meta_b = _make_meta("b.md")
        m._metadata_cache = {"a.md": meta_a, "b.md": meta_b}
        m.dependency_graph.add_specification(meta_a)
        m.dependency_graph.add_specification(meta_b)
        result = m.resolve_load_order(["a.md", "b.md"])
        assert isinstance(result, LoadOrderResult)
        assert result.metadata["strategy"] == "dependency"

    def test_resolve_load_order_priority_strategy(self) -> None:
        m = self._make_manager({"load_order_strategy": "priority"})
        meta_a = _make_meta("a.md", priority=10)
        meta_b = _make_meta("b.md", priority=1)
        m._metadata_cache = {"a.md": meta_a, "b.md": meta_b}
        m.dependency_graph.add_specification(meta_a)
        m.dependency_graph.add_specification(meta_b)
        result = m.resolve_load_order(["a.md", "b.md"])
        assert result.ordered_specs[0] == "a.md"

    def test_resolve_load_order_alphabetical_strategy(self) -> None:
        m = self._make_manager({"load_order_strategy": "alphabetical"})
        meta_a = _make_meta("b.md")
        meta_b = _make_meta("a.md")
        m._metadata_cache = {"b.md": meta_a, "a.md": meta_b}
        m.dependency_graph.add_specification(meta_a)
        m.dependency_graph.add_specification(meta_b)
        result = m.resolve_load_order(["b.md", "a.md"])
        assert result.ordered_specs == ["a.md", "b.md"]

    def test_resolve_load_order_topological_strategy(self) -> None:
        m = self._make_manager({"load_order_strategy": "topological"})
        meta_a = _make_meta("a.md", requires=["b.md"])
        meta_b = _make_meta("b.md")
        m._metadata_cache = {"a.md": meta_a, "b.md": meta_b}
        m.dependency_graph.add_specification(meta_a)
        m.dependency_graph.add_specification(meta_b)
        result = m.resolve_load_order(["a.md", "b.md"])
        assert result.ordered_specs.index("b.md") < result.ordered_specs.index("a.md")

    def test_resolve_load_order_custom_strategy(self) -> None:
        """Custom strategy falls back to dependency (topological) sort."""
        m = self._make_manager({"load_order_strategy": "custom"})
        meta = _make_meta("a.md")
        m._metadata_cache = {"a.md": meta}
        m.dependency_graph.add_specification(meta)
        result = m.resolve_load_order(["a.md"])
        assert "a.md" in result.ordered_specs

    def test_get_dependency_info_existing(self) -> None:
        m = self._make_manager()
        meta = _make_meta("a.md", requires=["b.md"])
        m._metadata_cache = {"a.md": meta}
        m.dependency_graph.add_specification(meta)
        info = m.get_dependency_info("a.md")
        assert info["metadata"]["name"] == "a.md"
        assert len(info["dependencies"]["requires"]) == 1

    def test_get_dependency_info_nonexistent(self) -> None:
        m = self._make_manager()
        info = m.get_dependency_info("missing.md")
        assert "error" in info

    def test_export_dependency_graph_json(self) -> None:
        m = self._make_manager()
        meta = _make_meta("a.md")
        m._metadata_cache = {"a.md": meta}
        m.dependency_graph.add_specification(meta)
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            path = f.name
        m.export_dependency_graph(path, format="json")
        with open(path) as f:
            data = json.load(f)
        assert "a.md" in data["nodes"]

    def test_export_dependency_graph_unsupported_format(self) -> None:
        m = self._make_manager()
        meta = _make_meta("a.md")
        m._metadata_cache = {"a.md": meta}
        m.dependency_graph.add_specification(meta)
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            path = f.name
        # Should log error but not raise
        m.export_dependency_graph(path, format="xml")

    def test_get_statistics(self) -> None:
        m = self._make_manager()
        meta = _make_meta("a.md", requires=["b.md"])
        m._metadata_cache = {"a.md": meta}
        m.dependency_graph.add_specification(meta)
        stats = m.get_statistics()
        assert stats["total_specifications"] == 1
        assert stats["total_dependencies"] == 1
        assert "config" in stats

    def test_get_statistics_empty(self) -> None:
        m = self._make_manager()
        stats = m.get_statistics()
        assert stats["total_specifications"] == 0
        assert stats["average_dependencies_per_spec"] == 0

    def test_refresh_metadata(self) -> None:
        m = self._make_manager()
        meta = _make_meta("a.md")
        m._metadata_cache["a.md"] = meta
        m.refresh_metadata()
        assert len(m._metadata_cache) == 0

    def test_auto_resolve_adds_missing_deps(self) -> None:
        m = self._make_manager({"auto_resolve": True})
        meta_a = _make_meta("a.md", requires=["b.md"])
        meta_b = _make_meta("b.md")
        m._metadata_cache = {"a.md": meta_a, "b.md": meta_b}
        m.dependency_graph.add_specification(meta_a)
        m.dependency_graph.add_specification(meta_b)
        result = m.resolve_load_order(["a.md"])
        assert "b.md" in result.ordered_specs

    def test_sort_by_priority_with_no_metadata(self) -> None:
        m = self._make_manager()
        result = m._sort_by_priority(["a.md", "b.md"])
        # Both have priority 0, sorted by get_priority
        assert set(result) == {"a.md", "b.md"}


# ===========================================================================
# _load_specification_metadata (via file)
# ===========================================================================


class TestLoadSpecificationMetadata:
    def test_load_with_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            steering_dir = Path(tmpdir)
            spec_file = steering_dir / "test.md"
            spec_file.write_text(
                "---\nname: test-spec\nversion: 2.0.0\npriority: 5\ninherits:\n  - base.md\nrequires:\n  - dep.md\ntags:\n  - important\n---\n# Content\n",
                encoding="utf-8",
            )
            m = SteeringDependencyManager({}, steering_root=str(steering_dir))
            meta = m._load_specification_metadata("test.md")
            assert meta is not None
            assert meta.name == "test-spec"
            assert meta.version == "2.0.0"
            assert meta.priority == 5
            assert "base.md" in meta.inherits
            assert "dep.md" in meta.requires
            assert "important" in meta.tags

    def test_load_without_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            steering_dir = Path(tmpdir)
            spec_file = steering_dir / "plain.md"
            spec_file.write_text("# Plain spec\nSome content", encoding="utf-8")
            m = SteeringDependencyManager({}, steering_root=str(steering_dir))
            meta = m._load_specification_metadata("plain.md")
            assert meta is not None
            assert meta.name == "plain.md"  # defaults to path
            assert meta.version == "1.0.0"

    def test_load_nonexistent_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            m = SteeringDependencyManager({}, steering_root=tmpdir)
            meta = m._load_specification_metadata("nonexistent.md")
            assert meta is None

    def test_load_invalid_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            steering_dir = Path(tmpdir)
            spec_file = steering_dir / "bad.md"
            spec_file.write_text("---\n[\ninvalid yaml\n---\n# Content\n", encoding="utf-8")
            m = SteeringDependencyManager({}, steering_root=str(steering_dir))
            meta = m._load_specification_metadata("bad.md")
            # Should still create metadata with defaults
            assert meta is not None

    def test_load_with_all_metadata_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            steering_dir = Path(tmpdir)
            spec_file = steering_dir / "full.md"
            spec_file.write_text(
                "---\nname: full-spec\ndescription: A full spec\nauthor: test\ncreated_at: '2025-01-01'\nupdated_at: '2025-06-01'\noptional:\n  - opt.md\nconflicts:\n  - conflict.md\ninclusion: always\nfileMatchPattern: '*.py'\nloadCondition: 'debug'\n---\n# Full spec\n",
                encoding="utf-8",
            )
            m = SteeringDependencyManager({}, steering_root=str(steering_dir))
            meta = m._load_specification_metadata("full.md")
            assert meta is not None
            assert meta.author == "test"
            assert meta.description == "A full spec"
            assert meta.inclusion == "always"
            assert meta.file_match_pattern == "*.py"
            assert meta.load_condition == "debug"
            assert "opt.md" in meta.optional_deps
            assert "conflict.md" in meta.conflicts


# ===========================================================================
# create_dependency_manager_from_config
# ===========================================================================


class TestCreateDependencyManagerFromConfig:
    def test_creates_manager(self) -> None:
        m = create_dependency_manager_from_config({"auto_resolve": False})
        assert m.auto_resolve is False
