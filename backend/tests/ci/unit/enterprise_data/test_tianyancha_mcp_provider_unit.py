"""TianyanchaMcpProvider 单元测试（mock MCP 客户端，无网络）。

覆盖：工具执行、各能力方法的调用参数与回退解析链
（items → markdown → table）、company_id/hcgid 回填、meta 构建。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.providers import tianyancha_mcp as tyc_mod
from apps.enterprise_data.services.providers.tianyancha_mcp import TianyanchaMcpProvider
from apps.enterprise_data.services.types import ProviderConfig


def _config() -> ProviderConfig:
    return ProviderConfig(
        name="tianyancha",
        enabled=True,
        transport="streamable_http",
        base_url="http://tyc-mcp.local/mcp",
        sse_url="http://tyc-mcp.local/sse",
        api_key="k",
        timeout_seconds=30,
    )


def _transport_result(payload: Any, **overrides: Any) -> dict[str, Any]:
    base = {
        "payload": payload,
        "raw": {"echo": payload},
        "transport": "streamable_http",
        "requested_transport": "streamable_http",
        "duration_ms": 8,
        "attempt_count": 1,
    }
    base.update(overrides)
    return base


@pytest.fixture
def provider() -> TianyanchaMcpProvider:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tyc_mod, "McpToolClient", MagicMock())
        prov = TianyanchaMcpProvider(config=_config())
    return prov


def _stub_call(provider: TianyanchaMcpProvider, result_or_side_effect: Any) -> Mock:
    if isinstance(result_or_side_effect, list):
        call_tool = Mock(side_effect=result_or_side_effect)
    else:
        call_tool = Mock(return_value=result_or_side_effect)
    provider._client.call_tool = call_tool
    return call_tool


class TestBasics:
    def test_supported_capabilities(self):
        caps = TianyanchaMcpProvider.supported_capabilities()
        assert caps == [
            "search_companies",
            "get_company_profile",
            "get_company_risks",
            "search_bidding_info",
            "get_company_shareholders",
            "get_company_personnel",
            "get_person_profile",
        ]

    def test_list_and_describe_tools_delegate(self, provider):
        provider._client.list_tools = Mock(return_value=["search_companies"])
        provider._client.describe_tools = Mock(return_value=[{"name": "search_companies"}])
        assert provider.list_tools() == ["search_companies"]
        assert provider.describe_tools() == [{"name": "search_companies"}]


class TestExecuteTool:
    def test_empty_tool_name_rejected(self, provider):
        with pytest.raises(ValidationException, match="tool_name 不能为空"):
            provider.execute_tool(tool_name="  ", arguments={})

    def test_success_returns_payload_and_meta(self, provider):
        payload = {"items": [{"name": "甲公司"}]}
        call_tool = _stub_call(provider, _transport_result(payload))

        response = provider.execute_tool(tool_name=" search_companies ", arguments={"query": "甲"})

        call_tool.assert_called_once_with(tool_name="search_companies", arguments={"query": "甲"})
        assert response.data == payload
        assert response.tool == "search_companies"
        assert response.meta["attempt_count"] == 1


class TestSearchCompanies:
    def test_dict_items_path(self, provider):
        payload = {"items": [{"company_id": "t1", "company_name": "甲公司"}]}
        call_tool = _stub_call(provider, _transport_result(payload))

        response = provider.search_companies(keyword="甲公司")

        call_tool.assert_called_once_with(
            tool_name=TianyanchaMcpProvider.TOOL_SEARCH_COMPANIES, arguments={"query": "甲公司"}
        )
        assert response.data["items"][0]["company_name"] == "甲公司"
        assert response.data["total"] == 1

    def test_markdown_fallback_when_items_empty(self, provider):
        adapter = MagicMock(wraps=provider._adapter)
        adapter.extract_items.return_value = []
        adapter.parse_search_companies_markdown.return_value = [{"company_id": "m1", "company_name": "甲公司"}]
        adapter.parse_search_companies_table.return_value = []
        provider._adapter = adapter
        _stub_call(provider, _transport_result("markdown payload"))

        response = provider.search_companies(keyword="甲公司")

        adapter.parse_search_companies_markdown.assert_called_once_with("markdown payload")
        assert response.data["items"] == [{"company_id": "m1", "company_name": "甲公司"}]

    def test_table_fallback_when_markdown_empty(self, provider):
        adapter = MagicMock(wraps=provider._adapter)
        adapter.extract_items.return_value = []
        adapter.parse_search_companies_markdown.return_value = []
        adapter.parse_search_companies_table.return_value = [{"company_id": "tb1", "company_name": "乙公司"}]
        provider._adapter = adapter
        _stub_call(provider, _transport_result("table payload"))

        response = provider.search_companies(keyword="乙公司")

        adapter.parse_search_companies_table.assert_called_once_with("table payload")
        assert response.data["items"][0]["company_id"] == "tb1"


class TestGetCompanyProfile:
    def test_key_fields_present_skip_markdown(self, provider):
        payload = {"company_id": "", "company_name": "甲公司", "legal_person": "张三"}
        _stub_call(provider, _transport_result(payload))

        response = provider.get_company_profile(company_id="t-9")

        assert response.data["company_name"] == "甲公司"
        assert response.data["company_id"] == "t-9"
        assert response.tool == TianyanchaMcpProvider.TOOL_GET_COMPANY_INFO

    def test_markdown_fallback_when_key_fields_missing(self, provider):
        adapter = MagicMock(wraps=provider._adapter)
        adapter.extract_primary_dict.return_value = {"company_id": "", "company_name": ""}
        adapter.normalize_company_profile.return_value = {
            "company_id": "",
            "company_name": "",
            "unified_social_credit_code": "",
            "legal_person": "",
            "address": "",
        }
        adapter.parse_company_profile_markdown.return_value = {
            "company_id": "mk-1",
            "company_name": "甲公司",
            "unified_social_credit_code": "",
            "legal_person": "",
            "address": "",
        }
        provider._adapter = adapter
        _stub_call(provider, _transport_result("profile markdown"))

        response = provider.get_company_profile(company_id="mk-1")

        adapter.parse_company_profile_markdown.assert_called_once_with("profile markdown")
        assert response.data["company_name"] == "甲公司"


class TestRiskAndListMethods:
    def test_get_company_risks(self, provider):
        payload = {"items": [{"riskType": "dishonest", "title": "失信"}]}
        call_tool = _stub_call(provider, _transport_result(payload))

        response = provider.get_company_risks(company_id="t-2", risk_type="dishonest")

        assert call_tool.call_args.kwargs == {
            "tool_name": TianyanchaMcpProvider.TOOL_GET_COMPANY_RISKS,
            "arguments": {"company_id": "t-2", "risk_type": "dishonest"},
        }
        assert response.data["items"][0]["title"] == "失信"
        assert response.data["risk_type"] == "dishonest"

    def test_get_company_shareholders(self, provider):
        payload = {"items": [{"name": "股东甲", "ratio": "51%"}]}
        call_tool = _stub_call(provider, _transport_result(payload))

        response = provider.get_company_shareholders(company_id="t-3")

        assert call_tool.call_args.kwargs["tool_name"] == TianyanchaMcpProvider.TOOL_GET_COMPANY_SHAREHOLDERS
        assert response.data["items"][0]["name"] == "股东甲"
        assert response.data["total"] == 1

    def test_get_company_personnel(self, provider):
        payload = {"items": [{"name": "高管乙", "position": "监事"}]}
        call_tool = _stub_call(provider, _transport_result(payload))

        response = provider.get_company_personnel(company_id="t-4")

        assert call_tool.call_args.kwargs["tool_name"] == TianyanchaMcpProvider.TOOL_GET_COMPANY_PERSONNEL
        assert response.data["items"][0]["position"] == "监事"

    def test_get_person_profile_fills_hcgid(self, provider):
        payload = {"name": "王五"}
        call_tool = _stub_call(provider, _transport_result(payload))

        response = provider.get_person_profile(hcgid="h-7")

        assert call_tool.call_args.kwargs == {
            "tool_name": TianyanchaMcpProvider.TOOL_GET_PERSON_PROFILE,
            "arguments": {"hcgid": "h-7"},
        }
        assert response.data["name"] == "王五"
        assert response.data["hcgid"] == "h-7"

    def test_search_bidding_info_optional_dates(self, provider):
        call_tool = _stub_call(provider, _transport_result({"items": []}))

        provider.search_bidding_info(keyword="项目", search_type=2, bid_type=1, start_date="2026-01-01")

        args = call_tool.call_args.kwargs
        assert args["tool_name"] == TianyanchaMcpProvider.TOOL_SEARCH_BIDDING_INFO
        assert args["arguments"] == {
            "keyword": "项目",
            "search_type": 2,
            "bid_type": 1,
            "start_date": "2026-01-01",
        }

    def test_search_bidding_info_with_end_date_only(self, provider):
        call_tool = _stub_call(provider, _transport_result({"items": []}))

        provider.search_bidding_info(keyword="项目", end_date="2026-12-31")

        assert call_tool.call_args.kwargs["arguments"] == {
            "keyword": "项目",
            "search_type": 1,
            "bid_type": 4,
            "end_date": "2026-12-31",
        }

    def test_search_bidding_info_without_dates(self, provider):
        call_tool = _stub_call(provider, _transport_result({"items": []}))
        provider.search_bidding_info(keyword="项目")
        assert call_tool.call_args.kwargs["arguments"] == {
            "keyword": "项目",
            "search_type": 1,
            "bid_type": 4,
        }


class TestBuildResponseMeta:
    def test_fallback_flag_and_clamps(self, provider):
        meta = provider._build_response_meta(
            {
                "transport": "",
                "requested_transport": "",
                "duration_ms": -1,
                "attempt_count": 0,
                "api_key_pool_size": 0,
                "api_key_attempt_count": 0,
            }
        )
        # 空串回退到 provider.transport，再空回退到 requested
        assert meta["transport"] == "streamable_http"
        assert meta["requested_transport"] == "streamable_http"
        assert meta["fallback_used"] is False
        assert meta["duration_ms"] == 0
        assert meta["attempt_count"] == 1
        assert meta["api_key_pool_size"] == 1
        assert meta["api_key_attempt_count"] == 1
        assert meta["api_key_switched"] is False

    def test_transport_switch_detected(self, provider):
        meta = provider._build_response_meta({"transport": "sse", "requested_transport": "streamable_http"})
        assert meta["fallback_used"] is True
