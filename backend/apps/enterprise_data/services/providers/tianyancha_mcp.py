"""天眼查 MCP provider 实现。"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.clients import McpToolClient
from apps.enterprise_data.services.providers.adapters import TianyanchaResponseAdapter
from apps.enterprise_data.services.types import ProviderConfig, ProviderResponse


class TianyanchaMcpProvider:
    name = "tianyancha"

    TOOL_SEARCH_COMPANIES = "search_companies"
    TOOL_GET_COMPANY_INFO = "get_company_info"
    TOOL_GET_COMPANY_SHAREHOLDERS = "get_company_shareholders"
    TOOL_GET_COMPANY_PERSONNEL = "get_company_personnel"
    TOOL_GET_PERSON_PROFILE = "get_person_profile"
    TOOL_GET_COMPANY_RISKS = "get_company_risks"
    TOOL_SEARCH_BIDDING_INFO = "search_bidding_info"

    def __init__(self, *, config: ProviderConfig) -> None:
        self.transport = config.transport
        self._client = McpToolClient(
            provider_name=self.name,
            transport=config.transport,
            base_url=config.base_url,
            sse_url=config.sse_url,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
            rate_limit_requests=config.rate_limit_requests,
            rate_limit_window_seconds=config.rate_limit_window_seconds,
            retry_max_attempts=config.retry_max_attempts,
            retry_backoff_seconds=config.retry_backoff_seconds,
        )
        self._adapter = TianyanchaResponseAdapter()

    @classmethod
    def supported_capabilities(cls) -> list[str]:
        return [
            "search_companies",
            "get_company_profile",
            "get_company_risks",
            "search_bidding_info",
            "get_company_shareholders",
            "get_company_personnel",
            "get_person_profile",
        ]

    def list_tools(self) -> list[str]:
        return self._client.list_tools()

    def describe_tools(self) -> list[dict[str, Any]]:
        return self._client.describe_tools()

    def execute_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> ProviderResponse:
        normalized_tool = str(tool_name or "").strip()
        if not normalized_tool:
            raise ValidationException(
                message="tool_name 不能为空",
                code="INVALID_TOOL_NAME",
                errors={"provider": self.name},
            )
        result = self._client.call_tool(tool_name=normalized_tool, arguments=arguments)
        return ProviderResponse(
            data=result["payload"],
            raw=result["raw"],
            tool=normalized_tool,
            meta=self._build_response_meta(result),
        )

    def search_companies(self, *, keyword: str) -> ProviderResponse:
        result = self._client.call_tool(tool_name=self.TOOL_SEARCH_COMPANIES, arguments={"keyword": keyword})
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_company_summary(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_SEARCH_COMPANIES,
            meta=self._build_response_meta(result),
        )

    def get_company_profile(self, *, company_id: str) -> ProviderResponse:
        result = self._client.call_tool(tool_name=self.TOOL_GET_COMPANY_INFO, arguments={"company_id": company_id})
        item = self._adapter.extract_primary_dict(result["payload"])
        data = self._adapter.normalize_company_profile(item)
        if not data["company_id"]:
            data["company_id"] = company_id
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_GET_COMPANY_INFO,
            meta=self._build_response_meta(result),
        )

    def get_company_risks(self, *, company_id: str, risk_type: str) -> ProviderResponse:
        result = self._client.call_tool(
            tool_name=self.TOOL_GET_COMPANY_RISKS,
            arguments={"company_id": company_id, "risk_type": risk_type},
        )
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_risk_item(item, fallback_risk_type=risk_type) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items), "risk_type": risk_type}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_GET_COMPANY_RISKS,
            meta=self._build_response_meta(result),
        )

    def get_company_shareholders(self, *, company_id: str) -> ProviderResponse:
        result = self._client.call_tool(
            tool_name=self.TOOL_GET_COMPANY_SHAREHOLDERS,
            arguments={"company_id": company_id},
        )
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_shareholder_item(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_GET_COMPANY_SHAREHOLDERS,
            meta=self._build_response_meta(result),
        )

    def get_company_personnel(self, *, company_id: str) -> ProviderResponse:
        result = self._client.call_tool(
            tool_name=self.TOOL_GET_COMPANY_PERSONNEL,
            arguments={"company_id": company_id},
        )
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_personnel_item(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_GET_COMPANY_PERSONNEL,
            meta=self._build_response_meta(result),
        )

    def get_person_profile(self, *, hcgid: str) -> ProviderResponse:
        result = self._client.call_tool(tool_name=self.TOOL_GET_PERSON_PROFILE, arguments={"hcgid": hcgid})
        item = self._adapter.extract_primary_dict(result["payload"])
        data = self._adapter.normalize_person_profile(item)
        if not data["hcgid"]:
            data["hcgid"] = hcgid
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_GET_PERSON_PROFILE,
            meta=self._build_response_meta(result),
        )

    def search_bidding_info(
        self,
        *,
        keyword: str,
        search_type: int = 1,
        bid_type: int = 4,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> ProviderResponse:
        args: dict[str, Any] = {"keyword": keyword, "search_type": search_type, "bid_type": bid_type}
        if start_date:
            args["start_date"] = start_date
        if end_date:
            args["end_date"] = end_date
        result = self._client.call_tool(tool_name=self.TOOL_SEARCH_BIDDING_INFO, arguments=args)
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_bidding_item(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_SEARCH_BIDDING_INFO,
            meta=self._build_response_meta(result),
        )

    def _build_response_meta(self, transport_result: dict[str, Any]) -> dict[str, Any]:
        requested_transport = str(transport_result.get("requested_transport", self.transport) or "").strip() or self.transport
        actual_transport = str(transport_result.get("transport", requested_transport) or "").strip() or requested_transport
        return {
            "transport": actual_transport,
            "requested_transport": requested_transport,
            "fallback_used": actual_transport != requested_transport,
            "duration_ms": max(0, int(transport_result.get("duration_ms", 0) or 0)),
            "attempt_count": max(1, int(transport_result.get("attempt_count", 1) or 1)),
        }
