from __future__ import annotations

from typing import Any

from django.core.cache import cache

import pytest

from apps.core.exceptions import PermissionDenied
from apps.enterprise_data.services.types import ProviderDescriptor, ProviderResponse
from apps.enterprise_data.services.workbench_service import McpWorkbenchService


class _FakeProvider:
    name = "tianyancha"
    transport = "streamable_http"

    def describe_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "search_companies",
                "description": "搜索企业",
                "input_schema": {
                    "type": "object",
                    "properties": {"keyword": {"type": "string"}},
                    "required": ["keyword"],
                },
            }
        ]

    def execute_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> ProviderResponse:
        return ProviderResponse(
            data={"items": [{"name": "腾讯"}], "echo": arguments},
            raw={"is_error": False},
            tool=tool_name,
            meta={"transport": "sse", "requested_transport": "streamable_http", "fallback_used": True},
        )


class _FakeRegistry:
    def __init__(self) -> None:
        self.provider = _FakeProvider()

    def list_providers(self) -> list[ProviderDescriptor]:
        return [
            ProviderDescriptor(
                name="tianyancha",
                enabled=True,
                is_default=True,
                transport="streamable_http",
                capabilities=["search_companies"],
            )
        ]

    def get_provider(self, provider: str | None = None) -> _FakeProvider:
        assert provider in (None, "tianyancha")
        return self.provider


def test_describe_tools_includes_cached_sample() -> None:
    service = McpWorkbenchService(registry=_FakeRegistry(), persist_history=False, enforce_superuser=False)
    cache_key = service._sample_cache_key(provider="tianyancha", tool_name="search_companies")
    cache.set(cache_key, {"captured_at": "2026-03-17T00:00:00+08:00", "data": {"items": [{"name": "腾讯"}]}}, 60)

    payload = service.describe_tools(provider="tianyancha")

    assert payload["provider"] == "tianyancha"
    assert len(payload["tools"]) == 1
    assert payload["tools"][0]["name"] == "search_companies"
    assert payload["tools"][0]["sample"] is not None


def test_execute_tool_returns_payload_and_stores_sample() -> None:
    service = McpWorkbenchService(registry=_FakeRegistry(), persist_history=False, enforce_superuser=False)

    result = service.execute_tool(
        provider="tianyancha",
        tool_name="search_companies",
        arguments={"keyword": "腾讯"},
    )

    assert result["provider"] == "tianyancha"
    assert result["tool"] == "search_companies"
    assert result["data"]["items"][0]["name"] == "腾讯"
    assert result["meta"]["fallback_used"] is True

    cache_key = service._sample_cache_key(provider="tianyancha", tool_name="search_companies")
    cached = cache.get(cache_key)
    assert isinstance(cached, dict)
    assert cached.get("data", {}).get("items", [{}])[0].get("name") == "腾讯"


def test_execute_tool_requires_superuser_by_default() -> None:
    service = McpWorkbenchService(registry=_FakeRegistry(), persist_history=False)

    with pytest.raises(PermissionDenied):
        service.execute_tool(
            provider="tianyancha",
            tool_name="search_companies",
            arguments={"keyword": "腾讯"},
            actor_is_superuser=False,
        )
