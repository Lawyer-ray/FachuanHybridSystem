"""JWT 密码绑定（pwd_ver）测试 — 安全审计 C-14/E-07。

改密后旧 refresh token 必须失效；部署前存量无 claim token 刷新被拒。
"""

from __future__ import annotations

import pytest
from ninja_jwt.tokens import RefreshToken

from apps.core.security.jwt_password_binding import (
    PWD_VER_CLAIM,
    PasswordBoundTokenObtainPairInputSchema,
    PasswordBoundTokenRefreshInputSchema,
    bind_password_claim,
    password_fingerprint,
)
from apps.organization.models import LawFirm, Lawyer


@pytest.fixture
def user(db: None) -> Lawyer:
    firm = LawFirm.objects.create(name="JWT绑定测试律所")
    return Lawyer.objects.create_user(
        username="jwtbinduser",
        password="oldpass123",  # pragma: allowlist secret
        law_firm=firm,
    )


@pytest.mark.django_db
class TestPasswordBinding:
    def test_obtain_pair_binds_pwd_ver_claim(self, user: Lawyer) -> None:
        """签发的 refresh token 携带密码指纹，access token 自动继承"""
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)
        refresh = RefreshToken(data["refresh"])
        assert refresh[PWD_VER_CLAIM] == password_fingerprint(user)
        access = refresh.access_token
        assert access[PWD_VER_CLAIM] == password_fingerprint(user)

    def test_refresh_allowed_while_password_unchanged(self, user: Lawyer) -> None:
        """密码未变时刷新成功"""
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)
        schema = PasswordBoundTokenRefreshInputSchema(refresh=data["refresh"])
        out = schema.to_response_schema()
        assert out.access

    def test_refresh_rejected_after_password_change(self, user: Lawyer) -> None:
        """改密后旧 refresh token 失效（审计核心场景）"""
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)
        user.set_password("newpass456")  # pragma: allowlist secret
        user.save(update_fields=["password"])

        schema = PasswordBoundTokenRefreshInputSchema(refresh=data["refresh"])
        from ninja_jwt.exceptions import AuthenticationFailed

        with pytest.raises(AuthenticationFailed):
            schema.to_response_schema()

    def test_refresh_rejected_for_legacy_token_without_claim(self, user: Lawyer) -> None:
        """部署前的存量 token（无 pwd_ver claim）刷新被拒，强制重新登录"""
        legacy = RefreshToken.for_user(user)  # type: ignore[misc]
        assert PWD_VER_CLAIM not in legacy

        schema = PasswordBoundTokenRefreshInputSchema(refresh=str(legacy))
        from ninja_jwt.exceptions import AuthenticationFailed

        with pytest.raises(AuthenticationFailed):
            schema.to_response_schema()

    def test_fingerprint_changes_on_set_password(self, user: Lawyer) -> None:
        """密码哈希指纹随 set_password 单调变化"""
        before = password_fingerprint(user)
        user.set_password("another789")  # pragma: allowlist secret
        assert password_fingerprint(user) != before

    def test_bind_password_claim_on_social_auth_mint(self, user: Lawyer) -> None:
        """扫码登录链路（token_exchange_service）直接铸造的 token 同样绑定"""
        refresh = bind_password_claim(RefreshToken.for_user(user), user)  # type: ignore[misc]
        assert refresh[PWD_VER_CLAIM] == password_fingerprint(user)


@pytest.mark.django_db
class TestTokenEndpointsEndToEnd:
    """端到端：真实 /api/v1/token 端点验证 settings 接线生效"""

    def _create_user(self) -> Lawyer:
        firm = LawFirm.objects.create(name="JWT端到端测试律所")
        return Lawyer.objects.create_user(
            username="jwte2euser",
            password="e2epass123",  # pragma: allowlist secret
            law_firm=firm,
        )

    def test_pair_and_refresh_then_invalidate_on_password_change(self, db: None) -> None:
        from django.test import Client

        user = self._create_user()
        client = Client()

        resp = client.post(
            "/api/v1/token/pair",
            {"username": "jwte2euser", "password": "e2epass123"},  # pragma: allowlist secret
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.content
        refresh = resp.json()["refresh"]

        # 密码未变：刷新成功
        ok = client.post("/api/v1/token/refresh", {"refresh": refresh}, content_type="application/json")
        assert ok.status_code == 200, ok.content

        # 改密后：旧 refresh token 被拒（401）
        user.set_password("changed456")  # pragma: allowlist secret
        user.save(update_fields=["password"])
        rejected = client.post("/api/v1/token/refresh", {"refresh": refresh}, content_type="application/json")
        assert rejected.status_code == 401, rejected.content
