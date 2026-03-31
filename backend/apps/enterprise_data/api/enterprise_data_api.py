"""企业数据查询 API。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth
from apps.enterprise_data.schemas import EnterpriseProvidersOut, EnterpriseQueryOut
from apps.enterprise_data.services import EnterpriseDataService

RiskType = Literal["周边风险", "预警提醒", "自身风险", "历史风险"]

router = Router(tags=["企业数据查询"], auth=JWTOrSessionAuth())


def _service() -> EnterpriseDataService:
    return EnterpriseDataService()


@router.get("/providers", response=EnterpriseProvidersOut)
def list_providers(request, include_tools: bool = False) -> EnterpriseProvidersOut:
    return EnterpriseProvidersOut(**_service().list_providers(include_tools=include_tools))


@router.get("/companies/search", response=EnterpriseQueryOut)
def search_companies(
    request,
    keyword: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    return EnterpriseQueryOut(
        **_service().search_companies(keyword=keyword, provider=provider, include_raw=include_raw)
    )


@router.get("/companies/{company_id}", response=EnterpriseQueryOut)
def get_company_profile(
    request,
    company_id: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    return EnterpriseQueryOut(
        **_service().get_company_profile(company_id=company_id, provider=provider, include_raw=include_raw)
    )


@router.get("/companies/{company_id}/risks", response=EnterpriseQueryOut)
def get_company_risks(
    request,
    company_id: str,
    risk_type: RiskType = "自身风险",
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    return EnterpriseQueryOut(
        **_service().get_company_risks(
            company_id=company_id,
            risk_type=risk_type,
            provider=provider,
            include_raw=include_raw,
        )
    )


@router.get("/companies/{company_id}/shareholders", response=EnterpriseQueryOut)
def get_company_shareholders(
    request,
    company_id: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    return EnterpriseQueryOut(
        **_service().get_company_shareholders(company_id=company_id, provider=provider, include_raw=include_raw)
    )


@router.get("/companies/{company_id}/personnel", response=EnterpriseQueryOut)
def get_company_personnel(
    request,
    company_id: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    return EnterpriseQueryOut(
        **_service().get_company_personnel(company_id=company_id, provider=provider, include_raw=include_raw)
    )


@router.get("/personnel/{hcgid}", response=EnterpriseQueryOut)
def get_person_profile(
    request,
    hcgid: str,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    return EnterpriseQueryOut(**_service().get_person_profile(hcgid=hcgid, provider=provider, include_raw=include_raw))


@router.get("/biddings/search", response=EnterpriseQueryOut)
def search_bidding_info(
    request,
    keyword: str,
    search_type: int = 1,
    bid_type: int = 4,
    start_date: date | None = None,
    end_date: date | None = None,
    provider: str | None = None,
    include_raw: bool = False,
) -> EnterpriseQueryOut:
    return EnterpriseQueryOut(
        **_service().search_bidding_info(
            keyword=keyword,
            search_type=search_type,
            bid_type=bid_type,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
            include_raw=include_raw,
        )
    )
