"""天眼查 MCP provider 实现。"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.transports import McpToolTransport
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

    _ITEM_KEYS = (
        "items",
        "list",
        "rows",
        "records",
        "companies",
        "data",
        "result",
    )

    def __init__(self, *, config: ProviderConfig) -> None:
        self.transport = config.transport
        self._transport = McpToolTransport(
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
        return self._transport.list_tools()

    def describe_tools(self) -> list[dict[str, Any]]:
        return self._transport.describe_tools()

    def execute_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> ProviderResponse:
        normalized_tool = str(tool_name or "").strip()
        if not normalized_tool:
            raise ValidationException(
                message="tool_name 不能为空",
                code="INVALID_TOOL_NAME",
                errors={"provider": self.name},
            )
        result = self._transport.call_tool(tool_name=normalized_tool, arguments=arguments)
        return ProviderResponse(
            data=result["payload"],
            raw=result["raw"],
            tool=normalized_tool,
            meta=self._build_response_meta(result),
        )

    def search_companies(self, *, keyword: str) -> ProviderResponse:
        result = self._transport.call_tool(tool_name=self.TOOL_SEARCH_COMPANIES, arguments={"keyword": keyword})
        items = self._extract_items(result["payload"])
        normalized_items = [self._normalize_company_summary(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_SEARCH_COMPANIES,
            meta=self._build_response_meta(result),
        )

    def get_company_profile(self, *, company_id: str) -> ProviderResponse:
        result = self._transport.call_tool(tool_name=self.TOOL_GET_COMPANY_INFO, arguments={"company_id": company_id})
        item = self._extract_primary_dict(result["payload"])
        data = self._normalize_company_profile(item)
        if not data["company_id"]:
            data["company_id"] = company_id
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_GET_COMPANY_INFO,
            meta=self._build_response_meta(result),
        )

    def get_company_risks(self, *, company_id: str, risk_type: str) -> ProviderResponse:
        result = self._transport.call_tool(
            tool_name=self.TOOL_GET_COMPANY_RISKS,
            arguments={"company_id": company_id, "risk_type": risk_type},
        )
        items = self._extract_items(result["payload"])
        normalized_items = [self._normalize_risk_item(item, fallback_risk_type=risk_type) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items), "risk_type": risk_type}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_GET_COMPANY_RISKS,
            meta=self._build_response_meta(result),
        )

    def get_company_shareholders(self, *, company_id: str) -> ProviderResponse:
        result = self._transport.call_tool(
            tool_name=self.TOOL_GET_COMPANY_SHAREHOLDERS,
            arguments={"company_id": company_id},
        )
        items = self._extract_items(result["payload"])
        normalized_items = [self._normalize_shareholder_item(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_GET_COMPANY_SHAREHOLDERS,
            meta=self._build_response_meta(result),
        )

    def get_company_personnel(self, *, company_id: str) -> ProviderResponse:
        result = self._transport.call_tool(
            tool_name=self.TOOL_GET_COMPANY_PERSONNEL,
            arguments={"company_id": company_id},
        )
        items = self._extract_items(result["payload"])
        normalized_items = [self._normalize_personnel_item(item) for item in items]
        data = {"items": normalized_items, "total": len(normalized_items)}
        return ProviderResponse(
            data=data,
            raw=result["raw"],
            tool=self.TOOL_GET_COMPANY_PERSONNEL,
            meta=self._build_response_meta(result),
        )

    def get_person_profile(self, *, hcgid: str) -> ProviderResponse:
        result = self._transport.call_tool(tool_name=self.TOOL_GET_PERSON_PROFILE, arguments={"hcgid": hcgid})
        item = self._extract_primary_dict(result["payload"])
        data = self._normalize_person_profile(item)
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
        result = self._transport.call_tool(tool_name=self.TOOL_SEARCH_BIDDING_INFO, arguments=args)
        items = self._extract_items(result["payload"])
        normalized_items = [self._normalize_bidding_item(item) for item in items]
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

    @staticmethod
    def _pick_str(obj: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = obj.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def _extract_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        queue: list[dict[str, Any]] = [payload]
        while queue:
            current = queue.pop(0)
            for key in self._ITEM_KEYS:
                value = current.get(key)
                if isinstance(value, list):
                    normalized = [item for item in value if isinstance(item, dict)]
                    if normalized:
                        return normalized
                if isinstance(value, dict):
                    queue.append(value)
        return [payload]

    def _extract_primary_dict(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            for key in self._ITEM_KEYS:
                value = payload.get(key)
                if isinstance(value, dict):
                    return value
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value[0]
            return payload
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    return item
        return {}

    def _normalize_company_summary(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "company_id": self._pick_str(item, ("company_id", "companyId", "id", "cid", "tycId")),
            "company_name": self._pick_str(item, ("company_name", "companyName", "name", "company")),
            "legal_person": self._pick_str(item, ("legalPersonName", "legal_person", "legalRepresentative")),
            "status": self._pick_str(item, ("regStatus", "status", "operatingStatus")),
            "establish_date": self._pick_str(item, ("estiblishTime", "establishDate", "foundedDate")),
            "registered_capital": self._pick_str(item, ("regCapital", "registeredCapital", "capital")),
        }

    def _normalize_company_profile(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "company_id": self._pick_str(item, ("company_id", "companyId", "id", "cid", "tycId")),
            "company_name": self._pick_str(item, ("company_name", "companyName", "name", "company")),
            "unified_social_credit_code": self._pick_str(
                item,
                ("creditCode", "unifiedSocialCreditCode", "socialCreditCode", "unified_social_credit_code"),
            ),
            "legal_person": self._pick_str(item, ("legalPersonName", "legal_person", "legalRepresentative")),
            "status": self._pick_str(item, ("regStatus", "status", "operatingStatus")),
            "establish_date": self._pick_str(item, ("estiblishTime", "establishDate", "foundedDate")),
            "registered_capital": self._pick_str(item, ("regCapital", "registeredCapital", "capital")),
            "address": self._pick_str(item, ("regLocation", "address", "registeredAddress")),
            "business_scope": self._pick_str(item, ("businessScope", "scope")),
        }

    def _normalize_risk_item(self, item: dict[str, Any], *, fallback_risk_type: str) -> dict[str, str]:
        return {
            "risk_type": self._pick_str(item, ("riskType", "type")) or fallback_risk_type,
            "title": self._pick_str(item, ("title", "riskTitle", "event", "name")),
            "level": self._pick_str(item, ("level", "riskLevel", "degree")),
            "amount": self._pick_str(item, ("amount", "amountStr", "money")),
            "publish_date": self._pick_str(item, ("date", "publishDate", "eventTime", "filingDate")),
            "source": self._pick_str(item, ("source", "court", "channel")),
        }

    def _normalize_shareholder_item(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "name": self._pick_str(item, ("name", "shareholderName", "holderName")),
            "amount": self._pick_str(item, ("subConAm", "capital", "amount", "contribution")),
            "ratio": self._pick_str(item, ("holdRatio", "ratio", "sharePercent")),
            "contribution_date": self._pick_str(item, ("conDate", "date", "subscribeDate")),
            "source": self._pick_str(item, ("source", "type")),
        }

    def _normalize_personnel_item(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "hcgid": self._pick_str(item, ("hcgid", "id", "personCompanyId")),
            "name": self._pick_str(item, ("name", "personName")),
            "position": self._pick_str(item, ("position", "jobTitle", "post")),
            "education": self._pick_str(item, ("education", "academicDegree")),
            "source": self._pick_str(item, ("source", "type")),
        }

    def _normalize_person_profile(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "hcgid": self._pick_str(item, ("hcgid", "id", "personCompanyId")),
            "name": self._pick_str(item, ("name", "personName")),
            "position": self._pick_str(item, ("position", "jobTitle", "post")),
            "intro": self._pick_str(item, ("intro", "introduction", "profile")),
            "resume": self._pick_str(item, ("resume", "experience", "workExperience")),
        }

    def _normalize_bidding_item(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "title": self._pick_str(item, ("title", "announceTitle", "name")),
            "project_name": self._pick_str(item, ("projectName", "project", "bidName")),
            "role": self._pick_str(item, ("role", "identity", "bidRole")),
            "amount": self._pick_str(item, ("amount", "amountStr", "money")),
            "date": self._pick_str(item, ("date", "publishDate", "bidDate", "winningDate")),
            "region": self._pick_str(item, ("region", "province", "city", "area")),
            "source": self._pick_str(item, ("source", "type", "noticeType")),
            "link": self._pick_str(item, ("url", "link", "detailUrl")),
        }
