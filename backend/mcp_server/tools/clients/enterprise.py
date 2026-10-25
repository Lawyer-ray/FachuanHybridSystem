"""企业数据搜索 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def enterprise_search(keyword: str, provider: str | None = None) -> dict[str, Any]:
    """搜索企业信息（建客户预填流程用）。keyword 为搜索关键词（公司名）；provider 为数据源（如 tianyancha、qichacha）。

    返回 ``{keyword, provider, items, total}``（后端 ``EnterpriseCompanySearchOut``），
    企业条目在 ``items`` 里，不是顶层数组。与 ``search_companies``（企业数据原始
    查询面）同源——本工具是**建客户预填链路**的入口：搜到后用企业标识调
    ``enterprise_prefill`` 直接生成客户草稿；只要原始企业情报（股东/风险/招投标）
    用 ``search_companies`` 系列。
    """
    params: dict[str, Any] = {"keyword": keyword}
    if provider:
        params["provider"] = provider
    return client.get("/client/clients/enterprise/search", params=params, timeout=180)  # type: ignore[no-any-return]


def enterprise_prefill(company_id: str) -> dict[str, Any]:
    """根据企业 ID 预填充客户信息（统一社会信用代码、法人等）。

    后端必填 query 参数是 ``company_id``（先用 ``enterprise_search`` 拿到的
    企业标识）。早前工具传 ``keyword``，参数名不符，调用必然 422。
    """
    return client.get("/client/clients/enterprise/prefill", params={"company_id": company_id}, timeout=180)  # type: ignore[no-any-return]
