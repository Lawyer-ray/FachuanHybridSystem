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
from django.utils.translation import gettext_lazy as _

from apps.organization.views import register

from .api import api_v1

# 配置 Django Admin 界面标题
admin.site.site_header = _(getattr(settings, "ADMIN_SITE_HEADER", "法穿AI案件管理系统"))
admin.site.site_title = _(getattr(settings, "ADMIN_SITE_TITLE", "法穿AI案件管理系统"))
admin.site.index_title = _(getattr(settings, "ADMIN_INDEX_TITLE", "欢迎来到法穿AI案件管理系统"))


def index_view(request: HttpRequest) -> HttpResponse:
    """首页视图"""
    return render(request, "index.html")


def root_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """根路径重定向到首页"""
    return HttpResponseRedirect("/index/")


def api_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """将 /api/ 重定向到 /api/v1/"""
    new_path = request.path.replace("/api/", "/api/v1/", 1)
    if request.META.get("QUERY_STRING"):
        new_path += "?" + request.META["QUERY_STRING"]
    return HttpResponseRedirect(new_path)


def favicon_view(request: HttpRequest) -> HttpResponse:
    """返回空的favicon响应，避免404错误"""
    return HttpResponse(status=204)  # No Content


urlpatterns = [
    path("admin/register/", register, name="admin_register"),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("onboarding/", include("apps.onboarding.urls")),
    path("api/v1/", api_v1.urls),
    path("api/", api_redirect),
    path("favicon.ico", favicon_view, name="favicon"),
    path("index/", index_view, name="index"),
    # 根路径重定向到首页 - 必须在最后
    path("", root_redirect),
]

# 媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
