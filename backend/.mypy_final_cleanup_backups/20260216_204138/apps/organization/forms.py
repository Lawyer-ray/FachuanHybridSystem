"""
用户注册表单
"""

import re
from typing import Any

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Lawyer


class LawyerRegistrationForm(UserCreationForm):
    """律师注册表单"""

    class Meta:
        model = Lawyer
        fields = ("username", "password1", "password2")

    def __init__(self, *args, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": "form-input", "placeholder": "请输入中文姓名"})
        self.fields["password1"].widget.attrs.update({"class": "form-input", "placeholder": "请输入密码"})
        self.fields["password2"].widget.attrs.update({"class": "form-input", "placeholder": "请确认密码"})
        self.fields["username"].label = "用户名/真实姓名"
        self.fields["password1"].label = "密码"
        self.fields["password2"].label = "确认密码"
        self.fields["username"].help_text = "只能输入中文"
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

    def _is_first_user(self) -> bool:
        """检查是否为第一个注册的用户"""
        return not Lawyer.objects.exists()

    def clean_username(self) -> Any:
        """验证用户名必须是中文"""
        username = self.cleaned_data.get("username")
        if username:
            if not re.match("^[\\u4e00-\\u9fa5]+$", username):
                raise ValidationError("用户名只能输入中文")
        return username

    def save(self, commit: Any = True) -> Any:
        """保存用户，根据是否为第一个用户设置权限"""
        user = super().save(commit=False)
        user.real_name = user.username
        if self._is_first_user():
            user.is_staff = True
            user.is_superuser = True
            user.is_admin = True
        else:
            user.is_staff = False
            user.is_superuser = False
            user.is_admin = False
            user.is_active = True
        if commit:
            user.save()
        return user
