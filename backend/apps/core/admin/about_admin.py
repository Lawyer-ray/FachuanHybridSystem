from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import path


class AboutAdminView:
    """关于法穿页面视图"""

    @staticmethod
    def about_view(request: HttpRequest) -> TemplateResponse:
        """关于法穿页面"""
        context = {
            "title": "关于法穿",
            "site_header": admin.site.site_header,
            "site_title": admin.site.site_title,
            "has_permission": request.user.is_authenticated,
        }
        return TemplateResponse(request, "admin/core/about.html", context)


def register_about_urls(admin_site: Any) -> None:
    """注册关于页面的 URL"""
    original_get_urls = admin_site.get_urls

    def get_urls() -> Any:
        urls = original_get_urls()
        custom_urls = [
            path("about/", admin_site.admin_view(AboutAdminView.about_view), name="about"),
        ]
        return custom_urls + urls

    admin_site.get_urls = get_urls


# 注册 URL
register_about_urls(admin.site)
