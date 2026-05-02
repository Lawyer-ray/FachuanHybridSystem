"""Django admin configuration."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.cases.domain.validators import normalize_stages
from apps.cases.models import Case, CaseParty, CaseStage, SupervisingAuthority


class CaseAdminForm(forms.ModelForm[Case]):
    current_stage = forms.ChoiceField(
        choices=[("", "---------")] + list(CaseStage.choices), required=False, label=_("当前阶段")
    )

    class Meta:
        model = Case
        fields: str = "__all__"
        widgets: ClassVar[dict[str, Any]] = {
            "cause_of_action": forms.TextInput(
                attrs={
                    "class": "vTextField js-cause-autocomplete",
                    "placeholder": _("请输入案由关键词..."),
                    "autocomplete": "off",
                }
            ),
        }

    def clean(self) -> dict[str, Any]:
        cleaned: dict[str, Any] = super().clean() or {}

        cur = cleaned.get("current_stage")
        contract = cleaned.get("contract")
        ctype = getattr(contract, "case_type", None) if contract else None
        rep = getattr(contract, "representation_stages", []) if contract else []

        try:
            _, cur2 = normalize_stages(ctype, rep, cur, strict=False)
            cleaned["current_stage"] = cur2
        except ValueError as e:
            code = str(e)
            if code == "invalid_cur":
                self.add_error("current_stage", _("当前阶段不在可选范围内"))
            elif code == "cur_not_in_rep":
                self.add_error("current_stage", _("当前阶段必须在合同的代理阶段范围内"))
            elif code == "stages_not_applicable":
                self.add_error("current_stage", _("该案件类型不支持阶段设置"))
            elif code.startswith("invalid_rep:"):
                invalid_stages = code.split(":", 1)[1]
                self.add_error("current_stage", _("代理阶段包含无效值: %s") % invalid_stages)
            else:
                self.add_error(None, _("案件数据验证失败: %s") % code)

        return cleaned


class CasePartyInlineForm(forms.ModelForm[CaseParty]):
    class Meta:
        model = CaseParty
        fields: str = "__all__"


class CasePartyInlineFormSet(forms.BaseInlineFormSet):
    def clean(self) -> None:
        super().clean()
        seen_clients: set[int] = set()
        for form in self.forms:
            if form.cleaned_data.get("DELETE"):
                continue
            client = form.cleaned_data.get("client")
            if client is None:
                continue
            if client.pk in seen_clients:
                raise forms.ValidationError(_("同一案件中不能出现相同的当事人。"))
            seen_clients.add(client.pk)


class SupervisingAuthorityInlineForm(forms.ModelForm[SupervisingAuthority]):
    class Meta:
        model = SupervisingAuthority
        fields: str = "__all__"
        widgets: ClassVar[dict[str, Any]] = {
            "name": forms.TextInput(
                attrs={
                    "class": "vTextField js-court-autocomplete",
                    "placeholder": _("请输入法院名称..."),
                    "autocomplete": "off",
                }
            )
        }
