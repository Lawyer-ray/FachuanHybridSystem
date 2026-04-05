"""SystemConfig Admin 表单。"""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec

_MULTI_KEY_CONFIGS = {"TIANYANCHA_MCP_API_KEY", "OLLAMA_MODEL"}


class SystemConfigAdminForm(forms.ModelForm):
    class Meta:
        model = SystemConfig
        fields = "__all__"
        widgets = {
            "value": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["value"].widget.attrs.setdefault("rows", 6)

        instance = self.instance
        if not instance or not instance.pk:
            return

        if instance.is_secret and instance.value:
            try:
                self.initial["value"] = SecretCodec().try_decrypt(instance.value)
            except Exception:
                self.initial["value"] = instance.value

        if instance.key in _MULTI_KEY_CONFIGS:
            if instance.key == "OLLAMA_MODEL":
                self.fields["value"].help_text = "支持多个模型名称，每行一个。实际使用时会在界面中选择具体模型。"
            else:
                self.fields[
                    "value"
                ].help_text = "支持多个 API Key，每行一个；也兼容逗号或分号分隔，调用时会自动切换可用 Key。"

    def clean_value(self) -> str:
        value = str(self.cleaned_data.get("value") or "")
        if not value:
            return ""
        if not bool(self.cleaned_data.get("is_secret")):
            return value
        try:
            return cast(str, SecretCodec().encrypt(value))
        except RuntimeError as exc:
            raise ValidationError("缺少敏感配置加密密钥，无法保存 secret 配置。") from exc
