"""
用户注册视图
"""

from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .forms import LawyerRegistrationForm
from .models import Lawyer


def register(request: HttpRequest) -> HttpResponse:
    """用户注册视图"""
    is_first_user = not Lawyer.objects.exists()

    if request.method == "POST":
        form = LawyerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            if user.is_staff:
                # 第一个用户（管理员）自动登录
                login(request, user)
                messages.success(
                    request, f"注册成功！您是第一个用户，已自动获得管理员权限。欢迎 {user.real_name or user.username}"
                )
                return redirect("admin:index")
            else:
                # 后续用户提示等待审核
                messages.info(request, "注册成功！请等待管理员开通权限后再登录。")
                return redirect("admin:login")
    else:
        form = LawyerRegistrationForm()

    return render(
        request,
        "admin/register.html",
        {
            "form": form,
            "title": "用户注册",
            "is_first_user": is_first_user,
        },
    )
