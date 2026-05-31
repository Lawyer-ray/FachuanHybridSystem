from __future__ import annotations

import re
from typing import Any

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Lawyer

class LawyerRegistrationForm(UserCreationForm[Lawyer]):
    class Meta:
        model = Lawyer
        fields = ("username", "password1", "password2")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": "form-input",
                "placeholder": str("请输入中文姓名"),
                "autocomplete": "username",
            }
        )
        self.fields["password1"].widget.attrs.update(
            {
                "class": "form-input",
                "placeholder": str("请输入密码"),
                "autocomplete": "new-password",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                "class": "form-input",
                "placeholder": str("请确认密码"),
                "autocomplete": "new-password",
            }
        )

        self.fields["username"].label = "用户名/真实姓名"
        self.fields["password1"].label = "密码"
        self.fields["password2"].label = "确认密码"

        self.fields["username"].help_text = "只能输入中文"
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

    def clean_username(self) -> str:
        username: str | None = self.cleaned_data.get("username")
        if username:
            if not re.match(r"^[\u4e00-\u9fa5]+$", username):
                raise ValidationError("用户名只能输入中文")
        if username is None:
            username = ""
        return username
