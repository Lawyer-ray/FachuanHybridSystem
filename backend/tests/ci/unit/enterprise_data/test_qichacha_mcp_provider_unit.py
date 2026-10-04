"""QichachaMcpProvider 单元测试（mock MCP 客户端，无网络）。

覆盖：execute_tool 多 Server 容错、各能力方法的工具路由与参数、
响应 meta 构建（fallback/钳制）、profile 电话补充链路。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.providers import qichacha_mcp as qcc_mod
from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
from apps.enterprise_data.services.types import ProviderConfig


def _config() -> ProviderConfig:
    return ProviderConfig(
        name="qichacha",
        enabled=True,
        transport="streamable_http",
        base_url="http://qcc-mcp.local",
        sse_url="",
        api_key="k",
        timeout_seconds=30,
    )


def _transport_result(payload: Any, **overrides: Any) -> dict[str, Any]:
    base = {
        "payload": payload,
        "raw": {"echo": payload},
        "transport": "streamable_http",
        "requested_transport": "streamable_http",
        "duration_ms": 15,
        "attempt_count": 1,
    }
    base.update(overrides)
    return base


@pytest.fixture
def provider() -> QichachaMcpProvider:
    return QichachaMcpProvider(config=_config())


def _stub_client(provider: QichachaMcpProvider, server_key: str, result_or_side_effect: Any) -> Mock:
    if isinstance(result_or_side_effect, list):
        call_tool = Mock(side_effect=result_or_side_effect)
    else:
        call_tool = Mock(return_value=result_or_side_effect)
    provider._clients[server_key].call_tool = call_tool
    return call_tool


class TestExecuteTool:
    def test_success_on_first_server(self, provider):
        payload = {"企业信息": {"企业名称": "甲公司"}}
        _stub_client(provider, "company", _transport_result(payload))
        response = provider.execute_tool(tool_name="get_company_by_query", arguments={"searchKey": "甲"})
        assert response.data == payload
        assert response.tool == "get_company_by_query"
        assert response.raw == {"echo": payload}
        assert response.meta["transport"] == "streamable_http"
        assert response.meta["fallback_used"] is False

    def test_falls_through_to_next_server(self, provider):
        provider._clients["company"].call_tool = Mock(side_effect=RuntimeError("company server down"))
        payload = {"风险信息": []}
        provider._clients["risk"].call_tool = Mock(return_value=_transport_result(payload))
        response = provider.execute_tool(tool_name="some_tool", arguments={})
        assert response.data == payload

    def test_all_servers_failed_raises(self, provider):
        for client in provider._clients.values():
            client.call_tool = Mock(side_effect=RuntimeError("down"))
        with pytest.raises(ValidationException, match="企查查工具调用失败"):
            provider.execute_tool(tool_name="get_company_by_query", arguments={})


class TestCapabilityRouting:
    def test_get_client_for_capability(self, provider):
        server_key, tool_name, client = provider._get_client_for_capability("search_companies")
        assert server_key == "company"
        assert tool_name == "get_company_by_query"
        assert client is provider._clients["company"]

    def test_risk_capability_uses_risk_server(self, provider):
        server_key, tool_name, _ = provider._get_client_for_capability("get_company_risks")
        assert server_key == "risk"
        assert tool_name == "get_dishonest_info"

    def test_search_companies_normalizes_and_filters(self, provider):
        payload = {
            "搜索结果": [
                {"企业名称": "甲公司", "统一社会信用代码": "USCC1", "法定代表人": "张三"},
                {"备注": "无名称无ID的噪声项"},
            ]
        }
        call_tool = _stub_client(provider, "company", _transport_result(payload))

        response = provider.search_companies(keyword="甲公司")

        call_tool.assert_called_once_with(tool_name="get_company_by_query", arguments={"searchKey": "甲公司"})
        items = response.data["items"]
        assert len(items) == 1
        assert items[0]["company_name"] == "甲公司"
        assert items[0]["company_id"] == "USCC1"
        assert items[0]["legal_person"] == "张三"
        assert response.data["total"] == 1
        assert response.tool == "get_company_by_query"


class TestGetCompanyProfile:
    def test_profile_with_phone_supplement(self, provider):
        main = _transport_result({"工商信息": {"企业名称": "甲公司", "注册地址": "上海市"}})
        contact = _transport_result({"联系方式信息": {"电话": [{"电话号码": "021-63330000"}]}})
        provider._clients["company"].call_tool = Mock(side_effect=[main, contact])

        response = provider.get_company_profile(company_id="id-1")

        assert response.data["company_name"] == "甲公司"
        assert response.data["company_id"] == "id-1"  # 详情缺失时回填入参
        assert response.data["phone"] == "021-63330000"
        calls = provider._clients["company"].call_tool.call_args_list
        assert calls[1].kwargs == {"tool_name": "get_contact_info", "arguments": {"searchKey": "id-1"}}

    def test_profile_phone_failure_ignored(self, provider):
        main = _transport_result({"工商信息": {"企业名称": "甲公司", "联系电话": "021-1"}})
        provider._clients["company"].call_tool = Mock(side_effect=[main, RuntimeError("contact down")])

        response = provider.get_company_profile(company_id="id-2")

        assert response.data["phone"] == "021-1"  # 主响应已有电话，不再补充

    def test_profile_without_phone_and_contact_call_failing(self, provider):
        """详情无电话且 get_contact_info 抛错 → 电话补充失败不影响主流程。"""
        main = _transport_result({"工商信息": {"企业名称": "甲公司"}})
        provider._clients["company"].call_tool = Mock(side_effect=[main, RuntimeError("contact down")])

        response = provider.get_company_profile(company_id="id-2b")

        assert response.data["company_name"] == "甲公司"
        assert response.data["phone"] == ""


class TestRiskMethods:
    def test_risk_type_routes_tool(self, provider):
        payload = {"风险信息": [{"title": "失信记录"}]}
        call_tool = _stub_client(provider, "risk", _transport_result(payload))

        response = provider.get_company_risks(company_id="id-3", risk_type="executed")

        assert call_tool.call_args.kwargs == {
            "tool_name": "get_judgment_debtor_info",
            "arguments": {"searchKey": "id-3"},
        }
        assert response.data["risk_type"] == "executed"
        assert response.data["items"][0]["title"] == "失信记录"
        assert response.data["items"][0]["risk_type"] == "executed"

    def test_unknown_risk_type_falls_back_to_dishonest(self, provider):
        call_tool = _stub_client(provider, "risk", _transport_result({"风险信息": []}))
        provider.get_company_risks(company_id="id-4", risk_type="weird")
        assert call_tool.call_args.kwargs["tool_name"] == "get_dishonest_info"


class TestShareholdersAndPersonnel:
    def test_shareholders(self, provider):
        payload = {"股东信息列表": [{"name": "股东甲", "subConAm": "100万", "holdRatio": "60%"}]}
        call_tool = _stub_client(provider, "company", _transport_result(payload))

        response = provider.get_company_shareholders(company_id="id-5")

        assert call_tool.call_args.kwargs["tool_name"] == "get_shareholder_info"
        item = response.data["items"][0]
        assert item["name"] == "股东甲"
        assert item["amount"] == "100万"
        assert item["ratio"] == "60%"
        assert response.data["total"] == 1

    def test_personnel(self, provider):
        payload = {"主要人员列表": [{"name": "高管乙", "position": "总经理"}]}
        call_tool = _stub_client(provider, "company", _transport_result(payload))

        response = provider.get_company_personnel(company_id="id-6")

        assert call_tool.call_args.kwargs["tool_name"] == "get_key_personnel"
        assert response.data["items"][0]["name"] == "高管乙"
        assert response.data["items"][0]["position"] == "总经理"


class TestPersonProfile:
    def test_executive_server_and_hcgid_fallback(self, provider):
        payload = {"主要人员信息": {"name": "王五", "position": "董事"}}
        call_tool = _stub_client(provider, "executive", _transport_result(payload))

        response = provider.get_person_profile(hcgid="h-1")

        assert call_tool.call_args.kwargs == {
            "tool_name": "get_executive_positions",
            "arguments": {"searchKey": "h-1"},
        }
        assert response.data["name"] == "王五"
        assert response.data["hcgid"] == "h-1"


class TestSearchBiddingInfo:
    def test_args_include_dates_only_when_given(self, provider):
        payload = {"招投标信息列表": [{"title": "某项目招标公告", "projectName": "项目A"}]}
        call_tool = _stub_client(provider, "operation", _transport_result(payload))

        response = provider.search_bidding_info(keyword="项目", start_date="2026-01-01", end_date="2026-06-30")

        args = call_tool.call_args.kwargs
        assert args["tool_name"] == "get_bidding_info"
        assert args["arguments"] == {
            "searchKey": "项目",
            "startDate": "2026-01-01",
            "endDate": "2026-06-30",
        }
        assert response.data["items"][0]["project_name"] == "项目A"

    def test_args_without_dates(self, provider):
        call_tool = _stub_client(provider, "operation", _transport_result({"招投标信息列表": []}))
        provider.search_bidding_info(keyword="项目")
        assert call_tool.call_args.kwargs["arguments"] == {"searchKey": "项目"}


class TestExtractPhoneFromContact:
    def test_phone_field_not_a_list_returns_empty(self):
        payload = {"联系方式信息": {"电话": "021-63330000"}}
        assert QichachaMcpProvider._extract_phone_from_contact(payload) == ""


class TestBuildResponseMeta:
    def test_defaults_for_empty_dict(self, provider):
        meta = provider._build_response_meta({})
        assert meta == {
            "transport": "streamable_http",
            "requested_transport": "streamable_http",
            "fallback_used": False,
            "duration_ms": 0,
            "attempt_count": 1,
            "api_key_pool_size": 1,
            "api_key_attempt_count": 1,
            "api_key_switched": False,
        }

    def test_clamps_and_flags_fallback(self, provider):
        meta = provider._build_response_meta(
            {
                "transport": "sse",
                "requested_transport": "streamable_http",
                "duration_ms": -5,
                "attempt_count": 0,
                "api_key_pool_size": 0,
                "api_key_attempt_count": 0,
                "api_key_switched": True,
            }
        )
        assert meta["transport"] == "sse"
        assert meta["fallback_used"] is True
        assert meta["duration_ms"] == 0
        assert meta["attempt_count"] == 1
        assert meta["api_key_pool_size"] == 1
        assert meta["api_key_attempt_count"] == 1
        assert meta["api_key_switched"] is True


class TestClientsConstruction:
    def test_six_servers_created(self):
        provider = QichachaMcpProvider(config=_config())
        assert set(provider._clients) == set(qcc_mod._SERVER_PATHS)
        # 每个能力路由到的 Server 均有对应 client 实例
        for capability in QichachaMcpProvider.supported_capabilities():
            server_key, _, _ = provider._get_client_for_capability(capability)
            assert server_key in provider._clients
