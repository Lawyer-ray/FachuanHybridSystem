"""
案件当事人 API
符合四层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""
from typing import List, Optional
from ninja import Router

from ..schemas import CasePartyIn, CasePartyOut, CasePartyUpdate

router = Router()


def _get_case_party_service():
    """工厂函数：创建 CasePartyService 实例"""
    from ..services.case_party_service import CasePartyService
    return CasePartyService()


@router.get("/parties", response=List[CasePartyOut])
def list_parties(request, case_id: Optional[int] = None):
    service = _get_case_party_service()
    user = getattr(request, "user", None)
    return service.list_parties(case_id=case_id, user=user)


@router.post("/parties", response=CasePartyOut)
def create_party(request, payload: CasePartyIn):
    service = _get_case_party_service()
    user = getattr(request, "user", None)
    return service.create_party(
        case_id=payload.case_id,
        client_id=payload.client_id,
        legal_status=payload.legal_status,
        user=user
    )


@router.get("/parties/{party_id}", response=CasePartyOut)
def get_party(request, party_id: int):
    service = _get_case_party_service()
    user = getattr(request, "user", None)
    return service.get_party(party_id=party_id, user=user)


@router.put("/parties/{party_id}", response=CasePartyOut)
def update_party(request, party_id: int, payload: CasePartyUpdate):
    service = _get_case_party_service()
    user = getattr(request, "user", None)
    data = payload.dict(exclude_unset=True)
    return service.update_party(party_id=party_id, data=data, user=user)


@router.delete("/parties/{party_id}")
def delete_party(request, party_id: int):
    service = _get_case_party_service()
    user = getattr(request, "user", None)
    return service.delete_party(party_id=party_id, user=user)
