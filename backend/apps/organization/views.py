from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.organization.services.auth_service import AuthService

from .forms import LawyerRegistrationForm

_auth_service = AuthService()


def register(request: HttpRequest) -> HttpResponse:
    is_first_user = _auth_service.is_first_user()

    if request.method == "POST":
        form = LawyerRegistrationForm(request.POST)
        if form.is_valid():
            username: str = form.cleaned_data["username"]
            password: str = form.cleaned_data["password1"]
            try:
                result = _auth_service.register(
                    username=username,
                    password=password,
                    real_name=username,
                )
            except Exception as e:
                messages.error(request, str(e))
            user = result.user
            if user.is_admin:
                login(request, user)
                messages.success(
                    request,
                    _("注册成功！您是第一个用户，已自动获得管理员权限。欢迎 %(name)s")
                    % {"name": user.real_name or user.username},
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
