"""Module for integration types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SteeringLoadingRule:
    pattern: str
    condition: str
    priority: int = 0
    cache_ttl: int = 3600
    dependencies: list[str] = field(default_factory=list)
    performance_threshold_ms: float = 100.0


@dataclass
class SteeringCacheConfig:
    enabled: bool = True
    ttl_seconds: int = 3600
    max_entries: int = 1000
    memory_limit_mb: int = 100
    auto_cleanup: bool = True
    cleanup_interval: int = 300


@dataclass
class SteeringPerformanceConfig:
    load_threshold_ms: float = 100.0
    warn_threshold_ms: float = 500.0
    error_threshold_ms: float = 2000.0
    enable_monitoring: bool = True
    enable_profiling: bool = False
    max_concurrent_loads: int = 4


@dataclass
class SteeringDependencyConfig:
    auto_resolve: bool = True
    max_depth: int = 10
    circular_detection: bool = True
    load_order_strategy: str = "priority"
