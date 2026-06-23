"""企业数据查询 API。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from asgiref.sync import sync_to_async
from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth
from apps.enterprise_data.schemas import EnterpriseProvidersOut, EnterpriseQueryOut
from apps.enterprise_data.services import EnterpriseDataService

RiskType = Literal["周边风险", "预警提醒", "自身风险", "历史风险"]

router = Router(tags=["企业数据查询"], auth=JWTOrSessionAuth())


def _service() -> EnterpriseDataService:
    return EnterpriseDataService()


@router.get("/providers", response=EnterpriseProvidersOut)
def list_providers(request: Any, include_tools: bool = False) -> EnterpriseProvidersOut:  # pragma: no cover
    return EnterpriseProvidersOut(**_service().list_providers(include_tools=include_tools))  # type: ignore[arg-type]


@router.get("/companies/search", response=EnterpriseQueryOut)
async def search_companies(  # pragma: no cover
    request: Any,
    keyword: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    result = await sync_to_async(_service().search_companies, thread_sensitive=False)(
        keyword=keyword, provider=provider, include_raw=include_raw
    )
    return EnterpriseQueryOut(**result)


@router.get("/companies/{company_id}", response=EnterpriseQueryOut)
async def get_company_profile(  # pragma: no cover
    request: Any,
    company_id: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    result = await sync_to_async(_service().get_company_profile, thread_sensitive=False)(
        company_id=company_id, provider=provider, include_raw=include_raw
    )
    return EnterpriseQueryOut(**result)


@router.get("/companies/{company_id}/risks", response=EnterpriseQueryOut)
async def get_company_risks(  # pragma: no cover
    request: Any,
    company_id: str,
    risk_type: RiskType = "自身风险",
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    result = await sync_to_async(_service().get_company_risks, thread_sensitive=False)(
        company_id=company_id,
        risk_type=risk_type,
        provider=provider,
        include_raw=include_raw,
    )
    return EnterpriseQueryOut(**result)


@router.get("/companies/{company_id}/shareholders", response=EnterpriseQueryOut)
async def get_company_shareholders(  # pragma: no cover
    request: Any,
    company_id: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    result = await sync_to_async(_service().get_company_shareholders, thread_sensitive=False)(
        company_id=company_id, provider=provider, include_raw=include_raw
    )
    return EnterpriseQueryOut(**result)


@router.get("/companies/{company_id}/personnel", response=EnterpriseQueryOut)
async def get_company_personnel(  # pragma: no cover
    request: Any,
    company_id: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    result = await sync_to_async(_service().get_company_personnel, thread_sensitive=False)(
        company_id=company_id, provider=provider, include_raw=include_raw
    )
    return EnterpriseQueryOut(**result)


@router.get("/personnel/{hcgid}", response=EnterpriseQueryOut)
async def get_person_profile(  # pragma: no cover
    request: Any,
    hcgid: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    result = await sync_to_async(_service().get_person_profile, thread_sensitive=False)(
        hcgid=hcgid, provider=provider, include_raw=include_raw
    )
    return EnterpriseQueryOut(**result)


@router.get("/biddings/search", response=EnterpriseQueryOut)
async def search_bidding_info(  # pragma: no cover
    request: Any,
    keyword: str,
    search_type: int = 1,
    bid_type: int = 4,
    start_date: date | None = None,
    end_date: date | None = None,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    result = await sync_to_async(_service().search_bidding_info, thread_sensitive=False)(
        keyword=keyword,
        search_type=search_type,
        bid_type=bid_type,
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        include_raw=include_raw,
    )
    return EnterpriseQueryOut(**result)
