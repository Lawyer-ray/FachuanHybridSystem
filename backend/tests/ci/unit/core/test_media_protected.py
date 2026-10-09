"""受保护 media 下载视图单测。

覆盖 ``apps/core/api/media_protected.py`` 与 ``apiSystem/urls.py`` 的媒体路由逻辑：

1. 默认启用（安全默认）：``MEDIA_REQUIRE_AUTH`` 默认 True，非 DEBUG 下注册鉴权视图；
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
from apps.core.security.download_tickets import issue_download_ticket
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


# ── 1. 默认启用（安全默认）+ 显式关闭回退 ──────────────────────────────────


class TestDefaultOn:
    def test_setting_default_true_when_env_unset(self, monkeypatch: Any) -> None:
        monkeypatch.delenv("MEDIA_REQUIRE_AUTH", raising=False)
        assert settings.MEDIA_REQUIRE_AUTH is True

    def test_setting_explicitly_disabled(self, monkeypatch: Any) -> None:
        # settings 常量在启动时已求值，这里验证的是 env 覆盖语义：
        # 显式 false 时该表达式（settings.py 同款写法）求值为 False
        monkeypatch.setenv("MEDIA_REQUIRE_AUTH", "false")
        resolved = os.environ.get("MEDIA_REQUIRE_AUTH", "true").lower() in ("1", "true", "yes")
        assert resolved is False

    def test_urlpatterns_register_protected_view_by_default(self) -> None:
        with override_settings(DEBUG=False, MEDIA_REQUIRE_AUTH=True):
            patterns = media_urlpatterns()
        assert patterns, "非 DEBUG 默认应注册鉴权媒体路由"
        assert all(getattr(p, "callback", None) is serve_protected_media for p in patterns)

    def test_no_urlpatterns_when_require_auth_explicitly_off(self) -> None:
        with override_settings(DEBUG=False, MEDIA_REQUIRE_AUTH=False):
            assert media_urlpatterns() == []

    def test_project_urlpatterns_exclude_protected_view_when_off(self) -> None:
        """显式关闭时，项目 urlpatterns 不注册 serve_protected_media（旧行为）。"""
        if settings.MEDIA_REQUIRE_AUTH:
            pytest.skip("MEDIA_REQUIRE_AUTH 环境变量已显式开启，跳过关闭断言")
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

    def test_download_ticket_200(self, media_root: Any, media_user: Any) -> None:
        """``?ticket=`` 短时票据应认证通过（M-2 后 JWT 退出 query 的替代路径）。"""
        ticket = issue_download_ticket(media_user.id, resource=f"media:{SAMPLE_REL}")
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get(SAMPLE_REL, query={"ticket": ticket})
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == SAMPLE_CONTENT

    def test_jwt_in_query_is_rejected_403(self, media_root: Any, media_user: Any) -> None:
        """M-2 红线：``?token=<JWT>`` 必须不再被接受——否则完整 JWT 会进 access log。"""
        from ninja_jwt.tokens import AccessToken

        token = str(AccessToken.for_user(media_user))  # type: ignore[misc]
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get(SAMPLE_REL, query={"token": token})
        assert response.status_code == 403
        assert response.content == b""

    def test_invalid_query_ticket_403(self, media_root: Any) -> None:
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get(SAMPLE_REL, query={"ticket": "not-a-ticket"})
        assert response.status_code == 403
        # 无效票据与未认证一样：403 且不泄露路径有效性
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


# ── 5b. 危险类型强制附件下载（防 /media/ 直链同源 XSS） ────────────────────────


class TestDangerousTypeForceDownload:
    """html/svg/xml/js 等可执行类型经 /media/ 直链返回时必须强制附件下载。"""

    def _save(self, rel: str) -> None:
        default_storage.save(rel, ContentFile(b"<html><script>alert(1)</script></html>"))

    def test_html_forced_to_attachment(self, media_root: Any, media_user: Any) -> None:
        self._save("test_media_protected/evil.html")
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get("test_media_protected/evil.html", user=media_user)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/octet-stream"
        assert response["Content-Disposition"].startswith("attachment")
        assert b"".join(response.streaming_content)

    def test_svg_forced_to_attachment(self, media_root: Any, media_user: Any) -> None:
        self._save("test_media_protected/evil.svg")
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get("test_media_protected/evil.svg", user=media_user)
        assert response["Content-Type"] == "application/octet-stream"
        assert response["Content-Disposition"].startswith("attachment")

    def test_js_forced_to_attachment(self, media_root: Any, media_user: Any) -> None:
        self._save("test_media_protected/evil.js")
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get("test_media_protected/evil.js", user=media_user)
        assert response["Content-Type"] == "application/octet-stream"
        assert response["Content-Disposition"].startswith("attachment")

    def test_safe_type_kept_inline_without_forced_download(self, media_root: Any, media_user: Any) -> None:
        """普通类型不强制下载：Content-Type 原样、不出现 attachment。"""
        with override_settings(MEDIA_REQUIRE_AUTH=True):
            response = _get(SAMPLE_REL, user=media_user)
        assert response["Content-Type"] == "text/plain"
        assert not str(response.get("Content-Disposition", "")).startswith("attachment")

    def test_xaccel_mode_also_forces_download_headers(self, media_root: Any, media_user: Any) -> None:
        """X-Accel 模式下同样下发 octet-stream + attachment 头（nginx 沿用后端头）。"""
        self._save("test_media_protected/evil.html")
        with override_settings(MEDIA_REQUIRE_AUTH=True, MEDIA_X_ACCEL_PREFIX="/protected_media/"):
            response = _get("test_media_protected/evil.html", user=media_user)
        assert response["Content-Type"] == "application/octet-stream"
        assert response["Content-Disposition"].startswith("attachment")
        assert "evil.html" in response["Content-Disposition"]


# ── 6. 开启后的路由注册 ──────────────────────────────────────────────────────


class TestRequireAuthOn:
    def test_urlpatterns_route_to_protected_view(self) -> None:
        with override_settings(DEBUG=False, MEDIA_REQUIRE_AUTH=True):
            patterns = media_urlpatterns()
        assert len(patterns) == 1
        assert patterns[0].callback is serve_protected_media
