"""cloud_storage 授权完成端点响应测试（安全审计：token 前缀不回显）。

onedrive_complete_auth / dropbox_complete_auth 此前在响应中回显
access_token[:20] 明文前缀；前端与 admin 模板均不消费该字段，
现已直接去除，授权成功仅返回 {"status": "authorized"}。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import async_to_sync
from django.test import RequestFactory

from apps.cloud_storage import api as cloud_api
from apps.cloud_storage.models import CloudStorageAccount
from apps.organization.models import Lawyer

SECRET_TOKEN = "super-secret-access-token-0123456789abcdef"  # pragma: allowlist secret


@pytest.fixture
def staff_user(db: None) -> Lawyer:
    return Lawyer.objects.create(username="cloud-auth-staff", is_staff=True)


def _make_account(storage_type: str) -> CloudStorageAccount:
    return CloudStorageAccount.objects.create(name=f"测试{storage_type}", storage_type=storage_type, is_active=True)


def _post_request(user: Lawyer, account_id: int):
    request = RequestFactory().post(
        f"/admin/cloud-storage/{account_id}/complete-auth/",
        data=json.dumps({"device_code": "dev-code-1"}),
        content_type="application/json",
    )
    request.user = user
    # Django 5+ 认证装饰器的 async 分支走 request.auser()，
    # RequestFactory 的 WSGIRequest 不带——显式补上。
    request.auser = AsyncMock(return_value=user)  # type: ignore[method-assign]
    return request


@pytest.mark.django_db
def test_onedrive_complete_auth_does_not_echo_token(staff_user: Lawyer) -> None:
    account = _make_account("onedrive")
    request = _post_request(staff_user, account.pk)

    with patch.object(cloud_api, "OAuthTokenManager") as mock_manager:
        mock_manager.return_value.acomplete_device_code_flow = AsyncMock(return_value=SECRET_TOKEN)
        response = async_to_sync(cloud_api.onedrive_complete_auth)(request, account.pk)

    data = json.loads(response.content)
    assert data == {"status": "authorized"}
    assert "token_preview" not in data
    assert SECRET_TOKEN[:20] not in response.content.decode()
    mock_manager.return_value.acomplete_device_code_flow.assert_awaited_once_with("dev-code-1")


@pytest.mark.django_db
def test_dropbox_complete_auth_does_not_echo_token(staff_user: Lawyer) -> None:
    account = _make_account("dropbox")
    request = _post_request(staff_user, account.pk)

    with patch("apps.cloud_storage.dropbox_provider.DropboxOAuthTokenManager") as mock_manager:
        mock_manager.return_value.acomplete_device_code_flow = AsyncMock(return_value=SECRET_TOKEN)
        response = async_to_sync(cloud_api.dropbox_complete_auth)(request, account.pk)

    data = json.loads(response.content)
    assert data == {"status": "authorized"}
    assert "token_preview" not in data
    assert SECRET_TOKEN[:20] not in response.content.decode()
