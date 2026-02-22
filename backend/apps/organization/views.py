from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import PermissionDenied
from apps.organization.services.auth_service import AuthService

from .forms import LawyerRegistrationForm


def register(request: HttpRequest) -> HttpResponse:
    """用户注册视图"""
    auth_service = AuthService()
    is_first_user = auth_service.is_first_user()

    if request.method == "POST":
        form = LawyerRegistrationForm(request.POST)
        if form.is_valid():
            username: str = form.cleaned_data["username"]
            password: str = form.cleaned_data["password1"]
            bootstrap_token: str | None = form.cleaned_data.get("bootstrap_token") or None
            try:
                result = auth_service.register(
                    username=username,
                    password=password,
                    real_name=username,
                    bootstrap_token=bootstrap_token,
                )
            except PermissionDenied as e:
                messages.error(request, str(e.message))
                return render(
                    request,
                    "admin/register.html",
                    {"form": form, "title": _("用户注册"), "is_first_user": is_first_user},
                )
            user = result.user
            if user.is_admin:
                login(request, user)
                messages.success(
                    request,
                    _("注册成功！您是第一个用户，已自动获得管理员权限。欢迎 %(name)s") % {"name": user.real_name or user.username},
                )
                return redirect("admin:index")
            else:
                messages.info(request, _("注册成功！请等待管理员开通权限后再登录。"))
                return redirect("admin:login")
    else:
        form = LawyerRegistrationForm()

    return render(
        request,
        "admin/register.html",
        {
            "form": form,
            "title": _("用户注册"),
            "is_first_user": is_first_user,
        },
    )
