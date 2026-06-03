"""
URL configuration for apiSystem project.

支持 API 版本控制：
- /api/v1/ - API v1 版本
- /api/ - 重定向到 /api/v1/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import include, path

from apps.organization.views import register

# Admin 界面自定义（侧边栏排序、Hub 页、工具收藏等）
# 导入即执行 monkey-patch，无需额外调用
from . import admin_customization as _admin_customization
from .api import api_v1


def api_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """将 /api/ 重定向到 /api/v1/"""
    new_path = request.path.replace("/api/", "/api/v1/", 1)
    if request.META.get("QUERY_STRING"):
        new_path += "?" + request.META["QUERY_STRING"]
    return HttpResponseRedirect(new_path)


def favicon_view(request: HttpRequest) -> HttpResponse:
    """返回空的favicon响应，避免404错误"""
    return HttpResponse(status=204)  # No Content


def chrome_devtools_probe_view(request: HttpRequest) -> HttpResponse:
    """返回空响应，避免 Chrome DevTools 探测请求产生 404 日志。"""
    return HttpResponse(status=204)  # No Content


def health_view(request: HttpRequest) -> HttpResponse:
    """健康检查端点，用于 liveness probe"""
    from django.db import connection

    try:
        connection.ensure_connection()
        return HttpResponse("ok")
    except Exception:
        return HttpResponse("db unavailable", status=503)


def index_view(request: HttpRequest) -> HttpResponse:
    """首页视图"""
    return render(request, "index.html")


def root_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """根路径重定向到首页"""
    return HttpResponseRedirect("/index/")


urlpatterns = [
    path("admin/register/", register, name="admin_register"),
    path("admin/cloud-storage/", include("apps.core.cloud_storage.urls")),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/v1/", api_v1.urls),
    path("api/", api_redirect),
    path("favicon.ico", favicon_view, name="favicon"),
    path(".well-known/appspecific/com.chrome.devtools.json", chrome_devtools_probe_view, name="chrome_devtools_probe"),
    path("health/", health_view, name="health"),
    path("index/", index_view, name="index"),
    # 根路径重定向到首页 - 必须在最后
    path("", root_redirect),
]

# 媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
