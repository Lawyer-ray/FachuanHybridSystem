from __future__ import annotations

from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import TianyanchaResponseAdapter


def test_parse_search_companies_markdown_extracts_candidates() -> None:
    adapter = TianyanchaResponseAdapter()
    payload = {
        "result": (
            "# 🏢 企业搜索结果\n\n"
            "## 1. 深圳市腾讯计算机系统有限公司\n\n"
            "| 项目 | 详情 |\n"
            "|------|------|\n"
            "| **企业ID(company_id)** | 9519792 |\n"
            "| **法定代表人** | 马化腾 |\n"
            "| **成立时间** | 1998-11-11 00:00:00.0 |\n"
            "| **注册资本** | 6500万人民币 |\n"
            "| **经营状态** | 存续 |\n"
            "| **联系电话** | 0755-86013388 |\n"
        )
    }

    items = adapter.parse_search_companies_markdown(payload)

    assert len(items) == 1
    assert items[0]["company_id"] == "9519792"
    assert items[0]["company_name"] == "深圳市腾讯计算机系统有限公司"
    assert items[0]["legal_person"] == "马化腾"
    assert items[0]["phone"] == "0755-86013388"


def test_parse_company_profile_markdown_extracts_profile() -> None:
    adapter = TianyanchaResponseAdapter()
    payload = {
        "result": (
            "# 🏢 深圳市腾讯计算机系统有限公司\n\n"
            "## 📋 基本信息\n\n"
            "| 项目 | 详情 |\n"
            "|------|------|\n"
            "| **企业ID** | 9519792 |\n"
            "| **法定代表人** | 马化腾 |\n"
            "| **经营状态** | 存续 |\n"
            "| **注册资本** | 6500万人民币 |\n"
            "| **成立日期** | 1998-11-10 |\n"
            "| **统一社会信用代码** | 91440300708461136T |\n"
            "| **注册地址** | 深圳市南山区粤海街道麻岭社区科技中一路腾讯大厦35层 |\n\n"
            "| **联系电话** | 0755-86013388 |\n\n"
            "## 📄 经营范围\n\n"
            "计算机软、硬件的设计、技术开发、销售。\n"
        )
    }

    profile = adapter.parse_company_profile_markdown(payload)

    assert profile["company_id"] == "9519792"
    assert profile["company_name"] == "深圳市腾讯计算机系统有限公司"
    assert profile["unified_social_credit_code"] == "91440300708461136T"
    assert profile["legal_person"] == "马化腾"
    assert profile["phone"] == "0755-86013388"
    assert "技术开发" in profile["business_scope"]
