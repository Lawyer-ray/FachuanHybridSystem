"""Coverage tests for enterprise_data tianyancha_response_adapter."""
from __future__ import annotations

import pytest

from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import TianyanchaResponseAdapter


class TestPickStr:
    def test_first_match(self):
        result = TianyanchaResponseAdapter.pick_str({"a": "hello", "b": "world"}, ("a", "b"))
        assert result == "hello"

    def test_second_match(self):
        result = TianyanchaResponseAdapter.pick_str({"b": "world"}, ("a", "b"))
        assert result == "world"

    def test_none_skipped(self):
        result = TianyanchaResponseAdapter.pick_str({"a": None, "b": "ok"}, ("a", "b"))
        assert result == "ok"

    def test_empty_string_skipped(self):
        result = TianyanchaResponseAdapter.pick_str({"a": "  ", "b": "ok"}, ("a", "b"))
        assert result == "ok"

    def test_no_match(self):
        result = TianyanchaResponseAdapter.pick_str({}, ("a", "b"))
        assert result == ""


class TestExtractItems:
    def test_list_input(self):
        adapter = TianyanchaResponseAdapter()
        data = [{"id": 1}, {"id": 2}]
        assert adapter.extract_items(data) == data

    def test_list_with_non_dict(self):
        adapter = TianyanchaResponseAdapter()
        data = [{"id": 1}, "bad", 42]
        result = adapter.extract_items(data)
        assert result == [{"id": 1}]

    def test_non_dict_non_list(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter.extract_items("string") == []
        assert adapter.extract_items(42) == []

    def test_dict_with_items_key(self):
        adapter = TianyanchaResponseAdapter()
        data = {"items": [{"id": 1}]}
        assert adapter.extract_items(data) == [{"id": 1}]

    def test_dict_with_list_key(self):
        adapter = TianyanchaResponseAdapter()
        data = {"list": [{"name": "test"}]}
        assert adapter.extract_items(data) == [{"name": "test"}]

    def test_dict_with_rows_key(self):
        adapter = TianyanchaResponseAdapter()
        data = {"rows": [{"id": 1}]}
        assert adapter.extract_items(data) == [{"id": 1}]

    def test_dict_nested(self):
        adapter = TianyanchaResponseAdapter()
        data = {"data": {"items": [{"id": 1}]}}
        assert adapter.extract_items(data) == [{"id": 1}]

    def test_dict_fallback_returns_self(self):
        adapter = TianyanchaResponseAdapter()
        data = {"foo": "bar"}
        result = adapter.extract_items(data)
        assert result == [{"foo": "bar"}]

    def test_dict_with_dict_value(self):
        adapter = TianyanchaResponseAdapter()
        data = {"result": {"id": 1, "name": "test"}}
        result = adapter.extract_items(data)
        # result is a dict, not a list, so it gets queued
        assert len(result) == 1


class TestExtractPrimaryDict:
    def test_dict_with_items_key(self):
        adapter = TianyanchaResponseAdapter()
        data = {"items": {"name": "company"}}
        result = adapter.extract_primary_dict(data)
        assert result == {"name": "company"}

    def test_dict_with_list_first_item(self):
        adapter = TianyanchaResponseAdapter()
        data = {"data": [{"id": 1}, {"id": 2}]}
        result = adapter.extract_primary_dict(data)
        assert result == {"id": 1}

    def test_dict_fallback(self):
        adapter = TianyanchaResponseAdapter()
        data = {"name": "company"}
        result = adapter.extract_primary_dict(data)
        assert result == {"name": "company"}

    def test_list_input(self):
        adapter = TianyanchaResponseAdapter()
        data = [{"id": 1}, {"id": 2}]
        result = adapter.extract_primary_dict(data)
        assert result == {"id": 1}

    def test_list_empty(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter.extract_primary_dict([]) == {}

    def test_non_dict_non_list(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter.extract_primary_dict("string") == {}


class TestParseSearchCompaniesMarkdown:
    def test_empty_markdown(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter.parse_search_companies_markdown("") == []

    def test_no_header(self):
        adapter = TianyanchaResponseAdapter()
        result = adapter.parse_search_companies_markdown("企业搜索结果\n一些文本")
        assert result == []

    def test_complete_parsing(self):
        adapter = TianyanchaResponseAdapter()
        md = (
            "企业搜索结果\n\n"
            "## 1. 测试公司A\n"
            "| **企业ID** | 12345 |\n"
            "| **法定代表人** | 张三 |\n"
            "| **经营状态** | 存续 |\n"
            "| **成立时间** | 2020-01-01 |\n"
            "| **注册资本** | 100万 |\n"
            "| **联系电话** | 010-12345678 |\n"
        )
        result = adapter.parse_search_companies_markdown(md)
        assert len(result) == 1
        assert result[0]["company_id"] == "12345"
        assert result[0]["company_name"] == "测试公司A"
        assert result[0]["legal_person"] == "张三"

    def test_multiple_companies(self):
        adapter = TianyanchaResponseAdapter()
        md = (
            "企业搜索结果\n\n"
            "## 1. 公司A\n"
            "| **企业ID** | 111 |\n"
            "## 2. 公司B\n"
            "| **企业ID** | 222 |\n"
        )
        result = adapter.parse_search_companies_markdown(md)
        assert len(result) == 2

    def test_empty_value_skipped(self):
        adapter = TianyanchaResponseAdapter()
        md = (
            "企业搜索结果\n\n"
            "## 1. 公司A\n"
            "| **企业ID** | |\n"
            "| **法定代表人** | 张三 |\n"
        )
        result = adapter.parse_search_companies_markdown(md)
        assert len(result) == 1
        assert result[0]["company_id"] == ""
        assert result[0]["legal_person"] == "张三"


class TestParseCompanyProfileMarkdown:
    def test_empty(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter.parse_company_profile_markdown("") == {}

    def test_no_meaningful_fields(self):
        adapter = TianyanchaResponseAdapter()
        result = adapter.parse_company_profile_markdown("random text with no structure")
        assert result == {}

    def test_complete_profile(self):
        adapter = TianyanchaResponseAdapter()
        md = (
            "# \U0001f3e2 测试公司\n\n"
            "| **企业ID** | 12345 |\n"
            "| **统一社会信用代码** | 91110000MA12345 |\n"
            "| **法定代表人** | 张三 |\n"
            "| **经营状态** | 存续 |\n"
            "| **成立日期** | 2020-01-01 |\n"
            "| **注册资本** | 100万人民币 |\n"
            "| **注册地址** | 北京市朝阳区 |\n"
            "| **联系电话** | 010-12345678 |\n"
            "\n## \U0001f4c4 经营范围\n技术开发；技术咨询\n\n**关于企业更多信息\n"
        )
        result = adapter.parse_company_profile_markdown(md)
        assert result["company_name"] == "测试公司"
        assert result["unified_social_credit_code"] == "91110000MA12345"
        assert result["business_scope"] == "技术开发；技术咨询"

    def test_dict_with_result_key(self):
        adapter = TianyanchaResponseAdapter()
        md = "# \U0001f3e2 公司名\n| **企业ID** | 123 |\n| **法定代表人** | 李四 |\n"
        result = adapter.parse_company_profile_markdown({"result": md})
        assert result["company_name"] == "公司名"

    def test_dict_with_text_key(self):
        adapter = TianyanchaResponseAdapter()
        md = "# \U0001f3e2 公司名\n| **法定代表人** | 李四 |\n"
        result = adapter.parse_company_profile_markdown({"text": md})
        assert result["legal_person"] == "李四"


class TestCleanMarkdownValue:
    def test_bold_removal(self):
        result = TianyanchaResponseAdapter._clean_markdown_value("**hello**")
        assert result == "hello"

    def test_backtick_removal(self):
        result = TianyanchaResponseAdapter._clean_markdown_value("`code`")
        assert result == "code"

    def test_whitespace_normalization(self):
        result = TianyanchaResponseAdapter._clean_markdown_value("  hello   world  ")
        assert result == "hello world"

    def test_tab_replacement(self):
        result = TianyanchaResponseAdapter._clean_markdown_value("hello\tworld")
        assert result == "hello world"

    def test_empty(self):
        result = TianyanchaResponseAdapter._clean_markdown_value(None)
        assert result == ""


class TestNormalizeCompanySummary:
    def test_standard_keys(self):
        adapter = TianyanchaResponseAdapter()
        item = {
            "company_id": "123",
            "company_name": "TestCo",
            "legalPersonName": "张三",
            "regStatus": "存续",
            "estiblishTime": "2020-01-01",
            "regCapital": "100万",
            "phone": "010-123",
        }
        result = adapter.normalize_company_summary(item)
        assert result["company_id"] == "123"
        assert result["company_name"] == "TestCo"

    def test_alternate_keys(self):
        adapter = TianyanchaResponseAdapter()
        item = {
            "companyId": "456",
            "name": "AltCo",
            "legalRepresentative": "李四",
            "status": "注销",
            "foundedDate": "2019-01-01",
            "capital": "200万",
            "tel": "021-456",
        }
        result = adapter.normalize_company_summary(item)
        assert result["company_id"] == "456"
        assert result["company_name"] == "AltCo"
        assert result["phone"] == "021-456"


class TestNormalizeCompanyProfile:
    def test_standard_keys(self):
        adapter = TianyanchaResponseAdapter()
        item = {
            "creditCode": "9111",
            "regLocation": "北京市",
            "businessScope": "技术",
        }
        result = adapter.normalize_company_profile(item)
        assert result["unified_social_credit_code"] == "9111"
        assert result["address"] == "北京市"
        assert result["business_scope"] == "技术"


class TestNormalizeRiskItem:
    def test_standard_keys(self):
        adapter = TianyanchaResponseAdapter()
        item = {
            "riskType": "诉讼",
            "title": "合同纠纷",
            "level": "高",
            "amount": "10万",
            "date": "2024-01-01",
            "source": "北京法院",
        }
        result = adapter.normalize_risk_item(item, fallback_risk_type="未知")
        assert result["risk_type"] == "诉讼"
        assert result["title"] == "合同纠纷"
        assert result["level"] == "高"

    def test_fallback_risk_type(self):
        adapter = TianyanchaResponseAdapter()
        item = {"title": "test"}
        result = adapter.normalize_risk_item(item, fallback_risk_type="默认风险")
        assert result["risk_type"] == "默认风险"


class TestNormalizeShareholderItem:
    def test_standard_keys(self):
        adapter = TianyanchaResponseAdapter()
        item = {
            "name": "股东A",
            "subConAm": "100万",
            "holdRatio": "30%",
            "conDate": "2020-01-01",
            "source": "工商",
        }
        result = adapter.normalize_shareholder_item(item)
        assert result["name"] == "股东A"
        assert result["amount"] == "100万"
        assert result["ratio"] == "30%"


class TestNormalizePersonnelItem:
    def test_standard_keys(self):
        adapter = TianyanchaResponseAdapter()
        item = {
            "hcgid": "abc123",
            "name": "张三",
            "position": "总经理",
            "education": "博士",
            "source": "tyc",
        }
        result = adapter.normalize_personnel_item(item)
        assert result["hcgid"] == "abc123"
        assert result["name"] == "张三"


class TestNormalizePersonProfile:
    def test_standard_keys(self):
        adapter = TianyanchaResponseAdapter()
        item = {
            "hcgid": "abc",
            "name": "张三",
            "position": "CEO",
            "intro": "简介",
            "resume": "履历",
        }
        result = adapter.normalize_person_profile(item)
        assert result["intro"] == "简介"
        assert result["resume"] == "履历"


class TestNormalizeBiddingItem:
    def test_standard_keys(self):
        adapter = TianyanchaResponseAdapter()
        item = {
            "title": "招标公告",
            "projectName": "某项目",
            "role": "中标人",
            "amount": "500万",
            "date": "2024-01-01",
            "region": "北京",
            "source": "招标网",
            "url": "http://example.com",
        }
        result = adapter.normalize_bidding_item(item)
        assert result["title"] == "招标公告"
        assert result["project_name"] == "某项目"
        assert result["link"] == "http://example.com"


class TestExtractMarkdownResult:
    def test_string_input(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result("hello") == "hello"

    def test_dict_with_result(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result({"result": "text"}) == "text"

    def test_dict_with_text(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result({"text": "content"}) == "content"

    def test_dict_with_message(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result({"message": "msg"}) == "msg"

    def test_empty_dict(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result({}) == ""

    def test_int_input(self):
        adapter = TianyanchaResponseAdapter()
        assert adapter._extract_markdown_result(42) == ""
