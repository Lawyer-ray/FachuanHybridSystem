"""Final push coverage tests for enterprise_data — types, adapter, registry."""

from __future__ import annotations

from unittest.mock import Mock

import pytest


# ============================================================================
# enterprise_data/services/types.py tests
# ============================================================================


class TestProviderConfig:
    def test_creation(self):
        from apps.enterprise_data.services.types import ProviderConfig

        config = ProviderConfig(
            name="test",
            enabled=True,
            transport="http",
            base_url="http://api.example.com",
            sse_url="http://sse.example.com",
            api_key="key123",
            timeout_seconds=30,
        )
        assert config.name == "test"
        assert config.enabled is True
        assert config.timeout_seconds == 30

    def test_frozen(self):
        from apps.enterprise_data.services.types import ProviderConfig

        config = ProviderConfig(
            name="test", enabled=True, transport="http",
            base_url="url", sse_url="sse", api_key="k", timeout_seconds=10,
        )
        with pytest.raises(AttributeError):
            config.name = "other"

    def test_defaults(self):
        from apps.enterprise_data.services.types import (
            DEFAULT_RATE_LIMIT_REQUESTS,
            ProviderConfig,
        )

        config = ProviderConfig(
            name="test", enabled=True, transport="http",
            base_url="url", sse_url="sse", api_key="k", timeout_seconds=10,
        )
        assert config.rate_limit_requests == DEFAULT_RATE_LIMIT_REQUESTS


class TestProviderDescriptor:
    def test_creation(self):
        from apps.enterprise_data.services.types import ProviderDescriptor

        desc = ProviderDescriptor(
            name="tyc",
            enabled=True,
            is_default=True,
            transport="http",
            capabilities=["search", "profile"],
        )
        assert desc.name == "tyc"
        assert desc.note == ""

    def test_with_note(self):
        from apps.enterprise_data.services.types import ProviderDescriptor

        desc = ProviderDescriptor(
            name="tyc", enabled=True, is_default=True, transport="http",
            capabilities=[], note="备注",
        )
        assert desc.note == "备注"


class TestProviderResponse:
    def test_creation(self):
        from apps.enterprise_data.services.types import ProviderResponse

        resp = ProviderResponse(data={"a": 1}, raw="raw", tool="search")
        assert resp.data == {"a": 1}
        assert resp.meta == {}

    def test_custom_meta(self):
        from apps.enterprise_data.services.types import ProviderResponse

        resp = ProviderResponse(data=None, raw=None, tool="t", meta={"k": "v"})
        assert resp.meta == {"k": "v"}


# ============================================================================
# enterprise_data/services/providers/adapters/tianyancha_response_adapter.py tests
# ============================================================================


