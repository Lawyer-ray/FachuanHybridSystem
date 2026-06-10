"""Tests for DependencyGraph and SteeringDependencyManager - targeting uncovered branches."""

from __future__ import annotations

import json
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


def _make_metadata(path, name, inherits=None, requires=None, optional_deps=None, conflicts=None, priority=0):
    return SpecificationMetadata(
        path=path,
        name=name,
        priority=priority,
        inherits=inherits or [],
        requires=requires or [],
        optional_deps=optional_deps or [],
        conflicts=conflicts or [],
    )


class TestDependencyType:
    """Test DependencyType enum."""

    def test_values(self):
        assert DependencyType.INHERITS.value == "inherits"
        assert DependencyType.REQUIRES.value == "requires"
        assert DependencyType.OPTIONAL.value == "optional"
        assert DependencyType.CONFLICTS.value == "conflicts"


class TestLoadOrderStrategy:
    """Test LoadOrderStrategy enum."""

    def test_values(self):
        assert LoadOrderStrategy.PRIORITY.value == "priority"
        assert LoadOrderStrategy.DEPENDENCY.value == "dependency"
        assert LoadOrderStrategy.ALPHABETICAL.value == "alphabetical"
        assert LoadOrderStrategy.TOPOLOGICAL.value == "topological"
        assert LoadOrderStrategy.CUSTOM.value == "custom"


