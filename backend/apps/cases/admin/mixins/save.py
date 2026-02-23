"""Module for save."""

from __future__ import annotations

import contextlib
import logging
from typing import Any, cast

from django.apps import apps
from django.contrib import messages
from django.db import IntegrityError, connection
from django.db.models import QuerySet
from django.forms import ModelForm
from django.http import HttpRequest

from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseLog

from .service import CaseAdminServiceMixin

logger = logging.getLogger("apps.cases")


class CaseAdminSaveMixin(CaseAdminServiceMixin):
    def _cleanup_before_delete(self, case_ids: list[int]) -> None:
        if not case_ids:
            return

        for app_label, model_name in (
            ("automation", "CourtDocument"),
            ("automation", "CourtSMS"),
            ("automation", "DocumentRecognitionTask"),
            ("automation", "ScraperTask"),
        ):
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                continue
            model.objects.filter(case_id__in=case_ids).update(case=None)

        from apps.cases.utils import fix_sqlite_orphan_contract_fk
        fix_sqlite_orphan_contract_fk()

    def delete_model(self, request: HttpRequest, obj: Case) -> None:
        try:
            self._cleanup_before_delete([obj.id])
            super().delete_model(request, obj)  # type: ignore[misc]
        except IntegrityError as e:
            logger.error(
                "Admin 删除案件失败",
                extra={"case_id": cast(int, obj.id), "error": str(e)},
                exc_info=True,
            )
            with connection.constraint_checks_disabled():
                super().delete_model(request, obj)  # type: ignore[misc]
            messages.warning(request, _("已强制删除案件 %(case_id)s(已绕过外键检查)") % {"case_id": cast(int, obj.id)})

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Case, Case]) -> None:
        case_ids = list(queryset.values_list("id", flat=True))
        try:
            self._cleanup_before_delete(case_ids)
            super().delete_queryset(request, queryset)  # type: ignore[misc]
        except IntegrityError as e:
            logger.error(
                "Admin 批量删除案件失败",
                extra={"case_ids": case_ids, "error": str(e)},
                exc_info=True,
            )
            with connection.constraint_checks_disabled():
                super().delete_queryset(request, queryset)  # type: ignore[misc]
            messages.warning(request, _("已强制批量删除 %d 个案件(已绕过外键检查)") % len(case_ids))

    def save_model(
        self,
        request: HttpRequest,
        obj: Case,
        form: ModelForm[Case],
        change: bool,
    ) -> None:
        old_case_type: str | None = None
        old_current_stage: str | None = None
        old_contract_id: int | None = None
        if change and obj.pk:
            try:
                old_obj = Case.objects.get(pk=obj.pk)
                old_case_type = old_obj.case_type
                old_current_stage = old_obj.current_stage
                old_contract_id = getattr(old_obj, "contract_id", None)
            except Case.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)  # type: ignore[misc]

        try:
            service = self._get_case_admin_service()
            filing_number = service.handle_case_filing_change(case_id=obj.id, is_archived=obj.is_archived)

            if filing_number:
                obj.filing_number = filing_number
                logger.info(
                    "案件 %s 建档编号已处理: %s",
                    cast(int, obj.id),
                    filing_number,
                    extra={
                        "case_id": obj.id,
                        "filing_number": filing_number,
                        "is_archived": obj.is_archived,
                    },
                )
        except Exception as e:
            logger.error(
                "处理案件 %s 建档编号失败: %s",
                cast(int, obj.id),
                e,
                extra={"case_id": obj.id},
                exc_info=True,
            )
            messages.error(request, _("处理建档编号失败: %s") % str(e))

        case_type_changed = old_case_type != obj.case_type
        stage_changed = old_current_stage != obj.current_stage

        if case_type_changed or stage_changed or not change:
            try:
                binding_service = self._get_case_template_binding_service()
                binding_service.sync_auto_recommendations(obj.id)
                logger.info(
                    "案件 %s 模板绑定已同步",
                    cast(int, obj.id),
                    extra={
                        "case_id": obj.id,
                        "case_type_changed": case_type_changed,
                        "stage_changed": stage_changed,
                    },
                )
            except Exception as e:
                logger.error(
                    "同步案件 %s 模板绑定失败: %s",
                    cast(int, obj.id),
                    e,
                    extra={"case_id": obj.id},
                    exc_info=True,
                )
                messages.warning(request, _("同步模板绑定失败: %s") % str(e))

        new_contract_id = getattr(obj, "contract_id", None)
        contract_changed = not change or (old_contract_id != new_contract_id)
        if contract_changed:
            try:
                assignment_service = self._get_case_assignment_service()
                assignment_service.sync_assignments_from_contract(
                    case_id=obj.id,
                    user=getattr(request, "user", None),
                    perm_open_access=True,
                )
            except Exception as e:
                logger.error(
                    "同步案件 %s 的律师指派失败: %s",
                    cast(int, obj.id),
                    e,
                    extra={"case_id": obj.id},
                    exc_info=True,
                )
                messages.error(request, _("同步律师指派失败: %s") % str(e))

    def save_formset(self, request: HttpRequest, form: ModelForm[Any], formset: Any, change: bool) -> None:
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, CaseLog) and not getattr(obj, "actor_id", None):
                user_id = getattr(request.user, "id", None)
                if user_id is not None:
                    obj.actor_id = user_id  # type: ignore[attr-defined]
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            with contextlib.suppress(Exception):
                obj.delete()


__all__: list[str] = ["CaseAdminSaveMixin"]
