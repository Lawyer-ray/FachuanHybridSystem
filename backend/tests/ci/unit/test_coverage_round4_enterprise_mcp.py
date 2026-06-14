"""Coverage round 4: qichacha_mcp + tianyancha_mcp."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.types import ProviderConfig, ProviderResponse


def _make_config(**overrides):
    defaults = dict(
        name="test",
        enabled=True,
        transport="streamable_http",
        base_url="http://localhost:8080",
        sse_url="",
        api_key="key123",
        timeout_seconds=30,
    )
    defaults.update(overrides)
    return ProviderConfig(**defaults)


# ============================================================
# QichachaMcpProvider
# ============================================================

class TestQichachaMcpProvider:
    def _make_provider(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        with patch("apps.enterprise_data.services.providers.qichacha_mcp.McpToolClient"):
            return QichachaMcpProvider(config=_make_config())

    def test_supported_capabilities(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        caps = QichachaMcpProvider.supported_capabilities()
        assert "search_companies" in caps
        assert "get_company_profile" in caps
        assert "get_company_risks" in caps

    def test_get_client_for_unsupported_capability(self):
        p = self._make_provider()
        with pytest.raises(ValidationException) as exc_info:
            p._get_client_for_capability("nonexistent")
        assert "不支持" in str(exc_info.value)

    def test_execute_tool_empty_name(self):
        p = self._make_provider()
        with pytest.raises(ValidationException) as exc_info:
            p.execute_tool(tool_name="", arguments={})
        assert "tool_name" in str(exc_info.value)

    def test_execute_tool_success(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {"data": "ok"}, "raw": {}, "duration_ms": 10, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        p._clients = {"company": mock_client}
        result = p.execute_tool(tool_name="get_company_by_query", arguments={"searchKey": "test"})
        assert isinstance(result, ProviderResponse)

    def test_execute_tool_all_clients_fail(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.side_effect = RuntimeError("fail")
        p._clients = {"company": mock_client}
        with pytest.raises(ValidationException) as exc_info:
            p.execute_tool(tool_name="some_tool", arguments={})
        assert "工具调用失败" in str(exc_info.value)

    def test_search_companies(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        p._clients = {"company": mock_client}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.search_companies(keyword="test")
        assert result.data["total"] == 0

    def test_get_company_profile(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {"data": {}}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        p._clients = {"company": mock_client}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_primary_dict.return_value = {}
            mock_adapter.normalize_company_profile.return_value = {"company_id": "", "phone": ""}
            result = p.get_company_profile(company_id="C1")
        assert result.data["company_id"] == "C1"

    def test_get_company_profile_with_phone_fallback(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        contact_resp = {"payload": {"联系方式信息": {"电话": [{"电话号码": "13800138000"}]}}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        mock_client.call_tool.side_effect = [
            {"payload": {}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1},
            contact_resp,
        ]
        p._clients = {"company": mock_client}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_primary_dict.return_value = {}
            mock_adapter.normalize_company_profile.return_value = {"company_id": "", "phone": ""}
            result = p.get_company_profile(company_id="C1")
        assert result.data["phone"] == "13800138000"

    def test_get_company_risks(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        p._clients = {"risk": mock_client}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.get_company_risks(company_id="C1", risk_type="dishonest")
        assert result.data["risk_type"] == "dishonest"

    def test_get_company_shareholders(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        p._clients = {"company": mock_client}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.get_company_shareholders(company_id="C1")
        assert result.data["total"] == 0

    def test_get_company_personnel(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        p._clients = {"company": mock_client}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.get_company_personnel(company_id="C1")
        assert result.data["total"] == 0

    def test_get_person_profile(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        p._clients = {"executive": mock_client}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_primary_dict.return_value = {}
            mock_adapter.normalize_person_profile.return_value = {"hcgid": ""}
            result = p.get_person_profile(hcgid="H1")
        assert result.data["hcgid"] == "H1"

    def test_search_bidding_info(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        p._clients = {"operation": mock_client}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.search_bidding_info(keyword="test", start_date="2024-01-01", end_date="2024-12-31")
        assert result.data["total"] == 0

    def test_search_bidding_no_dates(self):
        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        p._clients = {"operation": mock_client}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.search_bidding_info(keyword="test")
        assert result.data["total"] == 0

    def test_extract_phone_from_contact(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        payload = {"联系方式信息": {"电话": [{"电话号码": "010-12345678"}]}}
        assert QichachaMcpProvider._extract_phone_from_contact(payload) == "010-12345678"

    def test_extract_phone_not_dict(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        assert QichachaMcpProvider._extract_phone_from_contact("not a dict") == ""

    def test_extract_phone_no_contact_info(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        assert QichachaMcpProvider._extract_phone_from_contact({}) == ""

    def test_extract_phone_no_phones_list(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        assert QichachaMcpProvider._extract_phone_from_contact({"联系方式信息": {}}) == ""

    def test_extract_phone_empty_list(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        assert QichachaMcpProvider._extract_phone_from_contact({"联系方式信息": {"电话": []}}) == ""

    def test_extract_phone_non_dict_item(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        assert QichachaMcpProvider._extract_phone_from_contact({"联系方式信息": {"电话": ["not_dict"]}}) == ""

    def test_extract_phone_empty_number(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        assert QichachaMcpProvider._extract_phone_from_contact({"联系方式信息": {"电话": [{"电话号码": ""}]}}) == ""

    def test_build_response_meta(self):
        p = self._make_provider()
        transport_result = {
            "requested_transport": "streamable_http",
            "transport": "sse",
            "duration_ms": 100,
            "attempt_count": 2,
            "api_key_pool_size": 3,
            "api_key_attempt_count": 2,
            "api_key_switched": True,
        }
        meta = p._build_response_meta(transport_result)
        assert meta["fallback_used"] is True
        assert meta["duration_ms"] == 100
        assert meta["api_key_switched"] is True

    def test_build_response_meta_defaults(self):
        p = self._make_provider()
        meta = p._build_response_meta({})
        assert meta["fallback_used"] is False
        assert meta["duration_ms"] == 0
        assert meta["attempt_count"] == 1

    def test_list_tools(self):
        p = self._make_provider()
        for client in p._clients.values():
            client.list_tools.return_value = ["tool1"]
        assert len(p.list_tools()) == 6

    def test_describe_tools(self):
        p = self._make_provider()
        for client in p._clients.values():
            client.describe_tools.return_value = [{"name": "tool1"}]
        assert len(p.describe_tools()) == 6


# ============================================================
# TianyanchaMcpProvider
# ============================================================

class TestTianyanchaMcpProvider:
    def _make_provider(self):
        from apps.enterprise_data.services.providers.tianyancha_mcp import TianyanchaMcpProvider
        with patch("apps.enterprise_data.services.providers.tianyancha_mcp.McpToolClient"):
            return TianyanchaMcpProvider(config=_make_config())

    def test_supported_capabilities(self):
        from apps.enterprise_data.services.providers.tianyancha_mcp import TianyanchaMcpProvider
        caps = TianyanchaMcpProvider.supported_capabilities()
        assert "search_companies" in caps
        assert len(caps) == 7

    def test_execute_tool_empty_name(self):
        p = self._make_provider()
        with pytest.raises(ValidationException):
            p.execute_tool(tool_name="", arguments={})

    def test_execute_tool_whitespace_name(self):
        p = self._make_provider()
        with pytest.raises(ValidationException):
            p.execute_tool(tool_name="   ", arguments={})

    def test_execute_tool_success(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {"data": "ok"}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        result = p.execute_tool(tool_name="test_tool", arguments={"arg": "val"})
        assert isinstance(result, ProviderResponse)
        assert result.tool == "test_tool"

    def test_search_companies(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            mock_adapter.parse_search_companies_markdown.return_value = []
            result = p.search_companies(keyword="test")
        assert result.data["total"] == 0

    def test_search_companies_markdown_fallback(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {"text": "some md"}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = [{"name": "test"}]
            mock_adapter.normalize_company_summary.return_value = {"company_id": "", "company_name": ""}
            mock_adapter.parse_search_companies_markdown.return_value = [{"company_id": "C1", "company_name": "Test"}]
            result = p.search_companies(keyword="test")
        assert len(result.data["items"]) == 1

    def test_get_company_profile(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_primary_dict.return_value = {}
            mock_adapter.normalize_company_profile.return_value = {
                "company_id": "", "company_name": "TestCorp", "unified_social_credit_code": "",
                "legal_person": "", "address": "",
            }
            result = p.get_company_profile(company_id="C1")
        assert result.data["company_id"] == "C1"

    def test_get_company_profile_markdown_fallback(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {"content": "md"}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_primary_dict.return_value = {}
            mock_adapter.normalize_company_profile.return_value = {"company_id": "", "company_name": "", "unified_social_credit_code": "", "legal_person": "", "address": ""}
            mock_adapter.parse_company_profile_markdown.return_value = {"company_id": "", "company_name": "Fallback Corp", "unified_social_credit_code": "", "legal_person": "", "address": ""}
            result = p.get_company_profile(company_id="C1")
        assert result.data["company_name"] == "Fallback Corp"

    def test_get_company_risks(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.get_company_risks(company_id="C1", risk_type="dishonest")
        assert result.data["risk_type"] == "dishonest"

    def test_get_company_shareholders(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.get_company_shareholders(company_id="C1")
        assert result.data["total"] == 0

    def test_get_company_personnel(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.get_company_personnel(company_id="C1")
        assert result.data["total"] == 0

    def test_get_person_profile(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_primary_dict.return_value = {}
            mock_adapter.normalize_person_profile.return_value = {"hcgid": ""}
            result = p.get_person_profile(hcgid="H1")
        assert result.data["hcgid"] == "H1"

    def test_search_bidding_info(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.search_bidding_info(keyword="test", start_date="2024-01-01", end_date="2024-12-31")
        assert result.data["total"] == 0

    def test_search_bidding_no_dates(self):
        p = self._make_provider()
        p._client.call_tool.return_value = {"payload": {"items": []}, "raw": {}, "duration_ms": 5, "attempt_count": 1, "transport": "streamable_http", "requested_transport": "streamable_http", "api_key_pool_size": 1, "api_key_attempt_count": 1}
        with patch.object(p, '_adapter') as mock_adapter:
            mock_adapter.extract_items.return_value = []
            result = p.search_bidding_info(keyword="test")
        assert result.data["total"] == 0

    def test_build_response_meta(self):
        p = self._make_provider()
        meta = p._build_response_meta({"requested_transport": "sse", "transport": "streamable_http", "duration_ms": 50, "attempt_count": 3, "api_key_pool_size": 2, "api_key_attempt_count": 1, "api_key_switched": True})
        assert meta["fallback_used"] is True
        assert meta["api_key_switched"] is True

    def test_build_response_meta_defaults(self):
        p = self._make_provider()
        meta = p._build_response_meta({})
        assert meta["duration_ms"] == 0
        assert meta["attempt_count"] == 1
        assert meta["fallback_used"] is False

    def test_list_tools(self):
        p = self._make_provider()
        p._client.list_tools.return_value = ["tool_a"]
        assert p.list_tools() == ["tool_a"]

    def test_describe_tools(self):
        p = self._make_provider()
        p._client.describe_tools.return_value = [{"name": "tool_a"}]
        assert p.describe_tools() == [{"name": "tool_a"}]
