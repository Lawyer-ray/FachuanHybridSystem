"""企业数据查询 MCP tools

失败语义：本模块**不做** try/except 兜底。上游 4xx/5xx/超时会以
``FachuanApiError``/``FachuanTransportError``（均为 ``ToolError`` 子类）
抛出，MCP 层呈现为 ``isError: true`` 的工具错误——模型能明确看到失败
与原因（含传输层的重试指引）。曾在这里 ``except Exception`` 后返回
``{"success": False, ...}`` 伪正常结果：模型看到的是成功调用 + 空列表，
容易得出「没有配置 provider」这类假事实结论，还吞掉了重试指引。
批量循环内的部分失败聚合（如 folder_file）才需要归一化，单查询工具不要。

超时（三十六轮审计）：全部调用显式 ``timeout=180``。provider 链是同步
长 IO——qichacha MCP provider 内部一次调用最长 30+30s，``_execute``
provider 降级时串行再试一家，后端可合法跑到 ~120s；默认 60s 会把工具
先掐断而 provider 侧继续跑（GET 幂等重试还会再叠一次）。
"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_enterprise_providers(include_tools: bool = False) -> dict[str, Any]:
    """查询可用的企业数据提供商列表（如天眼查等）。include_tools=True 时返回支持的工具列表。"""
    return client.get("/enterprise-data/providers", params={"include_tools": include_tools}, timeout=180)  # type: ignore[no-any-return]


def search_companies(keyword: str, provider: str | None = None) -> dict[str, Any]:
    """按关键词搜索企业（企业数据原始查询面）。返回企业列表，包含 company_id 可用于后续查询。

    与 ``enterprise_search``（建客户预填链路）同源——本系列面向**企业情报**
    （画像/风险/股东/招投标）；要「搜公司→一键生成客户草稿」用 ``enterprise_search``+
    ``enterprise_prefill``。
    """
    params: dict[str, Any] = {"keyword": keyword}
    if provider:
        params["provider"] = provider
    return client.get("/enterprise-data/companies/search", params=params, timeout=180)  # type: ignore[no-any-return]


def get_company_profile(company_id: str, provider: str | None = None) -> dict[str, Any]:
    """获取企业基本信息（注册资本、法人、地址等）。company_id 来自 search_companies 结果。"""
    params: dict[str, Any] = {}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/companies/{company_id}", params=params, timeout=180)  # type: ignore[no-any-return]


def get_company_risks(
    company_id: str,
    risk_type: str = "自身风险",
    provider: str | None = None,
) -> dict[str, Any]:
    """查询企业风险信息。risk_type 可选：自身风险、周边风险、预警提醒、历史风险。"""
    params: dict[str, Any] = {"risk_type": risk_type}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/companies/{company_id}/risks", params=params, timeout=180)  # type: ignore[no-any-return]


def get_company_shareholders(company_id: str, provider: str | None = None) -> dict[str, Any]:
    """查询企业股东信息（持股比例、认缴额）。"""
    params: dict[str, Any] = {}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/companies/{company_id}/shareholders", params=params, timeout=180)  # type: ignore[no-any-return]


def get_company_personnel(company_id: str, provider: str | None = None) -> dict[str, Any]:
    """查询企业主要人员（高管、法定代表人等）。"""
    params: dict[str, Any] = {}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/companies/{company_id}/personnel", params=params, timeout=180)  # type: ignore[no-any-return]


def get_person_profile(hcgid: str, provider: str | None = None) -> dict[str, Any]:
    """查询自然人信息。hcgid 为人员唯一标识，来自 get_company_personnel 结果。"""
    params: dict[str, Any] = {}
    if provider:
        params["provider"] = provider
    return client.get(f"/enterprise-data/personnel/{hcgid}", params=params, timeout=180)  # type: ignore[no-any-return]


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
    return client.get("/enterprise-data/biddings/search", params=params, timeout=180)  # type: ignore[no-any-return]
