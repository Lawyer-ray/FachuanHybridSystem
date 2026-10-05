"""passkey_service 单元测试。

覆盖：Origin→rp_id 白名单校验矩阵、挑战会话（单次使用/TTL/环境绑定）、
注册 ceremony（成功/跨账号/环境变化/库异常/重复凭据）、登录 ceremony
（成功铸 token/重放/签名计数回退/免计数认证器/未激活/未知凭据）。

py_webauthn 的两个 verify 函数全程 mock（浏览器 ceremony 无法在 CI 里真实重放，
密码学部分信任库本身，本文件只验证我们自己的编排与防护逻辑）。
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpRequest
from django.test import RequestFactory
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse

from apps.organization.models import Lawyer
from apps.social_auth.models import PasskeyCredential
from apps.social_auth.services.passkey_service import (
    _LOGIN_KEY,
    _REGISTER_KEY,
    PasskeyError,
    build_login_options,
    build_registration_options,
    resolve_rp_context,
    verify_login,
    verify_registration,
)

pytestmark = pytest.mark.django_db

_LOOPBACK_ORIGIN = "http://localhost:5199"


def _make_request(origin: str = _LOOPBACK_ORIGIN) -> HttpRequest:
    """带 Origin 头与空 session 的请求（服务是同步的，直接构造即可）。"""
    request = RequestFactory().post("/api/v1/social/passkey/login/options", HTTP_ORIGIN=origin)
    store = SessionStore()
    # 测试内 session 只在内存读写，直接标记为已加载，不触库
    store._session_cache = {}
    request.session = store
    return request


@pytest.fixture(autouse=True)
def _passkey_env(settings: Any) -> Any:
    """通行密钥校验所需的统一环境：DEBUG 回环放行 + 显式白名单。"""
    settings.DEBUG = True
    settings.CORS_ALLOWED_ORIGINS = [_LOOPBACK_ORIGIN]
    settings.CSRF_TRUSTED_ORIGINS = [_LOOPBACK_ORIGIN]
    settings.FRONTEND_BASE_URL = _LOOPBACK_ORIGIN


@pytest.fixture
def user() -> Lawyer:
    return Lawyer.objects.create(
        username="pk-user",
        real_name="张三",
        password=make_password("old-password-123"),
    )


class TestResolveRpContext:
    """Origin → rp_id 校验矩阵。"""

    def test_debug_loopback_any_port(self, settings: Any) -> None:
        settings.DEBUG = True
        ctx = resolve_rp_context("http://127.0.0.1:8123")
        assert ctx.rp_id == "127.0.0.1"
        assert ctx.origin == "http://127.0.0.1:8123"

    def test_debug_loopback_ipv6(self, settings: Any) -> None:
        settings.DEBUG = True
        ctx = resolve_rp_context("http://[::1]:5199")
        assert ctx.rp_id == "::1"
        assert ctx.origin == "http://[::1]:5199"

    def test_allowlist_exact_match_without_debug(self, settings: Any) -> None:
        settings.DEBUG = False
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5090"]
        settings.CSRF_TRUSTED_ORIGINS = []
        settings.FRONTEND_BASE_URL = "http://localhost:5090"
        ctx = resolve_rp_context("http://localhost:5090")
        assert ctx.rp_id == "localhost"

    def test_allowlist_trailing_slash_normalized(self, settings: Any) -> None:
        settings.DEBUG = False
        settings.CORS_ALLOWED_ORIGINS = ["https://app.xlaw.top/"]
        settings.CSRF_TRUSTED_ORIGINS = []
        settings.FRONTEND_BASE_URL = ""
        ctx = resolve_rp_context("https://app.xlaw.top")
        assert ctx.rp_id == "app.xlaw.top"
        assert ctx.origin == "https://app.xlaw.top"

    def test_default_port_normalized(self, settings: Any) -> None:
        settings.DEBUG = False
        settings.CORS_ALLOWED_ORIGINS = ["https://app.xlaw.top:443"]
        settings.CSRF_TRUSTED_ORIGINS = []
        settings.FRONTEND_BASE_URL = ""
        ctx = resolve_rp_context("https://app.xlaw.top")
        assert ctx.rp_id == "app.xlaw.top"

    def test_rejects_loopback_port_not_allowlisted_without_debug(self, settings: Any) -> None:
        settings.DEBUG = False
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5090"]
        settings.CSRF_TRUSTED_ORIGINS = []
        settings.FRONTEND_BASE_URL = ""
        with pytest.raises(PasskeyError):
            resolve_rp_context(_LOOPBACK_ORIGIN)

    def test_rejects_http_non_loopback(self, settings: Any) -> None:
        settings.DEBUG = True
        with pytest.raises(PasskeyError, match="HTTPS"):
            resolve_rp_context("http://app.xlaw.top")

    def test_rejects_unknown_domain_even_https(self, settings: Any) -> None:
        settings.DEBUG = False
        settings.CORS_ALLOWED_ORIGINS = []
        settings.CSRF_TRUSTED_ORIGINS = []
        settings.FRONTEND_BASE_URL = ""
        with pytest.raises(PasskeyError, match="白名单"):
            resolve_rp_context("https://evil.example.com")

    @pytest.mark.parametrize("origin", ["", "ftp://localhost:5199", "http://", "not-a-url"])
    def test_rejects_malformed_origins(self, settings: Any, origin: str) -> None:
        settings.DEBUG = True
        with pytest.raises(PasskeyError):
            resolve_rp_context(origin)


class TestChallengeLifecycle:
    """挑战：单次使用 + TTL。"""

    def test_challenge_single_use(self) -> None:
        request = _make_request()
        payload = build_login_options(request)
        # 认证选项的 rp 字段是扁平的 rpId（注册选项才是 rp: {id, name}）
        assert payload["public_key"]["rpId"] == "localhost"
        assert payload["public_key"]["challenge"]

        stored = request.session.pop(_LOGIN_KEY)
        assert stored["rp_id"] == "localhost"
        # 读即删：再取就没了（重放直接失败）。pop 提到 assert 外：
        # assert 有副作用会被 python -O 静默跳过，CodeQL py/side-effect-in-assert
        replay = request.session.pop(_LOGIN_KEY, None)
        assert replay is None

    def test_expired_challenge_rejected(self) -> None:
        from apps.social_auth.services.passkey_service import _pop_challenge

        request = _make_request()
        build_login_options(request)
        request.session[_LOGIN_KEY]["created_at"] = time.time() - 400
        with pytest.raises(PasskeyError, match="过期"):
            _pop_challenge(request, _LOGIN_KEY)


class TestVerifyRegistration:
    def test_success_creates_credential(self, user: Lawyer) -> None:
        request = _make_request()
        build_registration_options(request, user)
        verified = SimpleNamespace(
            credential_id=b"\x01" * 32,
            credential_public_key=b"pubkey-bytes",
            sign_count=1,
            credential_backed_up=True,
        )
        with patch("apps.social_auth.services.passkey_service.verify_registration_response", return_value=verified):
            row = verify_registration(request, user, name="我的Mac", credential={"id": "x"})

        assert row.user_id == user.id
        assert row.credential_id == bytes_to_base64url(b"\x01" * 32)
        assert row.public_key == bytes_to_base64url(b"pubkey-bytes")
        assert row.rp_id == "localhost"
        assert row.backed_up is True
        assert row.sign_count == 1
        # 挑战已消费（pop 提到 assert 外，同 py/side-effect-in-assert）
        leftover = request.session.pop(_REGISTER_KEY, None)
        assert leftover is None

    def test_cross_user_challenge_rejected(self, user: Lawyer) -> None:
        other = Lawyer.objects.create(username="pk-other")
        request = _make_request()
        build_registration_options(request, user)  # 挑战绑定 user
        with pytest.raises(PasskeyError, match="不匹配"):
            verify_registration(request, other, name="", credential={"id": "x"})  # 另一人提交
        assert not PasskeyCredential.objects.exists()

    def test_environment_change_rejected(self, user: Lawyer) -> None:
        request = _make_request()
        build_registration_options(request, user)
        # 保留同一 session、换 Origin 头 → 推导出的环境与 session 里存的不一致
        request2 = _make_request(origin="http://127.0.0.1:5199")
        request2.session = request.session
        with (
            patch("apps.social_auth.services.passkey_service.verify_registration_response"),
            pytest.raises(PasskeyError, match="环境"),
        ):
            verify_registration(request2, user, name="", credential={"id": "x"})

    def test_library_failure_returns_generic_error(self, user: Lawyer) -> None:
        request = _make_request()
        build_registration_options(request, user)
        with (
            patch(
                "apps.social_auth.services.passkey_service.verify_registration_response",
                side_effect=InvalidRegistrationResponse("bad attestation"),
            ),
            pytest.raises(PasskeyError, match="校验失败"),
        ):
            verify_registration(request, user, name="", credential={"id": "x"})

    def test_duplicate_credential_rejected(self, user: Lawyer) -> None:
        from django.db import IntegrityError

        request = _make_request()
        build_registration_options(request, user)
        verified = SimpleNamespace(
            credential_id=b"\x02" * 32,
            credential_public_key=b"pk",
            sign_count=0,
            credential_backed_up=False,
        )
        with (
            patch(
                "apps.social_auth.services.passkey_service.verify_registration_response",
                return_value=verified,
            ),
            patch.object(PasskeyCredential.objects, "create", side_effect=IntegrityError),
            pytest.raises(PasskeyError, match="已经注册"),
        ):
            verify_registration(request, user, name="", credential={"id": "x"})

    def test_name_defaults_and_trims(self, user: Lawyer) -> None:
        request = _make_request()
        build_registration_options(request, user)
        verified = SimpleNamespace(
            credential_id=b"\x03" * 32,
            credential_public_key=b"pk",
            sign_count=0,
            credential_backed_up=False,
        )
        with patch("apps.social_auth.services.passkey_service.verify_registration_response", return_value=verified):
            row = verify_registration(request, user, name="   ", credential={"id": "x"})
        assert row.name == "通行密钥"

        request2 = _make_request()
        build_registration_options(request2, user)
        verified.credential_id = b"\x04" * 32
        with patch("apps.social_auth.services.passkey_service.verify_registration_response", return_value=verified):
            row2 = verify_registration(request2, user, name="长" * 120, credential={"id": "x"})
        assert len(row2.name) == 100


class TestVerifyLogin:
    def _seed_credential(self, user: Lawyer, sign_count: int = 5) -> PasskeyCredential:
        return PasskeyCredential.objects.create(
            user=user,
            name="测试密钥",
            credential_id="test-credential-id",
            public_key=bytes_to_base64url(b"public-key"),
            sign_count=sign_count,
            rp_id="localhost",
        )

    def test_success_mints_bound_tokens(self, user: Lawyer) -> None:
        from ninja_jwt.tokens import RefreshToken

        from apps.core.security.jwt_password_binding import PWD_VER_CLAIM, password_fingerprint

        cred = self._seed_credential(user)
        request = _make_request()
        build_login_options(request)
        verified = SimpleNamespace(new_sign_count=6)
        with patch(
            "apps.social_auth.services.passkey_service.verify_authentication_response",
            return_value=verified,
        ):
            result = verify_login(request, {"id": cred.credential_id, "response": {}})

        assert result.success is True
        assert result.user_id == user.id
        assert result.username == user.username
        # refresh 绑定密码指纹（与社交登录同口径）
        refresh = RefreshToken(result.refresh)
        assert refresh.payload[PWD_VER_CLAIM] == password_fingerprint(user)
        # 计数器与最近使用时间已更新
        cred.refresh_from_db()
        assert cred.sign_count == 6
        assert cred.last_used_at is not None

    def test_challenge_replay_rejected(self, user: Lawyer) -> None:
        cred = self._seed_credential(user)
        request = _make_request()
        build_login_options(request)
        verified = SimpleNamespace(new_sign_count=6)
        with patch(
            "apps.social_auth.services.passkey_service.verify_authentication_response",
            return_value=verified,
        ):
            verify_login(request, {"id": cred.credential_id, "response": {}})
        # 同一挑战重放 → 会话已弹出，直接失败
        with pytest.raises(PasskeyError, match="过期"):
            verify_login(request, {"id": cred.credential_id, "response": {}})

    def test_sign_count_rollback_rejected(self, user: Lawyer) -> None:
        cred = self._seed_credential(user, sign_count=10)
        request = _make_request()
        build_login_options(request)
        verified = SimpleNamespace(new_sign_count=9)
        with (
            patch(
                "apps.social_auth.services.passkey_service.verify_authentication_response",
                return_value=verified,
            ),
            pytest.raises(PasskeyError, match="校验失败"),
        ):
            verify_login(request, {"id": cred.credential_id, "response": {}})
        cred.refresh_from_db()
        assert cred.sign_count == 10  # 计数器不被污染

    def test_counterless_authenticator_allowed(self, user: Lawyer) -> None:
        cred = self._seed_credential(user, sign_count=0)
        request = _make_request()
        build_login_options(request)
        verified = SimpleNamespace(new_sign_count=0)
        with patch(
            "apps.social_auth.services.passkey_service.verify_authentication_response",
            return_value=verified,
        ):
            result = verify_login(request, {"id": cred.credential_id, "response": {}})
        assert result.success is True

    def test_inactive_user_rejected(self, user: Lawyer) -> None:
        cred = self._seed_credential(user)
        Lawyer.objects.filter(pk=user.pk).update(is_active=False)
        request = _make_request()
        build_login_options(request)
        with pytest.raises(PasskeyError, match="未激活"):
            verify_login(request, {"id": cred.credential_id, "response": {}})

    def test_unknown_credential_rejected(self) -> None:
        request = _make_request()
        build_login_options(request)
        with pytest.raises(PasskeyError):
            verify_login(request, {"id": "no-such-credential", "response": {}})

    def test_missing_credential_id_rejected(self) -> None:
        request = _make_request()
        build_login_options(request)
        with pytest.raises(PasskeyError):
            verify_login(request, {"response": {}})

    def test_library_failure_generic_error(self, user: Lawyer) -> None:
        cred = self._seed_credential(user)
        request = _make_request()
        build_login_options(request)
        with (
            patch(
                "apps.social_auth.services.passkey_service.verify_authentication_response",
                side_effect=InvalidAuthenticationResponse("bad signature"),
            ),
            pytest.raises(PasskeyError, match="校验失败"),
        ):
            verify_login(request, {"id": cred.credential_id, "response": {}})
