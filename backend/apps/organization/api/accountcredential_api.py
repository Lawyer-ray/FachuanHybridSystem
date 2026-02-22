from __future__ import annotations

from django.http import HttpRequest
from ninja import Router

from apps.organization.schemas import AccountCredentialIn, AccountCredentialOut, AccountCredentialUpdateIn
from apps.organization.services import AccountCredentialService

router = Router()


def _get_credential_service() -> AccountCredentialService:
    """工厂函数：创建 AccountCredentialService 实例"""
    return AccountCredentialService()


@router.get("/credentials", response=list[AccountCredentialOut])
def list_credentials(
    request: HttpRequest,
    lawyer_id: int | None = None,
    lawyer_name: str | None = None,
) -> list[AccountCredentialOut]:
    """
    获取账号凭证列表

    Args:
        lawyer_id: 按律师 ID 过滤
        lawyer_name: 按律师姓名过滤（支持模糊匹配 real_name 或 username）
    """
    service = _get_credential_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    return service.list_credentials(
        lawyer_id=lawyer_id,
        lawyer_name=lawyer_name,
        user=user,
    )


@router.get("/credentials/{cred_id}", response=AccountCredentialOut)
def get_credential(request: HttpRequest, cred_id: int) -> AccountCredentialOut:
    """获取单个凭证"""
    service = _get_credential_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    return service.get_credential(cred_id, user=user)


@router.post("/credentials", response=AccountCredentialOut)
def create_credential(request: HttpRequest, payload: AccountCredentialIn) -> AccountCredentialOut:
    """创建凭证"""
    service = _get_credential_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    return service.create_credential(
        lawyer_id=payload.lawyer_id,
        site_name=payload.site_name,
        account=payload.account,
        password=payload.password,
        url=payload.url,
        user=user,
    )


@router.put("/credentials/{cred_id}", response=AccountCredentialOut)
def update_credential(request: HttpRequest, cred_id: int, payload: AccountCredentialUpdateIn) -> AccountCredentialOut:
    """更新凭证"""
    service = _get_credential_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    return service.update_credential(
        credential_id=cred_id,
        data=payload.model_dump(exclude_unset=True),
        user=user,
    )


@router.delete("/credentials/{cred_id}")
def delete_credential(request: HttpRequest, cred_id: int) -> dict[str, bool]:
    """删除凭证"""
    service = _get_credential_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    service.delete_credential(cred_id, user=user)
    return {"success": True}
