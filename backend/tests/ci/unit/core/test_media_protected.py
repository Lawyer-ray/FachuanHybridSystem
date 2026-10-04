"""受保护 media 下载视图单测。

覆盖 ``apps/core/api/media_protected.py`` 与 ``apiSystem/urls.py`` 的媒体路由逻辑：

1. 默认关闭时行为不变：``MEDIA_REQUIRE_AUTH`` 默认 False，urlpatterns 不含鉴权视图，
   ``media_urlpatterns()`` 返回空；
2. DEBUG 分支保持：仍返回 static 直出路由（不接管）；
3. 开启后：未认证 403；带合法用户 200（小文件流式返回）；
4. 路径穿越拒绝：``../`` 越界与绝对路径越界均 404；
5. X-Accel 模式：返回 ``X-Accel-Redirect`` 头且**不读文件**（不存在的文件也返回 200）；
6. ``?token=`` 查询参数认证（JWTOrSessionAuth 的 window.open 下载场景）。
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import RequestFactory, override_settings

from apiSystem.urls import media_urlpatterns
from apps.core.api.media_protected import serve_protected_media
from apps.organization.models import LawFirm, Lawyer

SAMPLE_REL = "test_media_protected/sample.txt"
SAMPLE_CONTENT = b"protected-media-sample"


# ── Fixtures / Helpers ────────────────────────────────────────────────────────


@pytest.fixture
def media_user(db: Any) -> Any:
    """已认证律师（普通用户即可——视图只校验身份，不校验权限）。"""
    firm = LawFirm.objects.create(name=f"媒体鉴权测试律所-{Lawyer.objects.count()}")
    return Lawyer.objects.create_user(
        username=f"media_protected_{Lawyer.objects.count()}",
        password="testpass123",  # pragma: allowlist secret
        law_firm=firm,
    )


@pytest.fixture
def media_root(tmp_path: Any) -> Any:
    """隔离的 MEDIA_ROOT，内含一个小样例文件（经 default_storage 落盘）。"""
    media = tmp_path / "media"
    with override_settings(MEDIA_ROOT=str(media)):
        default_storage.save(SAMPLE_REL, ContentFile(SAMPLE_CONTENT))
        yield media


def _get(path: str = SAMPLE_REL, user: Any = None, query: dict[str, str] | None = None) -> Any:
    """构造直接打到视图的 GET request（绕过 URL 路由；path 即视图收到的捕获参数）。"""
    request = RequestFactory().get("/media/", data=query or {})
    if user is not None:
        request.user = user
    return serve_protected_media(request, path)


# ── 1. 默认关闭：行为不变 ────────────────────────────────────────────────────


class TestDefaultOff:
    def test_setting_default_false_when_env_unset(self, monkeypatch: Any) -> None:
        monkeypatch.delenv("MEDIA_REQUIRE_AUTH", raising=False)
        expected = os.environ.get("MEDIA_REQUIRE_AUTH", "false").lower() in ("1", "true", "yes")
        assert expected is False
        assert settings.MEDIA_REQUIRE_AUTH is expected

    def test_no_urlpatterns_when_require_auth_off(self) -> None:
        with override_settings(DEBUG=False, MEDIA_REQUIRE_AUTH=False):
            assert media_urlpatterns() == []

    def test_project_urlpatterns_exclude_protected_view_when_off(self) -> None:
        """默认关闭时，项目 urlpatterns 不注册 serve_protected_media（现状零变化）。"""
        if settings.MEDIA_REQUIRE_AUTH:
            pytest.skip("MEDIA_REQUIRE_AUTH 环境变量已显式开启，跳过默认关闭断言")
        from apiSystem import urls as project_urls

        callbacks = [getattr(p, "callback", None) for p in project_urls.urlpatterns]
        assert serve_protected_media not in callbacks


# ── 2. DEBUG 分支保持 ────────────────────────────────────────────────────────


class TestDebugBranchUnchanged:
    def test_debug_returns_static_serve(self) -> None:
        from django.views.static import serve

        with override_settings(DEBUG=True):
            patterns = media_urlpatterns()
        assert patterns, "DEBUG 分支应继续注册媒体/静态路由"
        assert any(getattr(p, "callback", None) is serve for p in patterns)


# ── 3. 开启后：认证与文件返回 ────────────────────────────────────────────────


class TestServeProtectedMedia:
    def test_unauthenticated_403(self, media_root: Any) -> None:
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get(SAMPLE_REL)
        assert response.status_code == 403
        # 403 响应不携带任何路径/文件信息（不泄露路径有效性）
        assert response.content == b""

    def test_authenticated_200_small_file(self, media_root: Any, media_user: Any) -> None:
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get(SAMPLE_REL, user=media_user)
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == SAMPLE_CONTENT

    def test_session_user_via_query_token_200(self, media_root: Any, media_user: Any) -> None:
        """``?token=`` 查询参数携带 JWT（window.open 下载场景）应认证通过。"""
        from ninja_jwt.tokens import AccessToken

        token = str(AccessToken.for_user(media_user))  # type: ignore[misc]
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get(SAMPLE_REL, query={"token": token})
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == SAMPLE_CONTENT

    def test_invalid_query_token_403(self, media_root: Any) -> None:
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get(SAMPLE_REL, query={"token": "not-a-jwt"})
        assert response.status_code == 403
        # 无效 token 与未认证一样：403 且不泄露路径有效性
        assert response.content == b""

    def test_post_method_405(self, media_root: Any, media_user: Any) -> None:
        request = RequestFactory().post("/media/")
        request.user = media_user
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = serve_protected_media(request, SAMPLE_REL)
        assert response.status_code == 405
        # require_http_methods 应声明允许 GET/HEAD
        assert "GET" in response["Allow"]
        assert "HEAD" in response["Allow"]


# ── 4. 路径穿越拒绝 ──────────────────────────────────────────────────────────


class TestPathTraversal:
    def test_dotdot_traversal_404(self, media_root: Any, media_user: Any) -> None:
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get("../../etc/passwd", user=media_user)
        assert response.status_code == 404
        # 穿越拒绝响应不含任何回显（不泄露被拒绝的目标路径）
        assert response.content == b""

    def test_absolute_outside_root_404(self, media_root: Any, media_user: Any) -> None:
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get("/etc/passwd", user=media_user)
        assert response.status_code == 404
        assert response.content == b""

    def test_missing_file_inside_root_404(self, media_root: Any, media_user: Any) -> None:
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get("test_media_protected/missing.txt", user=media_user)
        assert response.status_code == 404
        assert response.content == b""

    def test_empty_path_404(self, media_root: Any, media_user: Any) -> None:
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get("", user=media_user)
        assert response.status_code == 404
        assert response.content == b""


# ── 5. X-Accel 模式 ─────────────────────────────────────────────────────────


class TestXAccelMode:
    def test_header_set_and_file_not_read(self, media_root: Any, media_user: Any) -> None:
        """X-Accel 模式只返回响应头，不读文件——磁盘上不存在的文件也返回 200。"""
        ghost = "test_media_protected/ghost.pdf"
        with override_settings(MEDIA_REQUIRE_AUTH=True, MEDIA_X_ACCEL_PREFIX="/protected_media/"):
            response = _get(ghost, user=media_user)
        assert response.status_code == 200
        assert response["X-Accel-Redirect"] == "/protected_media/test_media_protected/ghost.pdf"
        assert response["Content-Type"] == "application/pdf"
        assert not response.content  # 不读文件、无响应体

    def test_accel_redirect_quotes_unsafe_chars(self, media_root: Any, media_user: Any) -> None:
        with override_settings(MEDIA_REQUIRE_AUTH=True, MEDIA_X_ACCEL_PREFIX="/protected_media"):
            response = _get("test dir/a b.pdf?q=1", user=media_user)
        assert response["X-Accel-Redirect"] == "/protected_media/test%20dir/a%20b.pdf%3Fq%3D1"


# ── 6. 开启后的路由注册 ──────────────────────────────────────────────────────


class TestRequireAuthOn:
    def test_urlpatterns_route_to_protected_view(self) -> None:
        with override_settings(DEBUG=False, MEDIA_REQUIRE_AUTH=True):
            patterns = media_urlpatterns()
        assert len(patterns) == 1
        assert patterns[0].callback is serve_protected_media
