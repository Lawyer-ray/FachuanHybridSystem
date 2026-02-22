"""
律所 API
只负责请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Router

from apps.organization.dtos import LawFirmCreateDTO, LawFirmUpdateDTO
from apps.organization.schemas import LawFirmIn, LawFirmOut, LawFirmUpdateIn
from apps.organization.services import LawFirmService

router = Router()


def _get_lawfirm_service() -> LawFirmService:
    """工厂函数：创建 LawFirmService 实例"""
    return LawFirmService()


@router.get("/lawfirms", response=list[LawFirmOut])
def list_lawfirms(request: HttpRequest) -> list[LawFirmOut]:
    """列表查询律所"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    return list(service.list_lawfirms(user=user))


@router.get("/lawfirms/{law_firm_id}", response=LawFirmOut)
def get_lawfirm(request: HttpRequest, law_firm_id: int) -> LawFirmOut:
    """获取律所详情"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    return service.get_lawfirm(law_firm_id, user)


@router.post("/lawfirms", response=LawFirmOut)
def create_lawfirm(request: HttpRequest, payload: LawFirmIn) -> LawFirmOut:
    """创建律所"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    dto = LawFirmCreateDTO(
        name=payload.name,
        address=payload.address,
        phone=payload.phone,
        social_credit_code=payload.social_credit_code,
    )
    return service.create_lawfirm(data=dto, user=user)


@router.put("/lawfirms/{law_firm_id}", response=LawFirmOut)
def update_lawfirm(request: HttpRequest, law_firm_id: int, payload: LawFirmUpdateIn) -> LawFirmOut:
    """更新律所"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    dto = LawFirmUpdateDTO(
        name=payload.name,
        address=payload.address,
        phone=payload.phone,
        social_credit_code=payload.social_credit_code,
    )
    return service.update_lawfirm(lawfirm_id=law_firm_id, data=dto, user=user)


@router.delete("/lawfirms/{law_firm_id}")
def delete_lawfirm(request: HttpRequest, law_firm_id: int) -> dict[str, bool]:
    """删除律所"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    service.delete_lawfirm(law_firm_id, user)
    return {"success": True}
