"""企业数据服务类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_PROVIDER_NAME = "tianyancha"
DEFAULT_TRANSPORT = "streamable_http"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_CACHE_TTL_SECONDS = 300
DEFAULT_RISK_TYPE = "自身风险"
DEFAULT_RATE_LIMIT_REQUESTS = 60
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_RETRY_MAX_ATTEMPTS = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25
DEFAULT_METRICS_WINDOW_SECONDS = 300
DEFAULT_ALERT_MIN_SAMPLES = 20
DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD = 0.90
DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD = 0.35
DEFAULT_ALERT_AVG_LATENCY_MS_THRESHOLD = 3000


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    enabled: bool
    transport: str
    base_url: str
    sse_url: str
    api_key: str
    timeout_seconds: int
    api_keys: tuple[str, ...] = ()
    rate_limit_requests: int = DEFAULT_RATE_LIMIT_REQUESTS
    rate_limit_window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS
    retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS


@dataclass(frozen=True)
class ProviderDescriptor:
    name: str
    enabled: bool
    is_default: bool
    transport: str
    capabilities: list[str]
    note: str = ""


@dataclass
class ProviderResponse:
    data: Any
    raw: Any
    tool: str
    meta: dict[str, Any] = field(default_factory=dict)
