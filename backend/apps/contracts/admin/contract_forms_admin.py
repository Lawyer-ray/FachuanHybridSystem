"""
Contract Admin - Forms

合同 Admin 的表单定义.
"""

import logging
from typing import Any

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract
from apps.core.enums import CaseStage, CaseStatus

logger = logging.getLogger(__name__)


class ContractAdminForm(forms.ModelForm[Contract]):
    representation_stages = forms.MultipleChoiceField(
        choices=CaseStage.choices,
        required=False,
        widget=forms.SelectMultiple,
        label=_("代理阶段"),
    )

    class Meta:
        model = Contract
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not getattr(self.instance, "pk", None):
            self.fields["status"].initial = CaseStatus.ACTIVE
            self.fields["specified_date"].initial = timezone.localdate()
        self.fields["representation_stages"].initial = list(getattr(self.instance, "representation_stages", []) or [])

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        try:
            from apps.contracts.validators import normalize_representation_stages

            ctype = cleaned.get("case_type")
            rep = cleaned.get("representation_stages") or []
            cleaned["representation_stages"] = normalize_representation_stages(ctype, rep, strict=False)
        except Exception:
            logger.exception("操作失败")
        return cleaned
