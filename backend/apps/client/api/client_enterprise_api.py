"""Client 企业信息预填 API。"""

from __future__ import annotations

from typing import Any

from ninja import Router

from apps.client.schemas import EnterpriseClientPrefillOut, EnterpriseCompanySearchOut
from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
from apps.core.exceptions import ValidationException

router = Router(tags=["客户管理"])


def _get_prefill_service() -> ClientEnterprisePrefillService:
    return ClientEnterprisePrefillService()


@router.get("/clients/enterprise/search", response=EnterpriseCompanySearchOut)
def search_enterprise_companies(
    request: Any,
    keyword: str,
    provider: str | None = None,
    limit: int = 8,
) -> EnterpriseCompanySearchOut:
    if limit < 1 or limit > 20:
        raise ValidationException(message="limit 必须在 1 到 20 之间", code="INVALID_LIMIT")
    payload = _get_prefill_service().search_companies(keyword=keyword, provider=provider, limit=limit)
    return EnterpriseCompanySearchOut(**payload)


@router.get("/clients/enterprise/prefill", response=EnterpriseClientPrefillOut)
def get_enterprise_prefill(
    request: Any,
    company_id: str,
    provider: str | None = None,
) -> EnterpriseClientPrefillOut:
    payload = _get_prefill_service().build_prefill(company_id=company_id, provider=provider)
    return EnterpriseClientPrefillOut(**payload)
