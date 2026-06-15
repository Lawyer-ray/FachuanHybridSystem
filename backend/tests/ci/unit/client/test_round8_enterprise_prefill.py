"""Tests for client_enterprise_prefill_service helper methods (no DB)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
from apps.core.exceptions import ValidationException


# ---------------------------------------------------------------------------
# _pick_str
# ---------------------------------------------------------------------------


class TestPickStr:
    def test_first_match(self):
        obj = {"name": "Test Co", "company_name": "Other"}
        assert ClientEnterprisePrefillService._pick_str(obj, ("name", "company_name")) == "Test Co"

    def test_second_match(self):
        obj = {"company_name": "Test Co"}
        assert ClientEnterprisePrefillService._pick_str(obj, ("name", "company_name")) == "Test Co"

    def test_empty_value_skipped(self):
        obj = {"name": "", "company_name": "Test Co"}
        assert ClientEnterprisePrefillService._pick_str(obj, ("name", "company_name")) == "Test Co"

    def test_none_value_skipped(self):
        obj = {"name": None, "company_name": "Test Co"}
        assert ClientEnterprisePrefillService._pick_str(obj, ("name", "company_name")) == "Test Co"

    def test_no_match(self):
        obj = {"key": "val"}
        assert ClientEnterprisePrefillService._pick_str(obj, ("name",)) == ""

    def test_not_dict(self):
        assert ClientEnterprisePrefillService._pick_str("string", ("name",)) == ""

    def test_whitespace_stripped(self):
        obj = {"name": "  Test Co  "}
        assert ClientEnterprisePrefillService._pick_str(obj, ("name",)) == "Test Co"


# ---------------------------------------------------------------------------
# _normalize_company_candidates
# ---------------------------------------------------------------------------


class TestNormalizeCompanyCandidates:
    def setup_method(self):
        self.svc = ClientEnterprisePrefillService.__new__(ClientEnterprisePrefillService)
        self.svc._enterprise_data_service = MagicMock()

    def test_list_input(self):
        items = [
            {"company_id": "123", "company_name": "Test Co"},
            {"company_id": "456", "company_name": "Other Co"},
        ]
        result = self.svc._normalize_company_candidates(items)
        assert len(result) == 2
        assert result[0]["company_id"] == "123"

    def test_dict_input_with_items(self):
        payload = {"items": [{"company_id": "123", "company_name": "Test Co"}]}
        result = self.svc._normalize_company_candidates(payload)
        assert len(result) == 1

    def test_empty_input(self):
        assert self.svc._normalize_company_candidates(None) == []
        assert self.svc._normalize_company_candidates("string") == []

    def test_items_not_list(self):
        payload = {"items": "not_a_list"}
        assert self.svc._normalize_company_candidates(payload) == []

    def test_non_dict_items_filtered(self):
        items = ["string", 123, None]
        assert self.svc._normalize_company_candidates(items) == []

    def test_no_company_id_or_name_filtered(self):
        items = [{"random_field": "value"}]
        assert self.svc._normalize_company_candidates(items) == []

    def test_alternate_field_names(self):
        items = [{"companyId": "123", "name": "Test Co"}]
        result = self.svc._normalize_company_candidates(items)
        assert len(result) == 1
        assert result[0]["company_id"] == "123"
        assert result[0]["company_name"] == "Test Co"


# ---------------------------------------------------------------------------
# _normalize_company_profile
# ---------------------------------------------------------------------------


class TestNormalizeCompanyProfile:
    def setup_method(self):
        self.svc = ClientEnterprisePrefillService.__new__(ClientEnterprisePrefillService)
        self.svc._enterprise_data_service = MagicMock()

    def test_normal(self):
        payload = {
            "company_id": "123",
            "company_name": "Test Co",
            "legalPersonName": "张三",
            "address": "广州市",
        }
        result = self.svc._normalize_company_profile(payload, fallback_company_id="fallback")
        assert result["company_id"] == "123"
        assert result["company_name"] == "Test Co"
        assert result["legal_person"] == "张三"

    def test_empty_payload(self):
        result = self.svc._normalize_company_profile({}, fallback_company_id="fallback")
        assert result["company_id"] == "fallback"

    def test_non_dict_payload(self):
        result = self.svc._normalize_company_profile(None, fallback_company_id="fallback")
        assert result["company_id"] == "fallback"


# ---------------------------------------------------------------------------
# search_companies
# ---------------------------------------------------------------------------


class TestSearchCompanies:
    def test_empty_keyword(self):
        mock_eds = MagicMock()
        svc = ClientEnterprisePrefillService(enterprise_data_service=mock_eds)
        with pytest.raises(ValidationException):
            svc.search_companies(keyword="")

    def test_normal(self):
        mock_eds = MagicMock()
        mock_eds.search_companies.return_value = {
            "data": [{"company_id": "123", "company_name": "Test Co"}],
            "meta": {"provider": "qichacha"},
        }
        svc = ClientEnterprisePrefillService(enterprise_data_service=mock_eds)
        result = svc.search_companies(keyword="Test")
        assert result["keyword"] == "Test"
        assert result["provider"] == "qichacha"
        assert len(result["items"]) == 1

    def test_limit(self):
        mock_eds = MagicMock()
        mock_eds.search_companies.return_value = {
            "data": [{"company_id": str(i), "company_name": f"Co{i}"} for i in range(10)],
            "meta": {},
        }
        svc = ClientEnterprisePrefillService(enterprise_data_service=mock_eds)
        result = svc.search_companies(keyword="Co", limit=3)
        assert len(result["items"]) == 3


# ---------------------------------------------------------------------------
# _resolve_profile_phone
# ---------------------------------------------------------------------------


class TestResolveProfilePhone:
    def test_direct_phone(self):
        mock_eds = MagicMock()
        svc = ClientEnterprisePrefillService(enterprise_data_service=mock_eds)
        result = svc._resolve_profile_phone(
            company_id="123",
            provider="qichacha",
            profile={"phone": "13800138000"},
        )
        assert result == "13800138000"

    def test_no_phone_empty_company(self):
        mock_eds = MagicMock()
        svc = ClientEnterprisePrefillService(enterprise_data_service=mock_eds)
        result = svc._resolve_profile_phone(
            company_id="123",
            provider="qichacha",
            profile={"phone": "", "company_name": ""},
        )
        assert result == ""

    def test_lookup_from_search(self):
        mock_eds = MagicMock()
        mock_eds.search_companies.return_value = {
            "data": [{"company_id": "123", "company_name": "Test Co", "phone": "139"}],
            "meta": {},
        }
        svc = ClientEnterprisePrefillService(enterprise_data_service=mock_eds)
        result = svc._resolve_profile_phone(
            company_id="123",
            provider="qichacha",
            profile={"phone": "", "company_name": "Test Co"},
        )
        assert result == "139"

    def test_lookup_from_search_exception(self):
        mock_eds = MagicMock()
        mock_eds.search_companies.side_effect = Exception("API error")
        svc = ClientEnterprisePrefillService(enterprise_data_service=mock_eds)
        result = svc._resolve_profile_phone(
            company_id="123",
            provider="qichacha",
            profile={"phone": "", "company_name": "Test Co"},
        )
        assert result == ""
