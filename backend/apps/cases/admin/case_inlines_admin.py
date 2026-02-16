"""Django admin configuration."""

import logging
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.db import models
from django.forms.models import BaseInlineFormSet

from apps.cases.models import CaseLog, CaseLogAttachment, CaseNumber, CaseParty, SupervisingAuthority

from .case_base_admin import BaseModelAdmin, BaseStackedInline, BaseTabularInline
from .case_forms_admin import CasePartyInlineForm, SupervisingAuthorityInlineForm


class CasePartyInline(BaseTabularInline):
    model = CaseParty
    form = CasePartyInlineForm
    extra: int = 1
    fields: tuple[Any, ...] = ("client", "legal_status", "is_our_client_display")
    readonly_fields: tuple[Any, ...] = ("is_our_client_display",)
    classes: ClassVar = ["contract-party-inline"]

    class UniqueClientInlineFormSet(BaseInlineFormSet):
        def clean(self) -> None:

            logger = logging.getLogger(__name__)
            logger.info(f"[CasePartyFormSet.clean] 开始验证, forms count: {len(self.forms)}")

            super().clean()
            existing = self._get_existing_client_ids()
            logger.info(f"[CasePartyFormSet.clean] case={getattr(self, 'instance', None)}, existing={existing}")

            try:
                our_party_statuses = self._validate_each_form(existing, logger)
                self._validate_our_party_conflicts(our_party_statuses, logger)
            except Exception as e:
                logger.error(f"当事人表单验证错误: {e}")
                from django.core.exceptions import ValidationError

                raise ValidationError(f"当事人数据验证失败: {e}") from e

            logger.info("[CasePartyFormSet.clean] 验证完成")

        def _get_existing_client_ids(self) -> set[Any]:
            case = getattr(self, "instance", None)
            if case and case.pk:
                from apps.cases.models import CaseParty

                return set(CaseParty.objects.filter(case=case).values_list("client_id", flat=True))
            return set()

        def _validate_each_form(self, existing: set[Any], logger) -> list[Any]:
            seen = set()
            our_party_statuses = []
            for i, form in enumerate(self.forms):
                logger.info(
                    f"[CasePartyFormSet.clean] form[{i}]: "
                    f"has cleaned_data={hasattr(form, 'cleaned_data')}, errors={form.errors}"
                )
                if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                    continue
                client = form.cleaned_data.get("client")
                if not client:
                    continue
                cid = client.pk
                self._check_duplicate(form, i, cid, seen, existing, logger)
                self._collect_our_party_status(our_party_statuses, i, client, form, logger)
            return our_party_statuses

        def _check_duplicate(self, form, idx, cid, seen, existing, logger) -> None:
            if cid in seen:
                form.add_error("client", "同一案件中当事人只能出现一次")
                logger.warning(f"[CasePartyFormSet.clean] form[{idx}]: 重复当事人 {cid}")
            else:
                seen.add(cid)
            if cid in existing and not form.instance.pk:
                form.add_error("client", "该当事人已存在于此案件")
                logger.warning(f"[CasePartyFormSet.clean] form[{idx}]: 当事人已存在 {cid}")

        @staticmethod
        def _collect_our_party_status(our_party_statuses, idx, client, form, logger) -> None:
            legal_status = form.cleaned_data.get("legal_status")
            if not (getattr(client, "is_our_client", False) and legal_status):
                return
            from apps.core.business_config import business_config

            config = business_config._compatibility_map.get(legal_status)
            if config:
                our_party_statuses.append((idx, client.name, legal_status, config.group))

        def _validate_our_party_conflicts(self, our_party_statuses, logger) -> None:
            if len(our_party_statuses) < 2:
                return

            from apps.core.business_config import business_config

            opposing_groups = {
                "plaintiff_side": "defendant_side",
                "defendant_side": "plaintiff_side",
                "appellant_side": "appellee_side",
                "appellee_side": "appellant_side",
                "applicant_side": "respondent_side",
                "respondent_side": "applicant_side",
                "criminal_defendant_side": "criminal_victim_side",
                "criminal_victim_side": "criminal_defendant_side",
            }

            for i, (_form_idx1, name1, status1, group1) in enumerate(our_party_statuses):
                opposing_group = opposing_groups.get(group1)
                if not opposing_group:
                    continue

                for form_idx2, name2, status2, group2 in our_party_statuses[i + 1 :]:
                    if group2 == opposing_group:
                        status1_label = business_config.get_legal_status_label(status1)
                        status2_label = business_config.get_legal_status_label(status2)

                        error_msg = (
                            f"我方当事人诉讼地位冲突:「{name1}」为{status1_label},"
                            f"「{name2}」为{status2_label},不能同时处于对立诉讼地位"
                        )

                        self.forms[form_idx2].add_error("legal_status", error_msg)
                        logger.warning(
                            f"[CasePartyFormSet.clean] 我方当事人诉讼地位冲突: {name1}({status1}) vs {name2}({status2})"
                        )

    formset = UniqueClientInlineFormSet

    def is_our_client_display(self, obj) -> None:
        if obj and getattr(obj, "client", None):
            return bool(getattr(obj.client, "is_our_client", False))
        return False

    is_our_client_display.boolean = True
    is_our_client_display.short_description = "是否为我方当事人"

    class Media:
        js: tuple[Any, ...] = ("cases/admin_caseparty.js",)
        css: ClassVar = {"all": ("cases/admin_caseparty.css",)}


