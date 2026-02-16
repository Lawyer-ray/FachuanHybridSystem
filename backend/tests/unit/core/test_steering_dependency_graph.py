import pytest

from apps.core.config.steering.dependency.graph import DependencyGraph
from apps.core.config.steering.dependency.model import DependencyConflict, SpecificationMetadata


def _spec(path: str, *, inherits=None, requires=None) -> SpecificationMetadata:
    return SpecificationMetadata(
        path=path,
        name=path,
        inherits=list(inherits or []),
        requires=list(requires or []),
    )


def _conflict_types(conflicts: list[DependencyConflict]) -> set[str]:
    return {c.conflict_type for c in conflicts}


class TestSteeringDependencyGraph:
    def test_validate_dependencies_reports_missing_required(self):
        g = DependencyGraph()
        g.add_specification(_spec("A", requires=["B"]))

        conflicts = g.validate_dependencies(["A"])
        assert _conflict_types(conflicts) == {"missing"}
        assert conflicts[0].affected_specs == ["A", "B"]

    def test_topological_sort_orders_dependencies_first(self):
        g = DependencyGraph()
        g.add_specification(_spec("A", requires=["B"]))
        g.add_specification(_spec("B"))

        ordered, conflicts = g.topological_sort(["A", "B"])
        assert conflicts == []
        assert ordered.index("B") < ordered.index("A")

    def test_topological_sort_reports_circular_when_remaining(self):
        g = DependencyGraph()
        g.add_specification(_spec("A", requires=["B"]))
        g.add_specification(_spec("B", requires=["A"]))

        ordered, conflicts = g.topological_sort(["A", "B"])
        assert "circular" in _conflict_types(conflicts)
        assert set(ordered) == {"A", "B"}

    def test_detect_circular_dependencies_returns_cycle_path(self):
        g = DependencyGraph()
        g.add_specification(_spec("A", requires=["B"]))
        g.add_specification(_spec("B", requires=["A"]))

        cycles = g.detect_circular_dependencies()
        assert cycles
        assert cycles[0][0] == cycles[0][-1]
        assert set(cycles[0][:-1]) == {"A", "B"}

    def test_get_dependency_levels_increase_along_chain(self):
        g = DependencyGraph()
        g.add_specification(_spec("A", requires=["B"]))
        g.add_specification(_spec("B", requires=["C"]))
        g.add_specification(_spec("C"))

        levels = g.get_dependency_levels(["A", "B", "C"])
        assert levels["C"] == 0
        assert levels["B"] == 1
        assert levels["A"] == 2
