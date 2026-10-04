from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.organization.services.auth.auth_service import AUTO_REGISTER_BOOTSTRAP_USERNAME, AuthService

from .forms import LawyerRegistrationForm

_auth_service = AuthService()


class AuthLoginView(LoginView):
    """自定义登录视图，向模板注入注册所需的上下文。"""

    template_name = "admin/login.html"
    # 安全审计：/admin/login/ 必须沿用 admin 口径的认证表单——
    # AdminAuthenticationForm 会拒绝非 is_staff 用户，避免此表单沦为
    # 非 staff 账号的密码验证预言机（自定义视图默认用 AuthenticationForm，
    # 只验密码不验 staff 身份）。
    authentication_form = AdminAuthenticationForm

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

    if request.method == "POST" and request.POST.get("action") == "auto_register":
        # BOOTSTRAP 自动注册分支不受 ALLOW_ADMIN_REGISTER 开关影响：
        # 首用户引导依赖它（生产环境由 BOOTSTRAP_ADMIN_TOKEN 保护，安全审计 C-02）
        return _handle_auto_register(request)

    # 安全审计：ALLOW_ADMIN_REGISTER（默认 False）接线——关闭时表单注册入口
    # 直接拒绝，不再渲染/接受注册表单
    if not getattr(settings, "ALLOW_ADMIN_REGISTER", False):
        messages.error(request, "注册入口未开放，请联系管理员创建账号")
        return redirect("admin:login")

    if request.method != "POST":
        return render(
            request,
            "admin/login.html",
            {
                "form": LawyerRegistrationForm(),
                "reg_form": LawyerRegistrationForm(),
                "title": "用户注册",
                "is_first_user": is_first_user,
                "show_auto_register": show_auto_register,
                "show_register": True,
            },
        )

    form = LawyerRegistrationForm(request.POST)
    if form.is_valid():
        return _handle_form_register(request, form)

    return render(
        request,
        "admin/login.html",
        {
            "form": form,
            "reg_form": form,
            "title": "用户注册",
            "is_first_user": is_first_user,
            "show_auto_register": show_auto_register,
            "show_register": True,
        },
    )


def _handle_auto_register(request: HttpRequest) -> HttpResponse:
    # 安全审计 C-02：生产环境自动注册同样需要 BOOTSTRAP_ADMIN_TOKEN，
    # 否则清库/新部署窗口内任何人可用源码中的硬编码口令抢占超管。
    from hmac import compare_digest

    from django.conf import settings as dj_settings

    if not getattr(dj_settings, "DEBUG", False):
        expected_token = str(getattr(dj_settings, "BOOTSTRAP_ADMIN_TOKEN", "") or "").strip()
        provided_token = str(request.POST.get("bootstrap_token", "") or "").strip()
        if not expected_token or not compare_digest(provided_token, expected_token):
            messages.error(request, "自动注册仅在开发环境开放；生产环境需提供有效引导令牌")
            return redirect("admin_register")

    try:
        result = _auth_service.auto_register_superadmin()
    except Exception as e:
        messages.error(request, str(e))
        return redirect("admin_register")

    user = result.user
    login(request, user)
    messages.success(
        request,
        "已自动创建超级管理员账户“%(name)s”，并为您完成登录。"
        % {"name": user.real_name or AUTO_REGISTER_BOOTSTRAP_USERNAME},
    )
    return redirect("admin:index")


def _handle_form_register(request: HttpRequest, form: LawyerRegistrationForm) -> HttpResponse:
    username: str = form.cleaned_data["username"]
    password: str = form.cleaned_data["password1"]
    try:
        result = _auth_service.register(username=username, password=password, real_name=username)
    except Exception as e:
        messages.error(request, str(e))
        return redirect("admin_register")

    user = result.user
    if user.is_admin:
        login(request, user)
        messages.success(
            request,
            "注册成功！您是第一个用户，已自动获得管理员权限。系统正在初始化中... %(name)s"
            % {"name": user.real_name or user.username},
        )
        return redirect("admin:index")

    messages.info(request, "注册成功！请等待管理员开通权限后再登录。")
    return redirect("admin:login")
