"""企查查 MCP provider 骨架（占位）。"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.types import ProviderConfig, ProviderResponse


class QichachaMcpProvider:
    """企查查 provider 骨架。

    当前仅完成注册与配置入口，业务能力待后续接入官方 MCP/API 后补齐。
    """

    name = "qichacha"

    def __init__(self, *, config: ProviderConfig) -> None:
        self.transport = config.transport

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
        return []

    def describe_tools(self) -> list[dict[str, Any]]:
        return []

    def execute_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> ProviderResponse:
        self._raise_not_implemented(capability=tool_name, arguments=arguments)
        raise AssertionError  # unreachable

    def search_companies(self, *, keyword: str) -> ProviderResponse:
        self._raise_not_implemented(capability="search_companies", arguments={"keyword": keyword})
        raise AssertionError  # unreachable

    def get_company_profile(self, *, company_id: str) -> ProviderResponse:
        self._raise_not_implemented(capability="get_company_profile", arguments={"company_id": company_id})
        raise AssertionError  # unreachable

    def get_company_risks(self, *, company_id: str, risk_type: str) -> ProviderResponse:
        self._raise_not_implemented(
            capability="get_company_risks",
            arguments={"company_id": company_id, "risk_type": risk_type},
        )
        raise AssertionError  # unreachable

    def get_company_shareholders(self, *, company_id: str) -> ProviderResponse:
        self._raise_not_implemented(capability="get_company_shareholders", arguments={"company_id": company_id})
        raise AssertionError  # unreachable

    def get_company_personnel(self, *, company_id: str) -> ProviderResponse:
        self._raise_not_implemented(capability="get_company_personnel", arguments={"company_id": company_id})
        raise AssertionError  # unreachable

    def get_person_profile(self, *, hcgid: str) -> ProviderResponse:
        self._raise_not_implemented(capability="get_person_profile", arguments={"hcgid": hcgid})
        raise AssertionError  # unreachable

    def search_bidding_info(
        self,
        *,
        keyword: str,
        search_type: int = 1,
        bid_type: int = 4,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> ProviderResponse:
        self._raise_not_implemented(
            capability="search_bidding_info",
            arguments={
                "keyword": keyword,
                "search_type": search_type,
                "bid_type": bid_type,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        raise AssertionError  # unreachable

    @staticmethod
    def _raise_not_implemented(*, capability: str, arguments: dict[str, Any]) -> None:
        raise ValidationException(
            message="企查查 Provider 尚未实现，请先完成 MCP 接口映射",
            code="PROVIDER_NOT_IMPLEMENTED",
            errors={"provider": QichachaMcpProvider.name, "capability": capability, "arguments": arguments},
        )
