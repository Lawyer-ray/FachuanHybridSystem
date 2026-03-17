"""企业数据查询 API 的 Schema 定义。"""

from __future__ import annotations

from typing import Any

from ninja import Field, Schema


class EnterpriseDataMetaOut(Schema):
    provider: str
    transport: str
    requested_transport: str | None = None
    fallback_used: bool = False
    tool: str
    capability: str
    cached: bool = False


class ProviderInfoOut(Schema):
    name: str
    enabled: bool
    is_default: bool
    transport: str
    capabilities: list[str]
    tools: list[str] = Field(default_factory=list)
    note: str = ""


class EnterpriseProvidersOut(Schema):
    items: list[ProviderInfoOut]


class CompanySummaryOut(Schema):
    company_id: str
    company_name: str
    legal_person: str = ""
    status: str = ""
    establish_date: str = ""
    registered_capital: str = ""


class CompanyProfileOut(Schema):
    company_id: str
    company_name: str
    unified_social_credit_code: str = ""
    legal_person: str = ""
    status: str = ""
    establish_date: str = ""
    registered_capital: str = ""
    address: str = ""
    business_scope: str = ""


class CompanyRiskItemOut(Schema):
    risk_type: str = ""
    title: str = ""
    level: str = ""
    amount: str = ""
    publish_date: str = ""
    source: str = ""


class BiddingItemOut(Schema):
    title: str = ""
    project_name: str = ""
    role: str = ""
    amount: str = ""
    date: str = ""
    region: str = ""
    source: str = ""
    link: str = ""


class EnterpriseQueryOut(Schema):
    query: dict[str, Any]
    data: Any
    meta: EnterpriseDataMetaOut
    raw: Any | None = None
