from __future__ import annotations

import re
from typing import Any

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Lawyer


class LawyerRegistrationForm(UserCreationForm[Lawyer]):

    bootstrap_token = forms.CharField(
        required=False,
        label=_("Bootstrap Token"),
        widget=forms.PasswordInput(attrs={"class": "form-input", "placeholder": str(_("首次注册管理员时填写"))}),
        help_text=_("仅首个管理员注册时需要"),
    )

    class Meta:
        model = Lawyer
        fields = ("username", "password1", "password2")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": "form-input", "placeholder": str(_("请输入中文姓名"))})
        self.fields["password1"].widget.attrs.update({"class": "form-input", "placeholder": str(_("请输入密码"))})
        self.fields["password2"].widget.attrs.update({"class": "form-input", "placeholder": str(_("请确认密码"))})

        self.fields["username"].label = _("用户名/真实姓名")
        self.fields["password1"].label = _("密码")
        self.fields["password2"].label = _("确认密码")

        self.fields["username"].help_text = _("只能输入中文")
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

    def clean_username(self) -> str:
        username: str | None = self.cleaned_data.get("username")
        if username:
            if not re.match(r"^[\u4e00-\u9fa5]+$", username):
                raise ValidationError(_("用户名只能输入中文"))
        if username is None:
            username = ""
        return username
