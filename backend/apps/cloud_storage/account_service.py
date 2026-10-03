"""云存储账号查询服务。

承载 contracts/folder_binding_api 下沉的存储账号解析：按 ID + 存储类型
定位启用中的账号，供文件夹绑定创建时引用。账号不存在或已禁用抛
``ValidationException``（HTTP 400），语义与 API 时期一致。
"""

from __future__ import annotations

from apps.cloud_storage.models import CloudStorageAccount
from apps.core.exceptions import ValidationException


async def resolve_active_storage_account(storage_account_id: int, storage_type: str) -> CloudStorageAccount:
    """解析启用中的云存储账号。

    Raises:
        ValidationException: 账号不存在、类型不匹配或已禁用（HTTP 400，
            code=STORAGE_ACCOUNT_NOT_FOUND）。
    """
    storage_account = await CloudStorageAccount.objects.filter(
        id=storage_account_id, storage_type=storage_type, is_active=True
    ).afirst()
    if storage_account is None:
        raise ValidationException(
            message="指定的云存储账号不存在或已禁用",
            code="STORAGE_ACCOUNT_NOT_FOUND",
            errors={"storage_account_id": storage_account_id},
        )
    return storage_account
