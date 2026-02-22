"""
用户注册表单
"""

from __future__ import annotations

import re
from typing import Any

from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Lawyer


class LawyerRegistrationForm(UserCreationForm[Lawyer]):
    """律师注册表单"""

    class Meta:
        model = Lawyer
        fields = ("username", "password1", "password2")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # 设置字段样式
        self.fields["username"].widget.attrs.update({"class": "form-input", "placeholder": "请输入中文姓名"})
        self.fields["password1"].widget.attrs.update({"class": "form-input", "placeholder": "请输入密码"})
        self.fields["password2"].widget.attrs.update({"class": "form-input", "placeholder": "请确认密码"})

        # 更新标签
        self.fields["username"].label = "用户名/真实姓名"
        self.fields["password1"].label = "密码"
        self.fields["password2"].label = "确认密码"

        # 清除帮助文本
        self.fields["username"].help_text = "只能输入中文"
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""


    def clean_username(self) -> str:
        """验证用户名必须是中文"""
        username: str | None = self.cleaned_data.get("username")
        if username:
            # 检查是否全部为中文字符
            if not re.match(r"^[\u4e00-\u9fa5]+$", username):
                raise ValidationError("用户名只能输入中文")
        if username is None:
            username = ""
        return username

    def save(self, commit: bool = True) -> Lawyer:
        """保存用户，仅负责表单数据映射"""
        user = super().save(commit=False)
        # 将用户名同时保存到 real_name 字段
        user.real_name = user.username

        if commit:
            user.save()
        return user
