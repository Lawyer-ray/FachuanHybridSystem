"""cloud_storage account_service 单元测试。

覆盖 resolve_active_storage_account 的命中与不存在/禁用/类型不匹配
（ValidationException，code=STORAGE_ACCOUNT_NOT_FOUND）路径。
"""

from __future__ import annotations

import pytest

from apps.cloud_storage.account_service import resolve_active_storage_account
from apps.cloud_storage.models import CloudStorageAccount
from apps.core.exceptions import ValidationException


@pytest.fixture
def webdav_account(db: None) -> CloudStorageAccount:
    return CloudStorageAccount.objects.create(name="坚果云", storage_type="webdav", is_active=True)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_resolve_active_account(webdav_account: CloudStorageAccount) -> None:
    got = await resolve_active_storage_account(webdav_account.id, "webdav")
    assert got.pk == webdav_account.pk


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_resolve_missing_account_raises_validation(webdav_account: CloudStorageAccount) -> None:
    with pytest.raises(ValidationException) as exc_info:
        await resolve_active_storage_account(999999, "webdav")
    assert exc_info.value.code == "STORAGE_ACCOUNT_NOT_FOUND"
    assert exc_info.value.errors == {"storage_account_id": 999999}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_resolve_type_mismatch_raises_validation(webdav_account: CloudStorageAccount) -> None:
    with pytest.raises(ValidationException):
        await resolve_active_storage_account(webdav_account.id, "onedrive")


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_resolve_disabled_account_raises_validation(webdav_account: CloudStorageAccount) -> None:
    await CloudStorageAccount.objects.filter(pk=webdav_account.pk).aupdate(is_active=False)
    with pytest.raises(ValidationException):
        await resolve_active_storage_account(webdav_account.id, "webdav")