class SupervisingAuthorityInline(BaseTabularInline):
    model = SupervisingAuthority
    form = SupervisingAuthorityInlineForm
    extra: int = 1
    fields: tuple[Any, ...] = ("name", "authority_type")


def _make_custom_formset(base_formset) -> None:  # noqa: C901 — Django formset 工厂函数,内部类方法被计入复杂度
    """创建自定义 FormSet 类,用于 CaseLogAttachmentInline"""

    class CustomFormSet(base_formset):
        def clean(self) -> None:
            if any(self.errors):
                return

            for form in self.forms:
                if not hasattr(form, "cleaned_data"):
                    continue
                if form.cleaned_data.get("DELETE"):
                    continue
                if not form.cleaned_data.get("file"):
                    continue

        def is_valid(self) -> None:
            result = super().is_valid()
            if result:
                return True
            return self._recheck_ignoring_empty_forms()

        def _recheck_ignoring_empty_forms(self) -> None:
            has_real_error = False
            for form in self.forms:
                if not form.errors:
                    continue
                if self._form_has_data(form):
                    has_real_error = True
                else:
                    form._errors = {}
            return not has_real_error

        @staticmethod
        def _form_has_data(form) -> None:
            skip_fields = {"DELETE", "id", "log"}
            for field_name in form.fields:
                if field_name in skip_fields:
                    continue
                if form.data.get(f"{form.prefix}-{field_name}"):
                    return True
            return False

    return CustomFormSet


class CaseLogAttachmentInline(BaseTabularInline):
    model = CaseLogAttachment
    extra: int = 0

    def get_formset(self, request, obj=None, **kwargs) -> None:
        formset = super().get_formset(request, obj, **kwargs)
        return _make_custom_formset(formset)


class CaseNumberInline(BaseTabularInline):
    model = CaseNumber
    extra: int = 1
    fields: tuple[Any, ...] = ("number", "remarks")
    formfield_overrides: ClassVar = {
        models.TextField: {"widget": forms.TextInput(attrs={"style": "width: 100%;"})},
    }


class CaseLogInlineForm(forms.ModelForm):
    class Meta:
        model = CaseLog
        fields: str = "__all__"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if "actor" in self.fields:
            self.fields["actor"].required = False


class CaseLogInline(BaseStackedInline):
    model = CaseLog
    form = CaseLogInlineForm
    extra: int = 1
    fields: tuple[Any, ...] = ("content",)
    exclude: tuple[Any, ...] = ("actor",)
    ordering: tuple[Any, ...] = ("-created_at",)
    classes: tuple[Any, ...] = ("collapse", "case-log-inline")
    verbose_name: str = "案件日志"
    verbose_name_plural: str = "案件日志"
    template: str = "admin/cases/case/caselog_inline.html"

    if BaseModelAdmin is not admin.ModelAdmin:
        inlines: list[Any] = [CaseLogAttachmentInline]
