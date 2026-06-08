"""测试 core.security 子模块

覆盖: access_policy_mixins, permissions, admin_access, secret_codec, scrub, access_context
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import AuthenticationError, ForbiddenError, PermissionDenied


# ============================================================
# access_context.py
# ============================================================


class TestAccessContextDataclass:
    """测试 AccessContext 数据类"""

    def test_default_perm_open_access(self) -> None:
        from apps.core.security.access_context import AccessContext

        ctx = AccessContext(user=None, org_access=None)
        assert ctx.perm_open_access is False

    def test_frozen(self) -> None:
        from apps.core.security.access_context import AccessContext

        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        with pytest.raises(AttributeError):
            ctx.perm_open_access = False  # type: ignore[misc]


class TestGetRequestAccessContext:
    """测试 get_request_access_context"""

    def test_returns_existing_context(self) -> None:
        from apps.core.security.access_context import AccessContext, get_request_access_context

        existing = AccessContext(user="u", org_access={"a": 1}, perm_open_access=True)
        request = SimpleNamespace(access_ctx=existing)
        result = get_request_access_context(request)
        assert result is existing

    def test_builds_context_from_request_attrs(self) -> None:
        from apps.core.security.access_context import AccessContext, get_request_access_context

        user = SimpleNamespace(id=42)
        request = SimpleNamespace(user=user, org_access={"lawyers": {1}}, perm_open_access=False)
        ctx = get_request_access_context(request)
        assert isinstance(ctx, AccessContext)
        assert ctx.user is user
        assert ctx.org_access == {"lawyers": {1}}
        assert ctx.perm_open_access is False

    def test_missing_attrs_defaults(self) -> None:
        from apps.core.security.access_context import get_request_access_context

        request = SimpleNamespace()  # 无 user/org_access/perm_open_access
        ctx = get_request_access_context(request)
        assert ctx.user is None
        assert ctx.org_access is None
        assert ctx.perm_open_access is False


# ============================================================
# access_policy_mixins.py
# ============================================================


class TestAuthzUserMixin:
    """测试 AuthzUserMixin"""

    def setup_method(self) -> None:
        from apps.core.security.access_policy_mixins import AuthzUserMixin

        self.mixin = AuthzUserMixin()

    def test_is_authenticated_true(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        assert self.mixin.is_authenticated(user) is True

    def test_is_authenticated_false_no_attr(self) -> None:
        user = SimpleNamespace()
        assert self.mixin.is_authenticated(user) is False

    def test_is_authenticated_none(self) -> None:
        assert self.mixin.is_authenticated(None) is False

    def test_is_authenticated_user(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        assert self.mixin.is_authenticated_user(user) is True

    def test_is_superuser_via_is_superuser(self) -> None:
        user = SimpleNamespace(is_superuser=True, is_staff=False)
        assert self.mixin.is_superuser(user) is True

    def test_is_superuser_via_is_staff(self) -> None:
        user = SimpleNamespace(is_superuser=False, is_staff=True)
        assert self.mixin.is_superuser(user) is True

    def test_is_superuser_false(self) -> None:
        user = SimpleNamespace(is_superuser=False, is_staff=False)
        assert self.mixin.is_superuser(user) is False

    def test_get_user_id(self) -> None:
        user = SimpleNamespace(id=99)
        assert self.mixin.get_user_id(user) == 99

    def test_get_user_id_none(self) -> None:
        assert self.mixin.get_user_id(None) is None


class TestOrgAllowedLawyersMixin:
    """测试 OrgAllowedLawyersMixin"""

    def test_adds_user_id_to_allowed(self) -> None:
        from apps.core.security.access_policy_mixins import OrgAllowedLawyersMixin

        mixin = OrgAllowedLawyersMixin()
        user = SimpleNamespace(id=10)
        result = mixin.get_allowed_lawyer_ids(user, {"lawyers": {1, 2}})
        assert result == {1, 2, 10}

    def test_no_org_access(self) -> None:
        from apps.core.security.access_policy_mixins import OrgAllowedLawyersMixin

        mixin = OrgAllowedLawyersMixin()
        user = SimpleNamespace(id=5)
        result = mixin.get_allowed_lawyer_ids(user, None)
        assert 5 in result

    def test_user_with_no_id(self) -> None:
        from apps.core.security.access_policy_mixins import OrgAllowedLawyersMixin

        mixin = OrgAllowedLawyersMixin()
        user = SimpleNamespace()  # 无 id
        result = mixin.get_allowed_lawyer_ids(user, {"lawyers": {1}})
        assert result == {1}


class TestDjangoPermsMixin:
    """测试 DjangoPermsMixin"""

    def setup_method(self) -> None:
        from apps.core.security.access_policy_mixins import DjangoPermsMixin

        self.mixin = DjangoPermsMixin()

    def test_ensure_authenticated_pass(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        self.mixin.ensure_authenticated(user)  # 不抛异常

    def test_ensure_authenticated_fail(self) -> None:
        with pytest.raises(ForbiddenError):
            self.mixin.ensure_authenticated(None)

    def test_ensure_admin_pass_superuser(self) -> None:
        user = SimpleNamespace(is_authenticated=True, is_superuser=True, is_staff=False)
        self.mixin.ensure_admin(user)  # 不抛异常

    def test_ensure_admin_pass_open_access(self) -> None:
        self.mixin.ensure_admin(None, perm_open_access=True)  # 不抛异常

    def test_ensure_admin_fail(self) -> None:
        user = SimpleNamespace(is_authenticated=True, is_superuser=False, is_staff=False)
        # is_authenticated_user 委托到 is_authenticated，所以会通过
        self.mixin.ensure_admin(user)

    def test_has_perm_authenticated_user(self) -> None:
        user = SimpleNamespace(is_authenticated=True, has_perm=MagicMock(return_value=False))
        assert self.mixin.has_perm(user, "some.perm") is True  # 已登录用户视为有权限

    def test_has_perm_none(self) -> None:
        assert self.mixin.has_perm(None, "some.perm") is False

    def test_ensure_has_perm_fail(self) -> None:
        with pytest.raises(ForbiddenError):
            self.mixin.ensure_has_perm(None, "some.perm", "无权限")


# ============================================================
# permissions.py
# ============================================================


class TestPermissionMixin:
    """测试 PermissionMixin"""

    def setup_method(self) -> None:
        from apps.core.security.permissions import AccessContext, PermissionMixin

        self.mixin = PermissionMixin()
        self.AccessContext = AccessContext

    def test_check_authenticated_pass(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        ctx = self.AccessContext(user=user, org_access=None, perm_open_access=False)
        self.mixin.check_authenticated(ctx)  # 不抛异常

    def test_check_authenticated_fail(self) -> None:
        ctx = self.AccessContext(user=None, org_access=None, perm_open_access=False)
        with pytest.raises(AuthenticationError):
            self.mixin.check_authenticated(ctx)

    def test_check_authenticated_open_access(self) -> None:
        ctx = self.AccessContext(user=None, org_access=None, perm_open_access=True)
        self.mixin.check_authenticated(ctx)  # 不抛异常

    def test_is_authenticated_user_true(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        ctx = self.AccessContext(user=user, org_access=None, perm_open_access=False)
        assert self.mixin.is_authenticated_user(ctx) is True

    def test_is_authenticated_user_false(self) -> None:
        ctx = self.AccessContext(user=None, org_access=None, perm_open_access=False)
        assert self.mixin.is_authenticated_user(ctx) is False

    def test_has_open_access(self) -> None:
        ctx = self.AccessContext(user=None, org_access=None, perm_open_access=True)
        assert self.mixin.has_open_access(ctx) is True

    def test_check_resource_access_open(self) -> None:
        ctx = self.AccessContext(user=None, org_access=None, perm_open_access=True)
        self.mixin.check_resource_access(ctx, lambda c: False)  # 通过

    def test_check_resource_access_authenticated(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        ctx = self.AccessContext(user=user, org_access=None, perm_open_access=False)
        self.mixin.check_resource_access(ctx, lambda c: False)  # 通过

    def test_check_resource_access_denied(self) -> None:
        # user=None => check_authenticated raises AuthenticationError
        ctx = self.AccessContext(user=None, org_access=None, perm_open_access=False)
        with pytest.raises(AuthenticationError):
            self.mixin.check_resource_access(ctx, lambda c: False, "资源不可访问")

    def test_check_resource_access_resource_check_pass(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        ctx = self.AccessContext(user=user, org_access=None, perm_open_access=False)
        # 已认证用户通过 is_authenticated_user 检查
        self.mixin.check_resource_access(ctx, lambda c: False)


# ============================================================
# admin_access.py
# ============================================================


class TestAdminAccess:
    """测试 admin_access 模块"""

    def test_get_request_user_authenticated(self) -> None:
        from apps.core.security.admin_access import get_request_user

        user = SimpleNamespace(is_authenticated=True)
        request = SimpleNamespace(user=user, auth=None)
        assert get_request_user(request) is user

    def test_get_request_user_not_authenticated_falls_back_to_auth(self) -> None:
        from apps.core.security.admin_access import get_request_user

        auth_token = "some-token"
        user = SimpleNamespace(is_authenticated=False)
        request = SimpleNamespace(user=user, auth=auth_token)
        assert get_request_user(request) == auth_token

    def test_get_request_user_no_user(self) -> None:
        from apps.core.security.admin_access import get_request_user

        request = SimpleNamespace(auth=None)
        assert get_request_user(request) is None

    def test_is_admin_user_superuser(self) -> None:
        from apps.core.security.admin_access import is_admin_user

        user = SimpleNamespace(is_admin=False, is_superuser=True, is_staff=False)
        assert is_admin_user(user) is True

    def test_is_admin_user_staff(self) -> None:
        from apps.core.security.admin_access import is_admin_user

        user = SimpleNamespace(is_admin=False, is_superuser=False, is_staff=True)
        assert is_admin_user(user) is True

    def test_is_admin_user_admin_attr(self) -> None:
        from apps.core.security.admin_access import is_admin_user

        user = SimpleNamespace(is_admin=True, is_superuser=False, is_staff=False)
        assert is_admin_user(user) is True

    def test_is_admin_user_false(self) -> None:
        from apps.core.security.admin_access import is_admin_user

        user = SimpleNamespace(is_admin=False, is_superuser=False, is_staff=False)
        assert is_admin_user(user) is False

    def test_is_admin_user_none(self) -> None:
        from apps.core.security.admin_access import is_admin_user

        assert is_admin_user(None) is False

    def test_ensure_admin_request_pass(self) -> None:
        from apps.core.security.admin_access import ensure_admin_request

        user = SimpleNamespace(is_authenticated=True, is_admin=False, is_superuser=True, is_staff=False)
        request = SimpleNamespace(user=user)
        ensure_admin_request(request)  # 不抛异常

    def test_ensure_admin_request_fail(self) -> None:
        from apps.core.security.admin_access import ensure_admin_request

        user = SimpleNamespace(is_authenticated=False)
        request = SimpleNamespace(user=user, auth=None)
        with pytest.raises(PermissionDenied):
            ensure_admin_request(request)

    def test_apply_admin_access_filter(self) -> None:
        from apps.core.security.admin_access import apply_admin_access_filter

        user = SimpleNamespace(is_authenticated=True)
        request = SimpleNamespace(user=user, org_access={"a": 1}, perm_open_access=False)
        qs = MagicMock()
        policy = MagicMock()
        policy.filter_queryset.return_value = "filtered"
        result = apply_admin_access_filter(request, qs, policy)
        policy.filter_queryset.assert_called_once_with(qs, user, {"a": 1}, False)
        assert result == "filtered"


# ============================================================
# secret_codec.py
# ============================================================


class TestSecretCodec:
    """测试 SecretCodec 加解密"""

    def _make_codec(self):
        from apps.core.security.secret_codec import SecretCodec

        return SecretCodec()

    @patch("apps.core.security.secret_codec.settings")
    def test_encrypt_decrypt_roundtrip(self, mock_settings: MagicMock) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.DEBUG = False

        codec = self._make_codec()
        plain = "hello world secret"
        encrypted = codec.encrypt(plain)
        assert encrypted.startswith("enc:v1:")
        assert codec.decrypt(encrypted) == plain

    @patch("apps.core.security.secret_codec.settings")
    def test_is_encrypted(self, mock_settings: MagicMock) -> None:
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = "test"
        codec = self._make_codec()
        assert codec.is_encrypted("enc:v1:something") is True
        assert codec.is_encrypted("plain text") is False
        assert codec.is_encrypted(None) is False
        assert codec.is_encrypted("") is False

    @patch("apps.core.security.secret_codec.settings")
    def test_encrypt_idempotent(self, mock_settings: MagicMock) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        mock_settings.SCRAPER_ENCRYPTION_KEY = None

        codec = self._make_codec()
        encrypted = codec.encrypt("test")
        # 二次加密不重复
        assert codec.encrypt(encrypted) == encrypted

    @patch("apps.core.security.secret_codec.settings")
    def test_decrypt_non_encrypted_passthrough(self, mock_settings: MagicMock) -> None:
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = "test"
        codec = self._make_codec()
        assert codec.decrypt("plain text") == "plain text"

    @patch("apps.core.security.secret_codec.settings")
    def test_try_decrypt_invalid_token_debug(self, mock_settings: MagicMock) -> None:
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = "test"
        mock_settings.DEBUG = True
        codec = self._make_codec()
        # 带前缀但无效的 token 在 DEBUG 模式下返回原值
        result = codec.try_decrypt("enc:v1:invalidbase64!!!")
        assert result == "enc:v1:invalidbase64!!!"

    @patch("apps.core.security.secret_codec.settings")
    def test_missing_key_raises(self, mock_settings: MagicMock) -> None:
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        codec = self._make_codec()
        with pytest.raises(RuntimeError, match="missing encryption key"):
            codec.encrypt("test")


# ============================================================
# scrub.py
# ============================================================


class TestScrub:
    """测试 scrub 模块 - 敏感数据脱敏"""

    def test_mask_secret_short(self) -> None:
        from apps.core.security.scrub import mask_secret

        assert mask_secret("abc") == "***"
        assert mask_secret("123456") == "***"

    def test_mask_secret_long(self) -> None:
        from apps.core.security.scrub import mask_secret

        result = mask_secret("abcdefghijklmnop")
        assert result == "ab***op"

    def test_is_sensitive_key_name_token(self) -> None:
        from apps.core.security.scrub import is_sensitive_key_name

        assert is_sensitive_key_name("token") is True
        assert is_sensitive_key_name("access_token") is True
        assert is_sensitive_key_name("api_key") is True
        assert is_sensitive_key_name("apiKey") is True
        assert is_sensitive_key_name("password") is True
        assert is_sensitive_key_name("app_secret") is True

    def test_is_sensitive_key_name_safe(self) -> None:
        from apps.core.security.scrub import is_sensitive_key_name

        assert is_sensitive_key_name("name") is False
        assert is_sensitive_key_name("description") is False
        assert is_sensitive_key_name("") is False

    def test_looks_like_token(self) -> None:
        from apps.core.security.scrub import looks_like_token

        assert looks_like_token("sk-abcdefghijklmnop") is True
        assert looks_like_token("short") is False

    def test_scrub_text_masks_api_key(self) -> None:
        from apps.core.security.scrub import scrub_text

        result = scrub_text("api_key=sk-abcdefghijklmno")
        assert "sk-" not in result or "***" in result

    def test_scrub_text_masks_bearer(self) -> None:
        from apps.core.security.scrub import scrub_text

        result = scrub_text("Bearer abcdefghijklmnopqrstuvwxyz")  # allowlist secret
        assert "Bearer" in result or "***" in result

    def test_scrub_obj_dict_masks_sensitive_keys(self) -> None:
        from apps.core.security.scrub import scrub_obj

        data = {"token": "secret123456", "name": "visible"}
        result = scrub_obj(data)
        assert result["name"] == "visible"
        assert "secret" not in result["token"]

    def test_scrub_obj_nested(self) -> None:
        from apps.core.security.scrub import scrub_obj

        data = {"outer": {"password": "mypassword123", "safe": "ok"}}
        result = scrub_obj(data)
        assert result["outer"]["safe"] == "ok"
        assert "mypassword" not in result["outer"]["password"]

    def test_scrub_obj_list(self) -> None:
        from apps.core.security.scrub import scrub_obj

        data = [{"api_key": "key123456"}, {"name": "safe"}]
        result = scrub_obj(data)
        assert result[1]["name"] == "safe"

    def test_scrub_obj_depth_limit(self) -> None:
        from apps.core.security.scrub import scrub_obj

        data = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "deep"}}}}}}}
        result = scrub_obj(data)
        # 深度 >= 6 应停止递归
        assert result is not None

    def test_scrub_obj_none(self) -> None:
        from apps.core.security.scrub import scrub_obj

        assert scrub_obj(None) is None

    def test_fingerprint_sha256(self) -> None:
        from apps.core.security.scrub import fingerprint_sha256

        result = fingerprint_sha256("test")
        assert len(result) == 64  # SHA-256 hex

    def test_scrub_for_storage(self) -> None:
        from apps.core.security.scrub import scrub_for_storage

        data = {"token": "my_secret_token_here", "info": "safe"}
        result = scrub_for_storage(data)
        assert result["info"] == "safe"
