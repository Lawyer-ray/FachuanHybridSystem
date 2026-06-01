from __future__ import annotations

import pytest

from apps.legal_research.services.executor_components.source_gateway import ExecutorSourceGatewayMixin
from apps.legal_research.services.sources.weike.transport import WeikeTransportMixin


def test_executor_source_gateway_retry_backoff_uses_exponential_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(
        "apps.legal_research.services.executor_components.source_gateway.time.sleep",
        lambda seconds: slept.append(seconds),
    )
    monkeypatch.setattr(
        "apps.legal_research.services.executor_components.source_gateway.random.uniform",
        lambda _a, b: b,
    )

    class _Gateway(ExecutorSourceGatewayMixin):
        RETRY_BACKOFF_SECONDS = 0.5
        RETRY_BACKOFF_MAX_SECONDS = 6.0

    _Gateway._sleep_for_retry(attempt=3)
    assert slept[0] == pytest.approx(2.5)

    slept.clear()
    _Gateway._sleep_for_retry(attempt=10)
    assert slept[0] == pytest.approx(7.5)


def test_weike_transport_retry_backoff_uses_exponential_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(
        "apps.legal_research.services.sources.weike.transport.time.sleep",
        lambda seconds: slept.append(seconds),
    )
    monkeypatch.setattr(
        "apps.legal_research.services.sources.weike.transport.random.uniform",
        lambda _a, b: b,
    )

    WeikeTransportMixin._sleep_for_retry(attempt=3, base_seconds=0.8)
    assert slept[0] == pytest.approx(4.0)
