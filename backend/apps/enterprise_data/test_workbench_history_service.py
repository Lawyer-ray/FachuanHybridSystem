from __future__ import annotations

from typing import Any

import pytest

from apps.enterprise_data.models import McpWorkbenchExecution
from apps.enterprise_data.services.types import ProviderDescriptor, ProviderResponse
from apps.enterprise_data.services.workbench_service import McpWorkbenchService


class _HistoryProvider:
    name = "tianyancha"
    transport = "streamable_http"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def describe_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "search_companies",
                "description": "搜索企业",
                "input_schema": {
                    "type": "object",
                    "properties": {"keyword": {"type": "string"}, "api_key": {"type": "string"}},
                    "required": ["keyword"],
                },
            }
        ]

    def execute_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> ProviderResponse:
        self.calls.append({"tool_name": tool_name, "arguments": dict(arguments)})
        return ProviderResponse(
            data={
                "items": [{"name": "腾讯"}],
                "authorization": "Bearer mock-token-1234567890",
                "api_key": "sk-example-secret-abcdefghijklmnopqrstuvwxyz",
            },
            raw={"authorization": "Bearer mock-token-1234567890"},
            tool=tool_name,
            meta={"transport": "sse", "requested_transport": "streamable_http", "fallback_used": True},
        )


class _HistoryRegistry:
    def __init__(self, provider: _HistoryProvider) -> None:
        self.provider = provider

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

    def get_provider(self, provider: str | None = None) -> _HistoryProvider:
        assert provider in (None, "tianyancha")
        return self.provider


@pytest.mark.django_db
def test_execute_tool_persists_history_and_masks_sensitive_values() -> None:
    provider = _HistoryProvider()
    service = McpWorkbenchService(registry=_HistoryRegistry(provider), enforce_superuser=False)

    result = service.execute_tool(
        provider="tianyancha",
        tool_name="search_companies",
        arguments={"keyword": "腾讯", "api_key": "sk_example_abcdefg1234567890"},
        actor_username="admin_user",
    )

    assert result["meta"]["fallback_used"] is True
    assert result["arguments"]["api_key"] != "sk_example_abcdefg1234567890"
    assert "***" in result["arguments"]["api_key"]
    assert result["data"]["api_key"] != "sk-example-secret-abcdefghijklmnopqrstuvwxyz"
    assert "***" in result["data"]["api_key"]

    history = McpWorkbenchExecution.objects.order_by("-id").first()
    assert history is not None
    assert history.success is True
    assert history.provider == "tianyancha"
    assert history.tool_name == "search_companies"
    assert history.operator_username == "admin_user"
    assert history.actual_transport == "sse"
    assert history.requested_transport == "streamable_http"
    assert history.arguments.get("api_key", "").find("***") > 0


@pytest.mark.django_db
def test_replay_execution_uses_original_arguments_and_creates_replay_record() -> None:
    provider = _HistoryProvider()
    service = McpWorkbenchService(registry=_HistoryRegistry(provider), enforce_superuser=False)

    first = service.execute_tool(
        provider="tianyancha",
        tool_name="search_companies",
        arguments={"keyword": "阿里巴巴"},
        actor_username="admin_user",
    )
    first_row = McpWorkbenchExecution.objects.order_by("-id").first()
    assert first_row is not None

    replay = service.replay_execution(execution_id=first_row.id, actor_username="admin_user")
    second_row = McpWorkbenchExecution.objects.order_by("-id").first()
    assert second_row is not None

    assert replay["replay_of"] == first_row.id
    assert second_row.replay_of_id == first_row.id
    assert provider.calls[0]["arguments"]["keyword"] == "阿里巴巴"
    assert provider.calls[1]["arguments"]["keyword"] == "阿里巴巴"
    assert first["tool"] == "search_companies"
