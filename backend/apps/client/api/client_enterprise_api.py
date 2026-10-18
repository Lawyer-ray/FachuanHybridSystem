"""Client 企业信息预填 API。"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router

from apps.client.schemas import EnterpriseClientPrefillOut, EnterpriseCompanySearchOut
from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService
from apps.core.exceptions import ValidationException

router = Router(tags=["客户管理"])


def _get_prefill_service() -> ClientEnterprisePrefillService:
    return ClientEnterprisePrefillService()


@router.get("/clients/enterprise/search", response=EnterpriseCompanySearchOut)
async def search_enterprise_companies(  # pragma: no cover
    request: Any,
    keyword: str,
    provider: str | None = None,
    limit: int = 8,
) -> EnterpriseCompanySearchOut:
    if limit < 1 or limit > 20:
        raise ValidationException(message="limit 必须在 1 到 20 之间", code="INVALID_LIMIT")
    service = _get_prefill_service()
    payload = await sync_to_async(service.search_companies)(keyword=keyword, provider=provider, limit=limit)
    return EnterpriseCompanySearchOut(**payload)


@router.get("/clients/enterprise/prefill", response=EnterpriseClientPrefillOut)
async def get_enterprise_prefill(  # pragma: no cover
    request: Any,
    company_id: str,
    provider: str | None = None,
) -> EnterpriseClientPrefillOut:
    # 安全审计（2026-10-19）：existing_client 按信用代码披露既有客户 id/name，
    # 仅对持 client.view_client 的调用方返回；预填本身（企业公开信息）保持全员可用
    from apps.client.services.client_access_policy import ClientAccessPolicy
    from apps.core.security.admin_access import get_request_user

    can_view_clients = await sync_to_async(ClientAccessPolicy().has_perm)(
        get_request_user(request), "client.view_client"
    )
    service = _get_prefill_service()
    payload = await sync_to_async(service.build_prefill)(
        company_id=company_id, provider=provider, include_existing=can_view_clients
    )
    return EnterpriseClientPrefillOut(**payload)
