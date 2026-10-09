"""JWT 密码绑定（pwd_ver）测试 — 安全审计 C-14/E-07。

改密后旧 refresh token 必须失效；部署前存量无 claim token 刷新被拒。

另覆盖 M-8（refresh token 轮换 + 黑名单）：刷新返回**新的** refresh，
旧 refresh 立即进入黑名单，二次使用即被拒。
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

    def test_refresh_rejected_for_inactive_user(self, user: Lawyer) -> None:
        """停用账号（is_active=False，密码未变）的 refresh token 立即失效。"""
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)
        user.is_active = False
        user.save(update_fields=["is_active"])

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
class TestRefreshRotationAndBlacklist:
    """M-8：refresh token 轮换 + 黑名单。

    前置：settings 已启用 ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION，
    且 ninja_jwt.token_blacklist 的迁移已应用到测试库。
    """

    def _assert_rotation_enabled(self) -> None:
        from django.conf import settings

        assert settings.SIMPLE_JWT["ROTATE_REFRESH_TOKENS"] is True
        assert settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] is True
        assert "ninja_jwt.token_blacklist" in settings.INSTALLED_APPS

    def test_refresh_returns_new_refresh_token(self, user: Lawyer) -> None:
        """刷新必须返回新的 refresh，而不是复用旧的。"""
        self._assert_rotation_enabled()
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)
        old_refresh = data["refresh"]

        schema = PasswordBoundTokenRefreshInputSchema(refresh=old_refresh)
        out = schema.to_response_schema()

        assert out.refresh
        assert out.refresh != old_refresh

    def test_rotated_refresh_keeps_pwd_ver_claim(self, user: Lawyer) -> None:
        """轮换后的新 refresh 必须仍带 pwd_ver，否则下次刷新会被拒（用户被踢下线）。

        set_jti/set_exp/set_iat 只重置这三个 claim、不清空其他 claim，故
        pwd_ver 自动继承——此测试锁定该依赖，防止未来上游改动破坏它。
        """
        self._assert_rotation_enabled()
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)

        schema = PasswordBoundTokenRefreshInputSchema(refresh=data["refresh"])
        out = schema.to_response_schema()

        rotated = RefreshToken(out.refresh)
        assert rotated[PWD_VER_CLAIM] == password_fingerprint(user)

    def test_rotated_refresh_is_usable_for_next_refresh(self, user: Lawyer) -> None:
        """新 refresh 可继续用于下一次刷新（链式轮换不断链）。"""
        self._assert_rotation_enabled()
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)

        first = PasswordBoundTokenRefreshInputSchema(refresh=data["refresh"]).to_response_schema()
        second = PasswordBoundTokenRefreshInputSchema(refresh=first.refresh).to_response_schema()

        assert second.access
        assert second.refresh != first.refresh

    def test_old_refresh_rejected_after_rotation(self, user: Lawyer) -> None:
        """M-8 核心：旧 refresh 轮换后立即失效，二次使用被拒。

        注意异常类型：RefreshToken.__init__ 的 check_blacklist() 抛裸
        TokenError，经 ninja_jwt 的 token_error 装饰器包装后对外呈现为
        InvalidToken（HTTP 401 token_not_valid）——断言的是 InvalidToken。
        """
        from ninja_jwt.exceptions import InvalidToken

        self._assert_rotation_enabled()
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)
        old_refresh = data["refresh"]

        first = PasswordBoundTokenRefreshInputSchema(refresh=old_refresh).to_response_schema()
        assert first.refresh

        with pytest.raises(InvalidToken):
            PasswordBoundTokenRefreshInputSchema(refresh=old_refresh).to_response_schema()

    def test_rotation_creates_blacklist_rows(self, user: Lawyer) -> None:
        """黑名单落库：OutstandingToken + BlacklistedToken 各一行。"""
        from ninja_jwt.token_blacklist.models import BlacklistedToken, OutstandingToken

        self._assert_rotation_enabled()
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)

        PasswordBoundTokenRefreshInputSchema(refresh=data["refresh"]).to_response_schema()

        assert OutstandingToken.objects.filter(user=user).count() >= 1
        assert BlacklistedToken.objects.filter(token__user=user).count() >= 1

    def test_password_change_still_kills_rotated_refresh(self, user: Lawyer) -> None:
        """轮换不削弱改密失效：新 refresh 仍受 pwd_ver 约束。"""
        from ninja_jwt.exceptions import AuthenticationFailed

        self._assert_rotation_enabled()
        data = PasswordBoundTokenObtainPairInputSchema.get_token(user)
        rotated = PasswordBoundTokenRefreshInputSchema(refresh=data["refresh"]).to_response_schema().refresh

        user.set_password("rotated999")  # pragma: allowlist secret
        user.save(update_fields=["password"])

        with pytest.raises(AuthenticationFailed):
            PasswordBoundTokenRefreshInputSchema(refresh=rotated).to_response_schema()


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
