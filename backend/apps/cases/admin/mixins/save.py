from typing import Any, cast

"""Module for save."""

import contextlib
import logging

from django.apps import apps
from django.contrib import messages
from django.db import IntegrityError, connection

from apps.cases.models import Case, CaseLog

from .views import CaseAdminServiceMixin

logger = logging.getLogger("apps.cases")


class CaseAdminSaveMixin(CaseAdminServiceMixin):
    def _cleanup_before_delete(self, case_ids) -> None:
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

        if connection.vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE cases_case
                    SET contract_id = NULL
                    WHERE contract_id IS NOT NULL
                      AND contract_id NOT IN (SELECT id FROM contracts_contract)
                    """
                )

    def delete_model(self, request, obj) -> None:
        try:
            self._cleanup_before_delete([obj.id])
            super().delete_model(request, obj)
        except IntegrityError as e:
            logger.error(
                "Admin 删除案件失败",
                extra={"case_id": cast(int, obj.id), "error": str(e)},
                exc_info=True,
            )
            with connection.constraint_checks_disabled():
                super().delete_model(request, obj)
            messages.warning(request, f"已强制删除案件 {cast(int, obj.id)}(已绕过外键检查)")

    def delete_queryset(self, request, queryset) -> None:
        case_ids = list(queryset.values_list("id", flat=True))
        try:
            self._cleanup_before_delete(case_ids)
            super().delete_queryset(request, queryset)
        except IntegrityError as e:
            logger.error(
                "Admin 批量删除案件失败",
                extra={"case_ids": case_ids, "error": str(e)},
                exc_info=True,
            )
            with connection.constraint_checks_disabled():
                super().delete_queryset(request, queryset)
            messages.warning(request, f"已强制批量删除 {len(case_ids)} 个案件(已绕过外键检查)")

    def save_model(self, request, obj, form, change) -> None:
        old_case_type: Any | None = None
        old_current_stage: Any | None = None
        if change and obj.pk:
            try:
                old_obj = Case.objects.get(pk=obj.pk)
                old_case_type = old_obj.case_type
                old_current_stage = old_obj.current_stage
            except Case.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

        try:
            service = self._get_case_admin_service()
            filing_number = service.handle_case_filing_change(case_id=obj.id, is_archived=obj.is_archived)

            if filing_number:
                obj.filing_number = filing_number
                logger.info(
                    f"案件 {cast(int, cast(int, obj.id))} 建档编号已处理: {filing_number}",
                    extra={
                        "case_id": obj.id,
                        "filing_number": filing_number,
                        "is_archived": obj.is_archived,
                    },
                )
        except Exception as e:
            logger.error(
                f"处理案件 {cast(int, cast(int, obj.id))} 建档编号失败: {e!s}",
                extra={"case_id": obj.id},
                exc_info=True,
            )
            messages.error(request, f"处理建档编号失败: {e!s}")

        case_type_changed = old_case_type != obj.case_type
        stage_changed = old_current_stage != obj.current_stage

        if case_type_changed or stage_changed or not change:
            try:
                binding_service = self._get_case_template_binding_service()
                binding_service.sync_auto_recommendations(obj.id)
                logger.info(
                    f"案件 {cast(int, cast(int, obj.id))} 模板绑定已同步",
                    extra={
                        "case_id": obj.id,
                        "case_type_changed": case_type_changed,
                        "stage_changed": stage_changed,
                    },
                )
            except Exception as e:
                logger.error(
                    f"同步案件 {cast(int, cast(int, obj.id))} 模板绑定失败: {e!s}",
                    extra={"case_id": obj.id},
                    exc_info=True,
                )
                messages.warning(request, f"同步模板绑定失败: {e!s}")

        try:
            from apps.cases.services import CaseAssignmentService
            from apps.core.interfaces import ServiceLocator

            CaseAssignmentService(
                case_service=ServiceLocator.get_case_service(),
                contract_assignment_query_service=ServiceLocator.get_contract_assignment_query_service(),
            ).sync_assignments_from_contract(
                case_id=obj.id,
                user=getattr(request, "user", None),
                perm_open_access=True,
            )
        except Exception as e:
            logger.error(
                f"同步案件 {cast(int, cast(int, obj.id))} 的律师指派失败: {e!s}",
                extra={"case_id": obj.id},
                exc_info=True,
            )
            messages.error(request, f"同步律师指派失败: {e!s}")

    def save_formset(self, request, form, formset, change) -> None:
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, CaseLog) and not getattr(obj, "actor_id", None):
                obj.actor_id = getattr(request.user, "id", None)
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            with contextlib.suppress(Exception):
                obj.delete()


__all__: list[str] = ["CaseAdminSaveMixin"]
