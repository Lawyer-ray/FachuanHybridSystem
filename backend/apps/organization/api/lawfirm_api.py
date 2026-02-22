"""
律所 API
只负责请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from django.http import HttpRequest
from apps.organization.api._utils import get_request_user
from ninja import Router

from apps.organization.dtos import LawFirmCreateDTO, LawFirmUpdateDTO
from apps.organization.schemas import LawFirmIn, LawFirmOut, LawFirmUpdateIn
from apps.organization.services import LawFirmService

router = Router()

_lawfirm_service = LawFirmService()


@router.get("/lawfirms", response=list[LawFirmOut])
def list_lawfirms(request: HttpRequest) -> list[LawFirmOut]:
    """列表查询律所"""
    return list(_lawfirm_service.list_lawfirms(user=get_request_user(request)))


@router.get("/lawfirms/{law_firm_id}", response=LawFirmOut)
def get_lawfirm(request: HttpRequest, law_firm_id: int) -> LawFirmOut:
    """获取律所详情"""
    return _lawfirm_service.get_lawfirm(law_firm_id, get_request_user(request))


@router.post("/lawfirms", response=LawFirmOut)
def create_lawfirm(request: HttpRequest, payload: LawFirmIn) -> LawFirmOut:
    """创建律所"""
    dto = LawFirmCreateDTO(
        name=payload.name,
        address=payload.address,
        phone=payload.phone,
        social_credit_code=payload.social_credit_code,
    )
    return _lawfirm_service.create_lawfirm(data=dto, user=get_request_user(request))


@router.put("/lawfirms/{law_firm_id}", response=LawFirmOut)
def update_lawfirm(request: HttpRequest, law_firm_id: int, payload: LawFirmUpdateIn) -> LawFirmOut:
    """更新律所"""
    dto = LawFirmUpdateDTO(
        name=payload.name,
        address=payload.address,
        phone=payload.phone,
        social_credit_code=payload.social_credit_code,
    )
    return _lawfirm_service.update_lawfirm(lawfirm_id=law_firm_id, data=dto, user=get_request_user(request))


@router.delete("/lawfirms/{law_firm_id}")
def delete_lawfirm(request: HttpRequest, law_firm_id: int) -> dict[str, bool]:
    """删除律所"""
    _lawfirm_service.delete_lawfirm(law_firm_id, get_request_user(request))
    return {"success": True}
