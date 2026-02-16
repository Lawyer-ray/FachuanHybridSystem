from typing import List, Optional
from ninja import Router
from ..schemas import AccountCredentialOut, AccountCredentialIn, AccountCredentialUpdateIn

router = Router()


def _get_credential_service():
    """工厂函数：创建 AccountCredentialService 实例"""
    from ..services import AccountCredentialService
    return AccountCredentialService()


@router.get("/credentials", response=List[AccountCredentialOut])
def list_credentials(
    request,
    lawyer_id: Optional[int] = None,
    lawyer_name: Optional[str] = None,
):
    """
    获取账号凭证列表

    Args:
        lawyer_id: 按律师 ID 过滤
        lawyer_name: 按律师姓名过滤（支持模糊匹配 real_name 或 username）
    """
    service = _get_credential_service()
    user = getattr(request, "user", None)
    return service.list_credentials(
        lawyer_id=lawyer_id,
        lawyer_name=lawyer_name,
        user=user,
    )


@router.get("/credentials/{cred_id}", response=AccountCredentialOut)
def get_credential(request, cred_id: int):
    """获取单个凭证"""
    service = _get_credential_service()
    user = getattr(request, "user", None)
    return service.get_credential(cred_id, user=user)


@router.post("/credentials", response=AccountCredentialOut)
def create_credential(request, payload: AccountCredentialIn):
    """创建凭证"""
    service = _get_credential_service()
    user = getattr(request, "user", None)
    return service.create_credential(
        lawyer_id=payload.lawyer_id,
        site_name=payload.site_name,
        account=payload.account,
        password=payload.password,
        url=payload.url,
        user=user,
    )


@router.put("/credentials/{cred_id}", response=AccountCredentialOut)
def update_credential(request, cred_id: int, payload: AccountCredentialUpdateIn):
    """更新凭证"""
    service = _get_credential_service()
    user = getattr(request, "user", None)
    return service.update_credential(
        credential_id=cred_id,
        data=payload.dict(exclude_unset=True),
        user=user,
    )


@router.delete("/credentials/{cred_id}")
def delete_credential(request, cred_id: int):
    """删除凭证"""
    service = _get_credential_service()
    user = getattr(request, "user", None)
    service.delete_credential(cred_id, user=user)
    return {"success": True}
