"""passkey API integration 测试。

覆盖：凭据管理端点鉴权与属主隔离、登录 ceremony 全流程（挑战→断言→JWT→
挑战一次性）、注册 ceremony 全流程（excludeCredentials 收敛）、Origin 缺失。

py_webauthn 的 verify 函数 mock 掉（同 unit 测试口径）；session 依赖 Django
test Client 的 cookie 串联，与前端同源 cookie 行为一致。

限流说明：ceremony 端点挂 AUTH 档 cache 计数限流，本文件 autouse 清缓存防 429。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from django.core.cache import cache

pytestmark = pytest.mark.django_db

_ORIGIN = "http://localhost:5199"


@pytest.fixture(autouse=True)
def _passkey_env(settings: Any) -> Any:
    settings.DEBUG = True
    settings.CORS_ALLOWED_ORIGINS = [_ORIGIN]
    settings.CSRF_TRUSTED_ORIGINS = [_ORIGIN]
    settings.FRONTEND_BASE_URL = _ORIGIN


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


def _origin_kwargs() -> dict[str, str]:
    return {"HTTP_ORIGIN": _ORIGIN}


def _fake_assertion(credential_id: str) -> dict[str, Any]:
    """浏览器 navigator.credentials.get() 会产出的 JSON 形状（内容由 mock 承接）。"""
    return {
        "id": credential_id,
        "rawId": credential_id,
        "type": "public-key",
        "response": {
            "clientDataJSON": "e30",
            "authenticatorData": "AA",
            "signature": "AA",
            "userHandle": None,
        },
    }


class TestCredentialManagement:
    def test_requires_auth(self, api_client: Any) -> None:
        resp = api_client.get("/api/v1/social/passkey/credentials")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "HTTP_ERROR"
        assert body["message"] == "Unauthorized"
        assert "credentials" not in body  # 未认证不泄露凭据列表

    def test_empty_list(self, authenticated_client: Any) -> None:
        resp = authenticated_client.get("/api/v1/social/passkey/credentials")
        assert resp.status_code == 200
        assert resp.json()["credentials"] == []

    def test_rename_and_delete_own_credential(self, authenticated_client: Any) -> None:
        from apps.organization.models import Lawyer
        from apps.social_auth.models import PasskeyCredential

        user = Lawyer.objects.get(username="testuser")
        cred = PasskeyCredential.objects.create(
            user=user,
            name="初始名",
            credential_id="cred-1",
            public_key="cHVia2V5",
            rp_id="localhost",
        )
        resp = authenticated_client.patch(
            f"/api/v1/social/passkey/credentials/{cred.id}",
            data={"name": "MacBook Touch ID"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        cred.refresh_from_db()
        assert cred.name == "MacBook Touch ID"

        resp = authenticated_client.delete(f"/api/v1/social/passkey/credentials/{cred.id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert not PasskeyCredential.objects.filter(pk=cred.id).exists()

        # 再删一次 → 未找到
        resp = authenticated_client.delete(f"/api/v1/social/passkey/credentials/{cred.id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_cannot_touch_other_users_credential(self, authenticated_client: Any) -> None:
        from apps.organization.models import Lawyer
        from apps.social_auth.models import PasskeyCredential

        other = Lawyer.objects.create(username="pk-other-user")
        cred = PasskeyCredential.objects.create(
            user=other,
            name="别人的",
            credential_id="cred-other",
            public_key="cHVia2V5",
            rp_id="localhost",
        )
        resp = authenticated_client.patch(
            f"/api/v1/social/passkey/credentials/{cred.id}",
            data={"name": "越权改名"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        resp = authenticated_client.delete(f"/api/v1/social/passkey/credentials/{cred.id}")
        assert resp.json()["success"] is False
        assert PasskeyCredential.objects.filter(pk=cred.id).exists()


class TestLoginCeremony:
    def test_login_options_success(self, api_client: Any) -> None:
        resp = api_client.post("/api/v1/social/passkey/login/options", **_origin_kwargs())
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["public_key"]["rpId"] == "localhost"
        assert body["public_key"]["challenge"]
        # 可发现凭据：不提供用户列表（无用户枚举面）
        assert body["public_key"].get("allowCredentials", []) == []

    def test_login_options_without_origin_fails(self, api_client: Any) -> None:
        resp = api_client.post("/api/v1/social/passkey/login/options")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["message"]

    def test_login_verify_full_flow_and_one_shot(self, api_client: Any) -> None:
        from apps.organization.models import Lawyer
        from apps.social_auth.models import PasskeyCredential

        user, _ = Lawyer.objects.get_or_create(
            username="pk-login-user", defaults={"is_active": True, "real_name": "李四"}
        )
        PasskeyCredential.objects.create(
            user=user,
            name="测试",
            credential_id="pk-login-cred",
            public_key="cHVia2V5",
            rp_id="localhost",
        )
        # 1) 拿挑战
        resp = api_client.post("/api/v1/social/passkey/login/options", **_origin_kwargs())
        assert resp.json()["success"] is True
        # 2) 提交断言（verify 由 mock 承接）
        with patch("apps.social_auth.services.passkey_service.verify_authentication_response") as mock_verify:
            mock_verify.return_value = SimpleNamespace(new_sign_count=7)
            resp = api_client.post(
                "/api/v1/social/passkey/login/verify",
                data={"credential": _fake_assertion("pk-login-cred")},
                content_type="application/json",
                **_origin_kwargs(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["access"] and body["refresh"]
        assert body["user_id"] == user.id
        # 3) 挑战一次性：重放失败
        resp = api_client.post(
            "/api/v1/social/passkey/login/verify",
            data={"credential": _fake_assertion("pk-login-cred")},
            content_type="application/json",
            **_origin_kwargs(),
        )
        assert resp.json()["success"] is False

    def test_login_verify_unknown_credential(self, api_client: Any) -> None:
        resp = api_client.post("/api/v1/social/passkey/login/options", **_origin_kwargs())
        assert resp.json()["success"] is True
        resp = api_client.post(
            "/api/v1/social/passkey/login/verify",
            data={"credential": _fake_assertion("no-such-cred")},
            content_type="application/json",
            **_origin_kwargs(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["message"]


class TestRegisterCeremony:
    def test_register_requires_auth(self, api_client: Any) -> None:
        resp = api_client.post("/api/v1/social/passkey/register/options", **_origin_kwargs())
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "HTTP_ERROR"
        assert body["message"] == "Unauthorized"
        assert "public_key" not in body  # 未认证不泄露挑战材料

    def test_register_flow_and_exclude_credentials(self, authenticated_client: Any) -> None:
        from apps.social_auth.models import PasskeyCredential

        # 1) 拿注册挑战
        resp = authenticated_client.post("/api/v1/social/passkey/register/options", **_origin_kwargs())
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["public_key"]["rp"]["id"] == "localhost"
        assert body["public_key"].get("excludeCredentials", []) == []

        # 2) 提交注册响应（verify 由 mock 承接）
        verified_reg = SimpleNamespace(
            credential_id=b"\x09" * 32,
            credential_public_key=b"pubkey",
            sign_count=1,
            credential_backed_up=False,
        )
        with patch("apps.social_auth.services.passkey_service.verify_registration_response") as mock_verify:
            mock_verify.return_value = verified_reg
            resp = authenticated_client.post(
                "/api/v1/social/passkey/register/verify",
                data={"name": "MacBook", "credential": _fake_assertion("ignored-by-mock")},
                content_type="application/json",
                **_origin_kwargs(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["credential"]["name"] == "MacBook"
        row = PasskeyCredential.objects.get(name="MacBook")
        assert row.rp_id == "localhost"

        # 3) 再次注册：excludeCredentials 已包含刚注册的凭据
        resp = authenticated_client.post("/api/v1/social/passkey/register/options", **_origin_kwargs())
        excluded = resp.json()["public_key"]["excludeCredentials"]
        assert len(excluded) == 1
        assert excluded[0]["id"]
