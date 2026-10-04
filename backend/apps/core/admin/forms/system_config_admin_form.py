"""SystemConfig Admin 表单。"""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec

_MULTI_KEY_CONFIGS = {"TIANYANCHA_MCP_API_KEY", "QCC_MCP_API_KEY"}


class SystemConfigAdminForm(forms.ModelForm):  # pragma: no cover
    class Meta:  # pragma: no cover
        model = SystemConfig
        fields = "__all__"
        widgets = {
            "value": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
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
            self.fields[
                "value"
            ].help_text = "支持多个 API Key，每行一个；也兼容逗号或分号分隔，调用时会自动切换可用 Key。"

    def clean(self) -> dict[str, Any]:  # pragma: no cover
        """表单级清洗：secret 值加密落库。

        注意：加密必须放在表单级 clean() 而非 clean_value()——Django 按字段声明顺序
        逐个清洗，SystemConfig.value 声明在 is_secret 之前，clean_value() 执行时
        cleaned_data 里还没有 is_secret（恒为 None），加密分支永不可达。
        """
        cleaned = super().clean()
        assert cleaned is not None  # super().clean() 返回 cleaned_data，校验阶段不会为 None
        value = str(cleaned.get("value") or "")
        if not value or not bool(cleaned.get("is_secret")):
            return cleaned
        try:
            cleaned["value"] = SecretCodec().encrypt(value)
        except RuntimeError as exc:
            raise ValidationError("缺少敏感配置加密密钥，无法保存 secret 配置。") from exc
        return cleaned
