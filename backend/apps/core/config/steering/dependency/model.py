"""Module for model."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DependencyType(Enum):
    INHERITS = "inherits"
    REQUIRES = "requires"
    OPTIONAL = "optional"
    CONFLICTS = "conflicts"


class LoadOrderStrategy(Enum):
    PRIORITY = "priority"
    DEPENDENCY = "dependency"
    ALPHABETICAL = "alphabetical"
    TOPOLOGICAL = "topological"
    CUSTOM = "custom"


@dataclass
class DependencyInfo:
    source_spec: str
    target_spec: str
    dependency_type: DependencyType
    version_constraint: str | None = None
    condition: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpecificationMetadata:
    path: str
    name: str
    version: str = "1.0.0"
    priority: int = 0
    tags: list[str] = field(default_factory=list)
    description: str = ""
    author: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    inherits: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    optional_deps: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    inclusion: str = "manual"
    file_match_pattern: str | None = None
    load_condition: str | None = None


@dataclass
class DependencyConflict:
    conflict_type: str
    description: str
    affected_specs: list[str]
    suggested_resolution: str | None = None


@dataclass
class LoadOrderResult:
    ordered_specs: list[str]
    dependency_levels: dict[str, int]
    conflicts: list[DependencyConflict]
    warnings: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