class TestDependencyGraph:
    """Test DependencyGraph."""

    def test_add_specification(self):
        g = DependencyGraph()
        meta = _make_metadata("a.md", "A")
        g.add_specification(meta)
        assert "a.md" in g.nodes

    def test_add_with_dependencies(self):
        g = DependencyGraph()
        meta = _make_metadata("a.md", "A", requires=["b.md"], inherits=["c.md"])
        g.add_specification(meta)
        deps = g.get_dependencies("a.md")
        assert len(deps) == 2

    def test_get_dependencies_empty(self):
        g = DependencyGraph()
        assert g.get_dependencies("nonexistent") == []

    def test_get_dependencies_filtered(self):
        g = DependencyGraph()
        meta = _make_metadata("a.md", "A", requires=["b.md"], optional_deps=["c.md"])
        g.add_specification(meta)

        req_deps = g.get_dependencies("a.md", [DependencyType.REQUIRES])
        assert len(req_deps) == 1
        assert req_deps[0].target_spec == "b.md"

        opt_deps = g.get_dependencies("a.md", [DependencyType.OPTIONAL])
        assert len(opt_deps) == 1
        assert opt_deps[0].target_spec == "c.md"

    def test_get_dependents(self):
        g = DependencyGraph()
        meta = _make_metadata("a.md", "A", requires=["b.md"])
        g.add_specification(meta)
        dependents = g.get_dependents("b.md")
        assert len(dependents) == 1
        assert dependents[0].source_spec == "a.md"

    def test_get_dependents_empty(self):
        g = DependencyGraph()
        assert g.get_dependents("nonexistent") == []

    def test_get_dependents_filtered(self):
        g = DependencyGraph()
        meta = _make_metadata("a.md", "A", requires=["b.md"], optional_deps=["c.md"])
        g.add_specification(meta)

        req_dependents = g.get_dependents("b.md", [DependencyType.REQUIRES])
        assert len(req_dependents) == 1

        opt_dependents = g.get_dependents("c.md", [DependencyType.OPTIONAL])
        assert len(opt_dependents) == 1

    def test_detect_circular_no_cycles(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", requires=["b.md"]))
        g.add_specification(_make_metadata("b.md", "B"))
        cycles = g.detect_circular_dependencies()
        assert len(cycles) == 0

    def test_detect_circular_with_cycle(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", requires=["b.md"]))
        g.add_specification(_make_metadata("b.md", "B", requires=["a.md"]))
        cycles = g.detect_circular_dependencies()
        assert len(cycles) > 0

    def test_topological_sort_simple(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", requires=["b.md"]))
        g.add_specification(_make_metadata("b.md", "B"))
        result, conflicts = g.topological_sort(["a.md", "b.md"])
        assert "b.md" in result
        assert "a.md" in result
        assert result.index("b.md") < result.index("a.md")
        assert len(conflicts) == 0

    def test_topological_sort_with_cycle(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", requires=["b.md"]))
        g.add_specification(_make_metadata("b.md", "B", requires=["a.md"]))
        result, conflicts = g.topological_sort(["a.md", "b.md"])
        assert len(conflicts) > 0
        # All specs should still be in result
        assert set(result) == {"a.md", "b.md"}

    def test_topological_sort_single(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A"))
        result, conflicts = g.topological_sort(["a.md"])
        assert result == ["a.md"]
        assert len(conflicts) == 0

    def test_validate_dependencies_no_conflicts(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", requires=["b.md"]))
        g.add_specification(_make_metadata("b.md", "B"))
        conflicts = g.validate_dependencies(["a.md", "b.md"])
        assert len(conflicts) == 0

    def test_validate_dependencies_missing_target(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", requires=["missing.md"]))
        conflicts = g.validate_dependencies(["a.md"])
        assert len(conflicts) > 0
        assert conflicts[0].conflict_type == "missing"

    def test_validate_dependencies_target_not_in_list(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", requires=["b.md"]))
        g.add_specification(_make_metadata("b.md", "B"))
        conflicts = g.validate_dependencies(["a.md"])
        assert len(conflicts) > 0

    def test_validate_dependencies_conflict(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", conflicts=["b.md"]))
        g.add_specification(_make_metadata("b.md", "B"))
        conflicts = g.validate_dependencies(["a.md", "b.md"])
        assert any(c.conflict_type == "conflict" for c in conflicts)

    def test_validate_nonexistent_spec(self):
        g = DependencyGraph()
        conflicts = g.validate_dependencies(["nonexistent.md"])
        assert len(conflicts) == 0

    def test_get_dependency_levels_simple(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", requires=["b.md"]))
        g.add_specification(_make_metadata("b.md", "B"))
        levels = g.get_dependency_levels(["a.md", "b.md"])
        assert levels["b.md"] == 0
        assert levels["a.md"] == 1

    def test_get_dependency_levels_with_cycle(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", requires=["b.md"]))
        g.add_specification(_make_metadata("b.md", "B", requires=["a.md"]))
        levels = g.get_dependency_levels(["a.md", "b.md"])
        # Both should have levels (cyclic returns 0)
        assert "a.md" in levels
        assert "b.md" in levels


class TestDependencyGraphOptionalAndConflicts:
    """Test optional and conflict dependency handling."""

    def test_optional_dependencies(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", optional_deps=["b.md"]))
        deps = g.get_dependencies("a.md", [DependencyType.OPTIONAL])
        assert len(deps) == 1

    def test_conflict_dependencies_no_reverse(self):
        g = DependencyGraph()
        g.add_specification(_make_metadata("a.md", "A", conflicts=["b.md"]))
        # Conflicts don't create reverse edges
        dependents = g.get_dependents("b.md")
        assert len(dependents) == 0


class TestSteeringDependencyManager:
    """Test SteeringDependencyManager."""

    def test_init_with_empty_dir(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={}, steering_root="/nonexistent")
            assert len(mgr._metadata_cache) == 0

    def test_normalize_dependency_list_string(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={})
            assert mgr._normalize_dependency_list("single") == ["single"]

    def test_normalize_dependency_list_list(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={})
            assert mgr._normalize_dependency_list(["a", "b"]) == ["a", "b"]

    def test_normalize_dependency_list_other(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={})
            assert mgr._normalize_dependency_list(123) == []  # type: ignore[arg-type]

    def test_config_parameters(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={
                "auto_resolve": False,
                "max_depth": 5,
                "circular_detection": False,
                "load_order_strategy": "priority",
            })
            assert mgr.auto_resolve is False
            assert mgr.max_depth == 5
            assert mgr.circular_detection is False
            assert mgr.load_order_strategy == LoadOrderStrategy.PRIORITY

    def test_resolve_load_order_alphabetical(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={"load_order_strategy": "alphabetical"})
            # Add specs manually
            mgr._metadata_cache["a.md"] = _make_metadata("a.md", "A")
            mgr._metadata_cache["b.md"] = _make_metadata("b.md", "B")
            mgr.dependency_graph.add_specification(mgr._metadata_cache["a.md"])
            mgr.dependency_graph.add_specification(mgr._metadata_cache["b.md"])

            result = mgr.resolve_load_order(["b.md", "a.md"])
            assert result.ordered_specs == ["a.md", "b.md"]

    def test_get_dependency_info_nonexistent(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={})
            result = mgr.get_dependency_info("nonexistent.md")
            assert "error" in result

    def test_get_dependency_info_existing(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={})
            meta = _make_metadata("a.md", "A", requires=["b.md"])
            mgr._metadata_cache["a.md"] = meta
            mgr.dependency_graph.add_specification(meta)

            result = mgr.get_dependency_info("a.md")
            assert "metadata" in result
            assert "dependencies" in result
            assert result["dependencies"]["requires"] == ["b.md"]

    def test_get_statistics(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={})
            meta = _make_metadata("a.md", "A", requires=["b.md"])
            mgr._metadata_cache["a.md"] = meta
            mgr.dependency_graph.add_specification(meta)

            stats = mgr.get_statistics()
            assert stats["total_specifications"] == 1
            assert stats["total_dependencies"] >= 1

    def test_export_dependency_graph_json(self, tmp_path):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={})
            meta = _make_metadata("a.md", "A")
            mgr._metadata_cache["a.md"] = meta
            mgr.dependency_graph.add_specification(meta)

            output_file = str(tmp_path / "graph.json")
            mgr.export_dependency_graph(output_file, format="json")
            with open(output_file) as f:
                data = json.load(f)
            assert "nodes" in data
            assert "edges" in data

    def test_export_unsupported_format(self, tmp_path):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={})
            meta = _make_metadata("a.md", "A")
            mgr._metadata_cache["a.md"] = meta
            mgr.dependency_graph.add_specification(meta)

            # The method catches ValueError internally and logs it
            output_file = str(tmp_path / "out.txt")
            mgr.export_dependency_graph(output_file, format="xml")
            # Should not crash; unsupported format is handled gracefully

    def test_refresh_metadata(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = SteeringDependencyManager(config={})
            meta = _make_metadata("a.md", "A")
            mgr._metadata_cache["a.md"] = meta
            assert len(mgr._metadata_cache) == 1

            mgr.refresh_metadata()
            assert len(mgr._metadata_cache) == 0


class TestCreateDependencyManagerFromConfig:
    """Test create_dependency_manager_from_config."""

    def test_creates_manager(self):
        with patch("apps.core.config.steering.dependency_manager.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path

            mgr = create_dependency_manager_from_config({"max_depth": 5})
            assert isinstance(mgr, SteeringDependencyManager)
            assert mgr.max_depth == 5
