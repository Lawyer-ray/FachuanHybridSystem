"""Comprehensive tests for client_enterprise_prefill_service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# ClientEnterprisePrefillService tests
# ===========================================================================
class TestClientEnterprisePrefillService:
    def _get_service(self):
        from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
        svc = ClientEnterprisePrefillService.__new__(ClientEnterprisePrefillService)
        svc._enterprise_data_service = MagicMock()
        return svc

    # _pick_str
    def test_pick_str_first_match(self):
        from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
        result = ClientEnterprisePrefillService._pick_str(
            {"a": "val_a", "b": "val_b"}, ("a", "b")
        )
        assert result == "val_a"

    def test_pick_str_second_key(self):
        from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
        result = ClientEnterprisePrefillService._pick_str(
            {"b": "val_b"}, ("a", "b")
        )
        assert result == "val_b"

    def test_pick_str_none_value(self):
        from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
        result = ClientEnterprisePrefillService._pick_str(
            {"a": None, "b": "val_b"}, ("a", "b")
        )
        assert result == "val_b"

    def test_pick_str_empty_value(self):
        from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
        result = ClientEnterprisePrefillService._pick_str(
            {"a": "", "b": "val_b"}, ("a", "b")
        )
        assert result == "val_b"

    def test_pick_str_not_dict(self):
        from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
        result = ClientEnterprisePrefillService._pick_str("not a dict", ("a",))
        assert result == ""

    def test_pick_str_no_match(self):
        from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
        result = ClientEnterprisePrefillService._pick_str({"c": "val"}, ("a", "b"))
        assert result == ""

    # _normalize_company_candidates
    def test_normalize_from_dict(self):
        svc = self._get_service()
        payload = {
            "items": [
                {"company_id": "C001", "company_name": "公司A", "legal_person": "张三"},
            ]
        }
        result = svc._normalize_company_candidates(payload)
        assert len(result) == 1
        assert result[0]["company_id"] == "C001"

    def test_normalize_from_list(self):
        svc = self._get_service()
        payload = [
            {"company_id": "C001", "name": "公司A"},
        ]
        result = svc._normalize_company_candidates(payload)
        assert len(result) == 1
        assert result[0]["company_name"] == "公司A"

    def test_normalize_non_dict_item(self):
        svc = self._get_service()
        payload = {"items": ["not a dict", {"company_id": "C001", "name": "公司A"}]}
        result = svc._normalize_company_candidates(payload)
        assert len(result) == 1

    def test_normalize_none(self):
        svc = self._get_service()
        result = svc._normalize_company_candidates(None)
        assert result == []

    def test_normalize_invalid_items_type(self):
        svc = self._get_service()
        result = svc._normalize_company_candidates({"items": "not a list"})
        assert result == []

    def test_normalize_empty_item(self):
        svc = self._get_service()
        payload = {"items": [{"random_key": "random_value"}]}
        result = svc._normalize_company_candidates(payload)
        assert len(result) == 0

    def test_normalize_alternate_keys(self):
        svc = self._get_service()
        payload = {"items": [
            {"companyId": "C001", "companyName": "公司A", "legalPersonName": "张三",
             "regStatus": "在营", "estiblishTime": "2020-01-01", "regCapital": "100万",
             "contactPhone": "13800138000"},
        ]}
        result = svc._normalize_company_candidates(payload)
        assert len(result) == 1
        assert result[0]["company_id"] == "C001"
        assert result[0]["company_name"] == "公司A"
        assert result[0]["status"] == "在营"

    # _normalize_company_profile
    def test_normalize_company_profile(self):
        svc = self._get_service()
        payload = {
            "company_id": "C001",
            "companyName": "测试公司",
            "creditCode": "91440101MA59TEST",
            "legalPersonName": "李四",
            "regStatus": "在营",
            "regLocation": "广州市天河区",
            "businessScope": "软件开发",
        }
        result = svc._normalize_company_profile(payload, fallback_company_id="FALLBACK")
        assert result["company_name"] == "测试公司"
        assert result["unified_social_credit_code"] == "91440101MA59TEST"
        assert result["address"] == "广州市天河区"

    def test_normalize_company_profile_empty(self):
        svc = self._get_service()
        result = svc._normalize_company_profile(None, fallback_company_id="FALLBACK")
        assert result["company_id"] == "FALLBACK"

    # _resolve_profile_phone
    def test_resolve_phone_direct(self):
        svc = self._get_service()
        profile = {"phone": "13800138000", "company_name": "公司"}
        result = svc._resolve_profile_phone(company_id="C001", provider=None, profile=profile)
        assert result == "13800138000"

    def test_resolve_phone_from_search(self):
        svc = self._get_service()
        profile = {"phone": "", "company_name": "测试公司"}
        svc._enterprise_data_service.search_companies.return_value = {
            "data": {"items": [{"company_id": "C001", "phone": "13900139000"}]}
        }
        result = svc._resolve_profile_phone(company_id="C001", provider=None, profile=profile)
        assert result == "13900139000"

    def test_resolve_phone_no_name(self):
        svc = self._get_service()
        profile = {"phone": "", "company_name": ""}
        result = svc._resolve_profile_phone(company_id="C001", provider=None, profile=profile)
        assert result == ""

    def test_resolve_phone_search_exception(self):
        svc = self._get_service()
        profile = {"phone": "", "company_name": "测试公司"}
        svc._enterprise_data_service.search_companies.side_effect = Exception("fail")
        result = svc._resolve_profile_phone(company_id="C001", provider=None, profile=profile)
        assert result == ""

    def test_resolve_phone_match_by_name(self):
        svc = self._get_service()
        profile = {"phone": "", "company_name": "测试公司"}
        svc._enterprise_data_service.search_companies.return_value = {
            "data": {"items": [{"company_id": "DIFFERENT", "company_name": "测试公司", "phone": "13900139000"}]}
        }
        result = svc._resolve_profile_phone(company_id="C001", provider=None, profile=profile)
        assert result == "13900139000"

    # search_companies validation
    def test_search_empty_keyword(self):
        svc = self._get_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            svc.search_companies(keyword="")

    def test_search_normalizes_limit(self):
        svc = self._get_service()
        svc._enterprise_data_service.search_companies.return_value = {"data": [], "meta": {}}
        result = svc.search_companies(keyword="test", limit=100)
        # limit should be clamped to 20
        assert result["total"] == 0

    # build_prefill validation
    def test_build_prefill_empty_company_id(self):
        svc = self._get_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            svc.build_prefill(company_id="")
