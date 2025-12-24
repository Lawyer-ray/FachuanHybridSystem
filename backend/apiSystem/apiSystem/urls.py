"""
URL configuration for apiSystem project.

支持 API 版本控制：
- /api/v1/ - API v1 版本
- /api/ - 重定向到 /api/v1/
"""
from django.contrib import admin
from django.urls import path
from django.http import HttpResponseRedirect
from django.conf import settings
from django.conf.urls.static import static

from .api import api_v1
from apps.organization.views import register

# 配置 Django Admin 界面标题
admin.site.site_header = getattr(settings, 'ADMIN_SITE_HEADER', '法穿案件管理')
admin.site.site_title = getattr(settings, 'ADMIN_SITE_TITLE', '法穿案件管理')
admin.site.index_title = getattr(settings, 'ADMIN_INDEX_TITLE', '欢迎来到法穿案件管理系统')


def api_root_redirect(request):
    """重定向到 API 文档"""
    return HttpResponseRedirect("/api/v1/docs")


def api_redirect(request):
    """将 /api/ 重定向到 /api/v1/"""
    new_path = request.path.replace("/api/", "/api/v1/", 1)
    if request.META.get("QUERY_STRING"):
        new_path += "?" + request.META["QUERY_STRING"]
    return HttpResponseRedirect(new_path)


urlpatterns = [
    path("admin/register/", register, name="admin_register"),  # 注册页面
    path("admin/", admin.site.urls),
    
    # API v1 版本
    path("api/v1/", api_v1.urls),
    
    # /api/ 重定向到 /api/v1/
    path("api/", api_redirect),
    
    # 根路径重定向到 API 文档
    path("", api_root_redirect),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
