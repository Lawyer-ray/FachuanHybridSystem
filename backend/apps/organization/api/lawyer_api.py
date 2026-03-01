"""
律师 API
只负责请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from ninja import File, Router
from ninja.files import UploadedFile
from django.http import HttpRequest
from apps.organization.api._utils import get_request_user

from apps.organization.dtos import LawyerCreateDTO, LawyerListFiltersDTO, LawyerUpdateDTO
from apps.organization.schemas import LawyerCreateIn, LawyerOut, LawyerUpdateIn
from apps.organization.services import LawyerService

from apps.core.auth import JWTOrSessionAuth

router = Router(auth=JWTOrSessionAuth())

_lawyer_service = LawyerService()


@router.get("/lawyers", response=list[LawyerOut])
def list_lawyers(
    request: HttpRequest,
    search: str | None = None,
    law_firm_id: int | None = None,
) -> list[LawyerOut]:
    filters = LawyerListFiltersDTO(search=search, law_firm_id=law_firm_id)
    return list(_lawyer_service.list_lawyers(filters=filters, user=get_request_user(request)))


@router.get("/lawyers/{lawyer_id}", response=LawyerOut)
def get_lawyer(request: HttpRequest, lawyer_id: int) -> LawyerOut:
    return _lawyer_service.get_lawyer(lawyer_id, get_request_user(request))


@router.post("/lawyers", response=LawyerOut)
def create_lawyer(
    request: HttpRequest,
    payload: LawyerCreateIn,
    license_pdf: UploadedFile | None = File(None),  # type: ignore[misc]
) -> LawyerOut:
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
    return _lawyer_service.create_lawyer(data=dto, user=get_request_user(request), license_pdf=license_pdf)


@router.put("/lawyers/{lawyer_id}", response=LawyerOut)
def update_lawyer(
    request: HttpRequest,
    lawyer_id: int,
    payload: LawyerUpdateIn,
    license_pdf: UploadedFile | None = File(None),  # type: ignore[misc]
) -> LawyerOut:
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
    return _lawyer_service.update_lawyer(
        lawyer_id=lawyer_id,
        data=dto,
        user=get_request_user(request),
        license_pdf=license_pdf,
    )


@router.delete("/lawyers/{lawyer_id}")
def delete_lawyer(request: HttpRequest, lawyer_id: int) -> dict[str, bool]:
    _lawyer_service.delete_lawyer(lawyer_id, get_request_user(request))
    return {"success": True}
