from __future__ import annotations

from typing import cast

from django.http import HttpRequest
from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth
from apps.organization.api.utils_api import get_request_user
from apps.organization.dtos import AccountCredentialCreateDTO, AccountCredentialUpdateDTO
from apps.organization.schemas import AccountCredentialIn, AccountCredentialOut, AccountCredentialUpdateIn
from apps.organization.services import AccountCredentialService

router = Router(auth=JWTOrSessionAuth())


def _get_credential_service() -> AccountCredentialService:
    """工厂函数：获取账号凭证服务实例"""
    return AccountCredentialService()


_credential_service = _get_credential_service()


@router.get("/credentials", response=list[AccountCredentialOut])
def list_credentials(
    request: HttpRequest,
    lawyer_id: int | None = None,
    lawyer_name: str | None = None,
) -> list[AccountCredentialOut]:
    return list(
        _credential_service.list_credentials(
            lawyer_id=lawyer_id,
            lawyer_name=lawyer_name,
            user=get_request_user(request),
        )
    )


@router.get("/credentials/{cred_id}", response=AccountCredentialOut)
def get_credential(request: HttpRequest, cred_id: int) -> AccountCredentialOut:
    return _credential_service.get_credential(cred_id, user=get_request_user(request))


@router.post("/credentials", response=AccountCredentialOut)
def create_credential(request: HttpRequest, payload: AccountCredentialIn) -> AccountCredentialOut:
    dto = AccountCredentialCreateDTO(
        lawyer_id=payload.lawyer_id,
        site_name=payload.site_name,
        account=payload.account,
        password=payload.password,
        url=payload.url,
    )
    credential = _credential_service.create_credential(data=dto, user=get_request_user(request))
    return cast(AccountCredentialOut, AccountCredentialOut.from_orm(credential))


@router.put("/credentials/{cred_id}", response=AccountCredentialOut)
def update_credential(request: HttpRequest, cred_id: int, payload: AccountCredentialUpdateIn) -> AccountCredentialOut:
    dto = AccountCredentialUpdateDTO(
        site_name=payload.site_name,
        url=payload.url,
        account=payload.account,
        password=payload.password,
    )
    credential = _credential_service.update_credential(
        credential_id=cred_id,
        data=dto,
        user=get_request_user(request),
    )
    return cast(AccountCredentialOut, AccountCredentialOut.from_orm(credential))


@router.delete("/credentials/{cred_id}")
def delete_credential(request: HttpRequest, cred_id: int) -> dict[str, bool]:
    _credential_service.delete_credential(cred_id, user=get_request_user(request))
    return {"success": True}
