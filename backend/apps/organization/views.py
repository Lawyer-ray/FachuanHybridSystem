from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.organization.services.auth.auth_service import AUTO_REGISTER_BOOTSTRAP_USERNAME, AuthService

from .forms import LawyerRegistrationForm

_auth_service = AuthService()


class AuthLoginView(LoginView):
    """自定义登录视图，向模板注入注册所需的上下文。"""

    template_name = "admin/login.html"

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx["is_first_user"] = _auth_service.is_first_user()
        ctx["show_auto_register"] = _auth_service.should_show_auto_register()
        ctx["reg_form"] = kwargs.get("reg_form", LawyerRegistrationForm())
        ctx["show_register"] = False
        return ctx


def register(request: HttpRequest) -> HttpResponse:
    is_first_user = _auth_service.is_first_user()
    show_auto_register = _auth_service.should_show_auto_register()

    if request.method == "POST":
        if request.POST.get("action") == "auto_register":
            try:
                result = _auth_service.auto_register_superadmin()
            except Exception as e:
                messages.error(request, str(e))
                return redirect("admin_register")

            user = result.user
            login(request, user)
            messages.success(
                request,
                _("已自动创建超级管理员账户\u201c%(name)s\u201d，并为您完成登录。")
                % {"name": user.real_name or AUTO_REGISTER_BOOTSTRAP_USERNAME},
            )
            return redirect("admin:index")

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
            else:
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
        "admin/login.html",
        {
            "form": form,
            "reg_form": form,
            "title": _("用户注册"),
            "is_first_user": is_first_user,
            "show_auto_register": show_auto_register,
            "show_register": True,
        },
    )
