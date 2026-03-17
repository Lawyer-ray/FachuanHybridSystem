"""企业数据 provider 抽象定义。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from apps.enterprise_data.services.types import ProviderResponse


@runtime_checkable
class EnterpriseDataProvider(Protocol):
    name: str
    transport: str

    @classmethod
    def supported_capabilities(cls) -> list[str]: ...

    def list_tools(self) -> list[str]: ...

    def describe_tools(self) -> list[dict[str, object]]: ...

    def execute_tool(self, *, tool_name: str, arguments: dict[str, object]) -> ProviderResponse: ...

    def search_companies(self, *, keyword: str) -> ProviderResponse: ...

    def get_company_profile(self, *, company_id: str) -> ProviderResponse: ...

    def get_company_risks(self, *, company_id: str, risk_type: str) -> ProviderResponse: ...

    def get_company_shareholders(self, *, company_id: str) -> ProviderResponse: ...

    def get_company_personnel(self, *, company_id: str) -> ProviderResponse: ...

    def get_person_profile(self, *, hcgid: str) -> ProviderResponse: ...

    def search_bidding_info(
        self,
        *,
        keyword: str,
        search_type: int = 1,
        bid_type: int = 4,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> ProviderResponse: ...