class TestTianyanchaResponseAdapterPickStr:
    def test_first_key_found(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.pick_str({"name": "test", "company": "other"}, ("name", "company"))
        assert result == "test"

    def test_fallback_key(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.pick_str({"company": "fallback"}, ("name", "company"))
        assert result == "fallback"

    def test_no_key_found(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.pick_str({}, ("a", "b"))
        assert result == ""

    def test_none_value_skipped(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.pick_str({"a": None, "b": "val"}, ("a", "b"))
        assert result == "val"

    def test_empty_string_skipped(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.pick_str({"a": "  ", "b": "val"}, ("a", "b"))
        assert result == "val"


class TestTianyanchaExtractItems:
    def test_list_payload(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        items = adapter.extract_items([{"a": 1}, {"b": 2}, "not_dict"])
        assert len(items) == 2

    def test_dict_with_items_key(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        items = adapter.extract_items({"items": [{"a": 1}]})
        assert len(items) == 1

    def test_dict_with_list_key(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        items = adapter.extract_items({"list": [{"name": "company1"}]})
        assert items[0]["name"] == "company1"

    def test_nested_dict(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        items = adapter.extract_items({"data": {"result": [{"x": 1}]}})
        assert len(items) == 1

    def test_non_dict_non_list(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        items = adapter.extract_items("string_payload")
        assert items == []

    def test_empty_dict_returns_self(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        items = adapter.extract_items({"foo": "bar"})
        assert len(items) == 1
        assert items[0] == {"foo": "bar"}


class TestTianyanchaExtractPrimaryDict:
    def test_dict_with_items_key(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.extract_primary_dict({"data": {"name": "test"}})
        assert result == {"name": "test"}

    def test_dict_with_list_of_dicts(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.extract_primary_dict({"result": [{"a": 1}, {"b": 2}]})
        assert result == {"a": 1}

    def test_list_payload(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.extract_primary_dict([{"x": 1}, {"y": 2}])
        assert result == {"x": 1}

    def test_empty_list(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.extract_primary_dict([])
        assert result == {}

    def test_non_dict_non_list(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.extract_primary_dict("string")
        assert result == {}


class TestTianyanchaNormalize:
    def test_normalize_company_summary(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        item = {
            "company_id": "123",
            "companyName": "测试公司",
            "legalPersonName": "张三",
            "regStatus": "在业",
            "estiblishTime": "2020-01-01",
            "regCapital": "100万",
            "phone": "13800138000",
        }
        result = adapter.normalize_company_summary(item)
        assert result["company_id"] == "123"
        assert result["company_name"] == "测试公司"
        assert result["legal_person"] == "张三"
        assert result["status"] == "在业"
        assert result["establish_date"] == "2020-01-01"
        assert result["registered_capital"] == "100万"
        assert result["phone"] == "13800138000"

    def test_normalize_company_summary_fallback_keys(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        item = {
            "id": "456",
            "name": "公司B",
            "status": "注销",
        }
        result = adapter.normalize_company_summary(item)
        assert result["company_id"] == "456"
        assert result["company_name"] == "公司B"

    def test_normalize_company_profile(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        item = {
            "companyName": "公司A",
            "creditCode": "91110000MA001EXAMPLE",
            "legalPersonName": "李四",
            "regStatus": "在业",
            "regLocation": "北京市朝阳区",
            "businessScope": "技术开发",
        }
        result = adapter.normalize_company_profile(item)
        assert result["company_name"] == "公司A"
        assert result["unified_social_credit_code"] == "91110000MA001EXAMPLE"
        assert result["address"] == "北京市朝阳区"
        assert result["business_scope"] == "技术开发"

    def test_normalize_risk_item(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        item = {
            "riskType": "司法风险",
            "title": "诉讼信息",
            "level": "高",
            "amount": "100万",
            "date": "2024-01-01",
            "source": "法院",
        }
        result = adapter.normalize_risk_item(item, fallback_risk_type="默认风险")
        assert result["risk_type"] == "司法风险"
        assert result["title"] == "诉讼信息"
        assert result["source"] == "法院"

    def test_normalize_risk_item_fallback(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.normalize_risk_item({}, fallback_risk_type="默认")
        assert result["risk_type"] == "默认"

    def test_normalize_shareholder_item(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        item = {
            "name": "股东A",
            "subConAm": "50万",
            "holdRatio": "50%",
            "conDate": "2020-01-01",
        }
        result = adapter.normalize_shareholder_item(item)
        assert result["name"] == "股东A"
        assert result["amount"] == "50万"
        assert result["ratio"] == "50%"

    def test_normalize_personnel_item(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        item = {"hcgid": "h1", "name": "张总", "position": "总经理", "education": "博士"}
        result = adapter.normalize_personnel_item(item)
        assert result["name"] == "张总"
        assert result["position"] == "总经理"

    def test_normalize_person_profile(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        item = {"name": "张三", "position": "CEO", "intro": "简介", "resume": "履历"}
        result = adapter.normalize_person_profile(item)
        assert result["name"] == "张三"
        assert result["intro"] == "简介"
        assert result["resume"] == "履历"

    def test_normalize_bidding_item(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        item = {
            "title": "招标公告",
            "projectName": "项目A",
            "role": "中标人",
            "amount": "500万",
            "date": "2024-06-01",
            "region": "广东省",
            "source": "招标网",
            "url": "http://example.com",
        }
        result = adapter.normalize_bidding_item(item)
        assert result["title"] == "招标公告"
        assert result["project_name"] == "项目A"
        assert result["link"] == "http://example.com"


class TestTianyanchaCleanMarkdownValue:
    def test_basic_clean(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        assert adapter._clean_markdown_value("**bold**") == "bold"
        assert adapter._clean_markdown_value("`code`") == "code"
        assert adapter._clean_markdown_value("") == ""
        assert adapter._clean_markdown_value(None) == ""
        assert adapter._clean_markdown_value("  spaces  ") == "spaces"


class TestTianyanchaExtractMarkdownResult:
    def test_string_payload(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result("  markdown  ") == "markdown"

    def test_dict_with_result_key(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result({"result": "content"}) == "content"

    def test_dict_with_text_key(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result({"text": "content"}) == "content"

    def test_non_string_non_dict(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result(123) == ""


class TestTianyanchaParseSearchCompaniesMarkdown:
    def test_no_results(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.parse_search_companies_markdown("no results here")
        assert result == []

    def test_with_results(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        md = """企业搜索结果

## 1. 测试公司

| **企业ID** | 123 |
| **法定代表人** | 张三 |
| **经营状态** | 在业 |
| **成立日期** | 2020-01-01 |
| **注册资本** | 100万 |
| **联系电话** | 13800138000 |
"""
        result = adapter.parse_search_companies_markdown(md)
        assert len(result) >= 1
        assert result[0]["company_name"] == "测试公司"
        assert result[0]["company_id"] == "123"


class TestTianyanchaParseCompanyProfileMarkdown:
    def test_empty_payload(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        result = adapter.parse_company_profile_markdown("")
        assert result == {}

    def test_with_profile(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )

        adapter = TianyanchaResponseAdapter()
        md = """# 🏢 测试公司

| **企业ID** | 123 |
| **统一社会信用代码** | 91110000MA001EXAMPLE |
| **法定代表人** | 张三 |
| **经营状态** | 在业 |
| **成立日期** | 2020-01-01 |
| **注册资本** | 100万 |
| **注册地址** | 北京市朝阳区 |
| **联系电话** | 13800138000 |
"""
        result = adapter.parse_company_profile_markdown(md)
        assert result["company_name"] == "测试公司"
        assert result["unified_social_credit_code"] == "91110000MA001EXAMPLE"
        assert result["legal_person"] == "张三"
        assert result["address"] == "北京市朝阳区"
