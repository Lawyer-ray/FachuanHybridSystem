"""Tests for enterprise_data/services/providers/adapters/qichacha_adapter.py (168 lines, 0% coverage).

Covers: pick_str, normalize_company_summary, normalize_company_profile,
normalize_risk_item, normalize_shareholder_item, normalize_personnel_item,
normalize_person_profile, normalize_bidding_item.
"""
from __future__ import annotations

import pytest

from apps.enterprise_data.services.providers.adapters.qichacha_adapter import (
    QichachaResponseAdapter,
)


class TestPickStr:
    def setup_method(self):
        self.adapter = QichachaResponseAdapter()

    def test_picks_first_match(self):
        obj = {"a": "value_a", "b": "value_b"}
        assert self.adapter.pick_str(obj, ("a", "b")) == "value_a"

    def test_picks_second_match(self):
        obj = {"a": None, "b": "value_b"}
        assert self.adapter.pick_str(obj, ("a", "b")) == "value_b"

    def test_strips_whitespace(self):
        obj = {"a": "  hello  "}
        assert self.adapter.pick_str(obj, ("a",)) == "hello"

    def test_skips_empty_string(self):
        obj = {"a": "", "b": "real"}
        assert self.adapter.pick_str(obj, ("a", "b")) == "real"

    def test_converts_int_to_string(self):
        obj = {"a": 123}
        assert self.adapter.pick_str(obj, ("a",)) == "123"

    def test_returns_empty_when_no_match(self):
        obj = {"x": None}
        assert self.adapter.pick_str(obj, ("a", "b")) == ""

    def test_returns_empty_for_empty_keys(self):
        obj = {"a": "val"}
        assert self.adapter.pick_str(obj, ()) == ""


class TestNormalizeCompanySummary:
    def setup_method(self):
        self.adapter = QichachaResponseAdapter()

    def test_with_all_fields(self):
        item = {
            "company_id": "91310000",
            "company_name": "测试公司",
            "legalPersonName": "张三",
            "regStatus": "存续",
            "startDate": "2020-01-01",
            "regCapital": "100万",
            "phone": "13800138000",
        }
        result = self.adapter.normalize_company_summary(item)
        assert result["company_id"] == "91310000"
        assert result["company_name"] == "测试公司"
        assert result["legal_person"] == "张三"
        assert result["status"] == "存续"
        assert result["establish_date"] == "2020-01-01"
        assert result["registered_capital"] == "100万"
        assert result["phone"] == "13800138000"

    def test_with_alternative_keys(self):
        item = {
            "companyId": "alt_id",
            "entName": "公司名",
            "operName": "李四",
            "openStatus": "在营",
            "estiblishTime": "2019-05-10",
        }
        result = self.adapter.normalize_company_summary(item)
        assert result["company_id"] == "alt_id"
        assert result["company_name"] == "公司名"
        assert result["legal_person"] == "李四"

    def test_empty_item(self):
        result = self.adapter.normalize_company_summary({})
        assert all(v == "" for v in result.values())


class TestNormalizeCompanyProfile:
    def setup_method(self):
        self.adapter = QichachaResponseAdapter()

    def test_with_fields(self):
        item = {
            "creditCode": "91310000ABC",
            "name": "测试公司",
            "address": "北京市朝阳区",
            "businessScope": "技术开发",
        }
        result = self.adapter.normalize_company_profile(item)
        assert result["unified_social_credit_code"] == "91310000ABC"
        assert result["company_name"] == "测试公司"
        assert result["address"] == "北京市朝阳区"
        assert result["business_scope"] == "技术开发"

    def test_empty(self):
        result = self.adapter.normalize_company_profile({})
        assert all(v == "" for v in result.values())


class TestNormalizeRiskItem:
    def setup_method(self):
        self.adapter = QichachaResponseAdapter()

    def test_with_fields(self):
        item = {
            "riskType": "司法风险",
            "title": "被起诉",
            "level": "高",
            "amount": "100万",
            "date": "2026-01-01",
            "source": "法院",
        }
        result = self.adapter.normalize_risk_item(item, fallback_risk_type="其他")
        assert result["risk_type"] == "司法风险"
        assert result["title"] == "被起诉"
        assert result["level"] == "高"

    def test_fallback_risk_type(self):
        result = self.adapter.normalize_risk_item({}, fallback_risk_type="默认类型")
        assert result["risk_type"] == "默认类型"

    def test_with_alt_keys(self):
        item = {
            "type": "经营风险",
            "riskTitle": "行政处罚",
            "riskLevel": "中",
            "publishDate": "2026-06-01",
        }
        result = self.adapter.normalize_risk_item(item, fallback_risk_type="其他")
        assert result["risk_type"] == "经营风险"
        assert result["title"] == "行政处罚"


class TestNormalizeShareholderItem:
    def setup_method(self):
        self.adapter = QichachaResponseAdapter()

    def test_with_fields(self):
        item = {
            "name": "股东A",
            "subConAm": "500万",
            "holdRatio": "30%",
            "conDate": "2020-01-01",
        }
        result = self.adapter.normalize_shareholder_item(item)
        assert result["name"] == "股东A"
        assert result["amount"] == "500万"
        assert result["ratio"] == "30%"
        assert result["contribution_date"] == "2020-01-01"


class TestNormalizePersonnelItem:
    def setup_method(self):
        self.adapter = QichachaResponseAdapter()

    def test_with_fields(self):
        item = {
            "name": "王五",
            "position": "总经理",
            "education": "本科",
        }
        result = self.adapter.normalize_personnel_item(item)
        assert result["name"] == "王五"
        assert result["position"] == "总经理"
        assert result["education"] == "本科"


class TestNormalizePersonProfile:
    def setup_method(self):
        self.adapter = QichachaResponseAdapter()

    def test_with_fields(self):
        item = {
            "name": "赵六",
            "position": "董事",
            "intro": "资深律师",
            "resume": "10年从业经验",
        }
        result = self.adapter.normalize_person_profile(item)
        assert result["name"] == "赵六"
        assert result["intro"] == "资深律师"
        assert result["resume"] == "10年从业经验"


class TestNormalizeBiddingItem:
    def setup_method(self):
        self.adapter = QichachaResponseAdapter()

    def test_with_fields(self):
        item = {
            "title": "招标公告",
            "projectName": "项目A",
            "role": "投标方",
            "amount": "200万",
            "date": "2026-01-01",
            "region": "上海",
            "url": "https://example.com",
        }
        result = self.adapter.normalize_bidding_item(item)
        assert result["title"] == "招标公告"
        assert result["project_name"] == "项目A"
        assert result["amount"] == "200万"
        assert result["link"] == "https://example.com"
