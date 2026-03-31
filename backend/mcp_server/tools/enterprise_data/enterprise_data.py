"""企业数据查询 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_enterprise_providers(include_tools: bool = False) -> dict[str, Any]:
    """查询可用的企业数据提供商列表（如天眼查等）。include_tools=True 时返回支持的工具列表。"""
    return client.get("/enterprise-data/providers", params={"include_tools": include_tools})  # type: ignore[return-value]


def search_companies(keyword: str, provider: str | None = None) -> dict[str, Any]:
    """按关键词搜索企业。返回企业列表，包含 company_id 可用于后续查询。"""
    params: dict[str, Any] = {"keyword": keyword}
    if provider:
        params["provider"] = provider
    return client.get("/enterprise-data/companies/search", params=params)  # type: ignore[return-value]


def get_company_profile(company_id: str, provider: str | None = None) -> dict[str, Any]:
    """获取企业基本信息（注册资本、法人、地址等）。company_id 来自 search_companies 结果。"""
    params: dict[str, Any] = {}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/companies/{company_id}", params=params)  # type: ignore[return-value]


def get_company_risks(
    company_id: str,
    risk_type: str = "自身风险",
    provider: str | None = None,
) -> dict[str, Any]:
    """查询企业风险信息。risk_type 可选：自身风险、周边风险、预警提醒、历史风险。"""
    params: dict[str, Any] = {"risk_type": risk_type}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/companies/{company_id}/risks", params=params)  # type: ignore[return-value]


def get_company_shareholders(company_id: str, provider: str | None = None) -> dict[str, Any]:
    """查询企业股东信息。"""
    params: dict[str, Any] = {}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/companies/{company_id}/shareholders", params=params)  # type: ignore[return-value]


def get_company_personnel(company_id: str, provider: str | None = None) -> dict[str, Any]:
    """查询企业主要人员（高管、法人等）。"""
    params: dict[str, Any] = {}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/companies/{company_id}/personnel", params=params)  # type: ignore[return-value]


def get_person_profile(hcgid: str, provider: str | None = None) -> dict[str, Any]:
    """查询自然人信息。hcgid 为人员唯一标识，来自 get_company_personnel 结果。"""
    params: dict[str, Any] = {}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/personnel/{hcgid}", params=params)  # type: ignore[return-value]


def search_bidding_info(
    keyword: str,
    search_type: int = 1,
    bid_type: int = 4,
    start_date: str | None = None,
    end_date: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """搜索招投标信息。start_date/end_date 格式：YYYY-MM-DD。"""
    params: dict[str, Any] = {"keyword": keyword, "search_type": search_type, "bid_type": bid_type}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if provider:
        params["provider"] = provider
    return client.get("/enterprise-data/biddings/search", params=params)  # type: ignore[return-value]
