from __future__ import annotations

import pytest

from apps.client.models import Client
from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService


class _FakeEnterpriseDataService:
    def search_companies(self, *, keyword: str, provider: str | None = None, include_raw: bool = False) -> dict:
        return {
            "meta": {"provider": provider or "tianyancha"},
            "data": {
                "items": [
                    {
                        "company_id": "1001",
                        "company_name": "腾讯科技（深圳）有限公司",
                        "legal_person": "马化腾",
                        "status": "存续",
                        "establish_date": "1998-11-11",
                        "registered_capital": "6500万人民币",
                        "phone": "0755-86013388",
                    },
                    {"company_id": "1002", "company_name": "腾讯云计算有限公司"},
                ]
            },
        }

    def get_company_profile(self, *, company_id: str, provider: str | None = None, include_raw: bool = False) -> dict:
        return {
            "meta": {"provider": provider or "tianyancha"},
            "data": {
                "company_id": company_id,
                "company_name": "腾讯科技（深圳）有限公司",
                "unified_social_credit_code": "91440300708461136T",
                "legal_person": "马化腾",
                "status": "存续",
                "establish_date": "1998-11-11",
                "registered_capital": "6500万人民币",
                "address": "深圳市南山区",
                "business_scope": "技术开发",
            },
        }


def test_search_companies_returns_normalized_candidates_with_limit() -> None:
    service = ClientEnterprisePrefillService(enterprise_data_service=_FakeEnterpriseDataService())

    result = service.search_companies(keyword="腾讯", provider="tianyancha", limit=1)

    assert result["provider"] == "tianyancha"
    assert result["total"] == 1
    assert result["items"][0]["company_id"] == "1001"
    assert result["items"][0]["company_name"] == "腾讯科技（深圳）有限公司"
    assert result["items"][0]["phone"] == "0755-86013388"


@pytest.mark.django_db
def test_build_prefill_includes_existing_client_when_credit_code_exists() -> None:
    existing = Client.objects.create(
        name="腾讯历史当事人",
        client_type=Client.LEGAL,
        id_number="91440300708461136T",
        legal_representative="马化腾",
    )
    service = ClientEnterprisePrefillService(enterprise_data_service=_FakeEnterpriseDataService())

    result = service.build_prefill(company_id="1001", provider="tianyancha")

    assert result["prefill"]["client_type"] == "legal"
    assert result["prefill"]["name"] == "腾讯科技（深圳）有限公司"
    assert result["prefill"]["id_number"] == "91440300708461136T"
    assert result["prefill"]["phone"] == "0755-86013388"
    assert result["existing_client"] == {"id": existing.id, "name": existing.name}
