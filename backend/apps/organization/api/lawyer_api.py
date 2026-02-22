"""
律师 API
只负责请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from ninja import File, Router
from ninja.files import UploadedFile
from django.http import HttpRequest
from apps.organization.api._utils import get_request_user

from apps.organization.dtos import LawyerCreateDTO, LawyerUpdateDTO
from apps.organization.schemas import LawyerCreateIn, LawyerOut, LawyerUpdateIn
from apps.organization.services import LawyerService

router = Router()


def _get_lawyer_service() -> LawyerService:
    """工厂函数：创建 LawyerService 实例"""
    return LawyerService()


@router.get("/lawyers", response=list[LawyerOut])
def list_lawyers(request: HttpRequest) -> list[LawyerOut]:
    """列表查询律师"""
    service = _get_lawyer_service()
    user = get_request_user(request)
    lawyers = service.list_lawyers(user=user)
    return list(lawyers)


@router.get("/lawyers/{lawyer_id}", response=LawyerOut)
def get_lawyer(request: HttpRequest, lawyer_id: int) -> LawyerOut:
    """获取律师详情"""
    service = _get_lawyer_service()
    user = get_request_user(request)
    lawyer = service.get_lawyer(lawyer_id, user)
    return lawyer


@router.post("/lawyers", response=LawyerOut)
def create_lawyer(
    request: HttpRequest,
    payload: LawyerCreateIn,
    license_pdf: UploadedFile | None = File(None),  # type: ignore[misc]
) -> LawyerOut:
    """创建律师"""
    service = _get_lawyer_service()
    user = get_request_user(request)
    dto = LawyerCreateDTO(
        username=payload.username,
        password=payload.password,
        real_name=payload.real_name,
        phone=payload.phone,
        license_no=payload.license_no,
        id_card=payload.id_card,
        law_firm_id=payload.law_firm_id,
        is_admin=payload.is_admin,
        lawyer_team_ids=payload.lawyer_team_ids,
        biz_team_ids=payload.biz_team_ids,
    )
    lawyer = service.create_lawyer(data=dto, user=user, license_pdf=license_pdf)
    return lawyer


@router.put("/lawyers/{lawyer_id}", response=LawyerOut)
def update_lawyer(
    request: HttpRequest,
    lawyer_id: int,
    payload: LawyerUpdateIn,
    license_pdf: UploadedFile | None = File(None),  # type: ignore[misc]
) -> LawyerOut:
    """更新律师"""
    service = _get_lawyer_service()
    user = get_request_user(request)
    dto = LawyerUpdateDTO(
        real_name=payload.real_name,
        phone=payload.phone,
        license_no=payload.license_no,
        id_card=payload.id_card,
        law_firm_id=payload.law_firm_id,
        is_admin=payload.is_admin,
        password=payload.password,
        lawyer_team_ids=payload.lawyer_team_ids,
        biz_team_ids=payload.biz_team_ids,
    )
    lawyer = service.update_lawyer(
        lawyer_id=lawyer_id,
        data=dto,
        user=user,
        license_pdf=license_pdf,
    )
    return lawyer


@router.delete("/lawyers/{lawyer_id}")
def delete_lawyer(request: HttpRequest, lawyer_id: int) -> dict[str, bool]:
    """删除律师"""
    service = _get_lawyer_service()
    user = get_request_user(request)
    service.delete_lawyer(lawyer_id, user)
    return {"success": True}
