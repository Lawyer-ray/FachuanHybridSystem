"""企查查 MCP provider 实现。

企查查提供 6 个独立 MCP Server，每个 Server 有独立 URL 但共享 API Key：
- qcc-company: 企业基座（工商登记、股东、年报等）
- qcc-risk: 风控大脑（失信、被执行、行政处罚等）
- qcc-ipr: 知产引擎（专利、商标、软著等）
- qcc-operation: 经营罗盘（招投标、资质、新闻等）
- qcc-executive: 董监高画像（高管风险、关联企业等）
- qcc-history: 历史存档（历史股东、法人变更等）

本 provider 为每个 Server 创建独立的 McpToolClient 实例，
通过路由表将统一能力映射到对应 Server 的工具。
"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.clients import McpToolClient
from apps.enterprise_data.services.providers.adapters import QichachaResponseAdapter
from apps.enterprise_data.services.types import ProviderConfig, ProviderResponse

# 每个 MCP Server 的路径后缀
_SERVER_PATHS: dict[str, str] = {
    "company": "/mcp/company/stream",
    "risk": "/mcp/risk/stream",
    "ipr": "/mcp/ipr/stream",
    "operation": "/mcp/operation/stream",
    "executive": "/mcp/executive/stream",
    "history": "/mcp/history/stream",
}

# 统一能力 → (server_key, qcc_tool_name)
_CAPABILITY_ROUTING: dict[str, tuple[str, str]] = {
    "search_companies": ("company", "get_company_by_query"),
    "get_company_profile": ("company", "get_company_registration_info"),
    "get_company_shareholders": ("company", "get_shareholder_info"),
    "get_company_personnel": ("company", "get_key_personnel"),
    "get_company_risks": ("risk", "get_dishonest_info"),
    "search_bidding_info": ("operation", "get_bidding_info"),
    "get_person_profile": ("executive", "get_executive_positions"),
}


class QichachaMcpProvider:
    """企查查 MCP provider — 通过 6 个独立 MCP Server 提供企业数据。"""

    name = "qichacha"

    def __init__(self, *, config: ProviderConfig) -> None:
        self.transport = config.transport
        self._adapter = QichachaResponseAdapter()

        # 为每个 Server 创建独立的 McpToolClient
        self._clients: dict[str, McpToolClient] = {}
        base_url = (config.base_url or "").rstrip("/")
        for server_key, path in _SERVER_PATHS.items():
            self._clients[server_key] = McpToolClient(
                provider_name=f"{self.name}_{server_key}",
                transport=config.transport,
                base_url=f"{base_url}{path}",
                sse_url="",  # 企查查仅支持 streamable_http
                api_key=config.api_key,
                api_keys=config.api_keys,
                timeout_seconds=config.timeout_seconds,
                rate_limit_requests=config.rate_limit_requests,
                rate_limit_window_seconds=config.rate_limit_window_seconds,
                retry_max_attempts=config.retry_max_attempts,
                retry_backoff_seconds=config.retry_backoff_seconds,
            )

    def _get_client_for_capability(self, capability: str) -> tuple[str, str, McpToolClient]:
        """返回 (server_key, tool_name, client) 三元组。"""
        routing = _CAPABILITY_ROUTING.get(capability)
        if not routing:
            raise ValidationException(
                message=f"企查查不支持此能力: {capability}",
                code="UNSUPPORTED_CAPABILITY",
                errors={"provider": self.name, "capability": capability},
            )
        server_key, tool_name = routing
        return server_key, tool_name, self._clients[server_key]

    @classmethod
    def supported_capabilities(cls) -> list[str]:
        return list(_CAPABILITY_ROUTING.keys())

    def list_tools(self) -> list[str]:
        all_tools: list[str] = []
        for client in self._clients.values():
            all_tools.extend(client.list_tools())
        return all_tools

    def describe_tools(self) -> list[dict[str, Any]]:
        all_descriptions: list[dict[str, Any]] = []
        for client in self._clients.values():
            all_descriptions.extend(client.describe_tools())
        return all_descriptions

    def execute_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> ProviderResponse:
        normalized_tool = str(tool_name or "").strip()
        if not normalized_tool:
            raise ValidationException(
                message="tool_name 不能为空",
                code="INVALID_TOOL_NAME",
                errors={"provider": self.name},
            )
        # 尝试从所有 client 中调用
        for server_key, client in self._clients.items():
            try:
                result = client.call_tool(tool_name=normalized_tool, arguments=arguments)
                return ProviderResponse(
                    data=result["payload"],
                    raw=result["raw"],
                    tool=normalized_tool,
                    meta=self._build_response_meta(result),
                )
            except Exception:
                continue
        raise ValidationException(
            message=f"企查查工具调用失败: {normalized_tool}",
            code="TOOL_CALL_FAILED",
            errors={"provider": self.name, "tool": normalized_tool},
        )

    def search_companies(self, *, keyword: str) -> ProviderResponse:
        _, tool_name, client = self._get_client_for_capability("search_companies")
        result = client.call_tool(tool_name=tool_name, arguments={"searchKey": keyword})
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_company_summary(item) for item in items]
        normalized_items = [item for item in normalized_items if item.get("company_id") or item.get("company_name")]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=tool_name,
            meta=self._build_response_meta(result),
        )

    def get_company_profile(self, *, company_id: str) -> ProviderResponse:
        _, tool_name, client = self._get_client_for_capability("get_company_profile")
        result = client.call_tool(tool_name=tool_name, arguments={"searchKey": company_id})
        item = self._adapter.extract_primary_dict(result["payload"])
        data = self._adapter.normalize_company_profile(item)
        if not data["company_id"]:
            data["company_id"] = company_id
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=tool_name,
            meta=self._build_response_meta(result),
        )

    def get_company_risks(self, *, company_id: str, risk_type: str) -> ProviderResponse:
        # 根据 risk_type 选择对应的 QCC 风险工具
        risk_tool_map = {
            "dishonest": "get_dishonest_info",
            "executed": "get_judgment_debtor_info",
            "punishment": "get_administrative_penalty",
            "court_document": "get_judicial_documents",
            "abnormal": "get_business_exception",
            "judicial_sale": "get_judicial_auction",
            "high_consumption": "get_high_consumption_restriction",
        }
        tool_name = risk_tool_map.get(risk_type, "get_dishonest_info")
        client = self._clients["risk"]
        result = client.call_tool(tool_name=tool_name, arguments={"searchKey": company_id})
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_risk_item(item, fallback_risk_type=risk_type) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items), "risk_type": risk_type}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=tool_name,
            meta=self._build_response_meta(result),
        )

    def get_company_shareholders(self, *, company_id: str) -> ProviderResponse:
        _, tool_name, client = self._get_client_for_capability("get_company_shareholders")
        result = client.call_tool(tool_name=tool_name, arguments={"searchKey": company_id})
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_shareholder_item(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=tool_name,
            meta=self._build_response_meta(result),
        )

    def get_company_personnel(self, *, company_id: str) -> ProviderResponse:
        _, tool_name, client = self._get_client_for_capability("get_company_personnel")
        result = client.call_tool(tool_name=tool_name, arguments={"searchKey": company_id})
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_personnel_item(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=tool_name,
            meta=self._build_response_meta(result),
        )

    def get_person_profile(self, *, hcgid: str) -> ProviderResponse:
        _, tool_name, client = self._get_client_for_capability("get_person_profile")
        result = client.call_tool(tool_name=tool_name, arguments={"searchKey": hcgid})
        item = self._adapter.extract_primary_dict(result["payload"])
        data = self._adapter.normalize_person_profile(item)
        if not data["hcgid"]:
            data["hcgid"] = hcgid
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=tool_name,
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
        _, tool_name, client = self._get_client_for_capability("search_bidding_info")
        args: dict[str, Any] = {"searchKey": keyword}
        if start_date:
            args["startDate"] = start_date
        if end_date:
            args["endDate"] = end_date
        result = client.call_tool(tool_name=tool_name, arguments=args)
        items = self._adapter.extract_items(result["payload"])
        normalized_items = [self._adapter.normalize_bidding_item(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=tool_name,
            meta=self._build_response_meta(result),
        )

    def _build_response_meta(self, transport_result: dict[str, Any]) -> dict[str, Any]:
        requested_transport = (
            str(transport_result.get("requested_transport", self.transport) or "").strip() or self.transport
        )
        actual_transport = (
            str(transport_result.get("transport", requested_transport) or "").strip() or requested_transport
        )
        return {
            "transport": actual_transport,
            "requested_transport": requested_transport,
            "fallback_used": actual_transport != requested_transport,
            "duration_ms": max(0, int(transport_result.get("duration_ms", 0) or 0)),
            "attempt_count": max(1, int(transport_result.get("attempt_count", 1) or 1)),
            "api_key_pool_size": max(1, int(transport_result.get("api_key_pool_size", 1) or 1)),
            "api_key_attempt_count": max(1, int(transport_result.get("api_key_attempt_count", 1) or 1)),
            "api_key_switched": bool(transport_result.get("api_key_switched", False)),
        }
