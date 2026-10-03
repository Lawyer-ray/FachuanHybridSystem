"""Module for save."""

from __future__ import annotations

import logging
from typing import Any

from django.apps import apps
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.forms import ModelForm
from django.http import HttpRequest

from apps.cases.models import Case, CaseAssignment, CaseLog

from .service import CaseAdminServiceMixin

logger = logging.getLogger("apps.cases")


class CaseAdminSaveMixin(CaseAdminServiceMixin):  # pragma: no cover
    def _cleanup_before_delete(self, case_ids: list[int]) -> None:  # pragma: no cover
        """删除前把指向案件的弱引用 FK 置空，避免外键约束阻断删除。

        注意：新增指向 Case 的可空 FK 时要同步加进这张表；
        删除失败会直接报 IntegrityError（不再绕过外键检查强删，
        避免留下无审计的孤儿数据）。
        """
        if not case_ids:
            return

        for app_label, model_name in (
            ("automation", "CourtDocument"),
            ("automation", "CourtSMS"),
            ("document_recognition", "DocumentRecognitionTask"),
            ("automation", "ScraperTask"),
        ):
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                continue
            model.objects.filter(case_id__in=case_ids).update(case=None)

    def delete_model(self, request: HttpRequest, obj: Case) -> None:  # pragma: no cover
        try:
            self._cleanup_before_delete([obj.id])
            super().delete_model(request, obj)  # type: ignore[misc]
        except IntegrityError:
            logger.error(
                "Admin 删除案件失败：存在未清理的外键引用",
                extra={"case_id": obj.id},
                exc_info=True,
            )
            messages.error(request, "删除失败：仍有数据引用该案件，请先处理关联数据（详情见服务器日志）")

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Case, Case]) -> None:  # pragma: no cover
        case_ids = list(queryset.values_list("id", flat=True))
        try:
            self._cleanup_before_delete(case_ids)
            super().delete_queryset(request, queryset)  # type: ignore[misc]
        except IntegrityError:
            logger.error(
                "Admin 批量删除案件失败：存在未清理的外键引用",
                extra={"case_ids": case_ids},
                exc_info=True,
            )
            messages.error(request, "批量删除失败：仍有数据引用部分案件，请先处理关联数据（详情见服务器日志）")

    def save_model(  # pragma: no cover
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
                logger.warning("读取案件旧值失败（已忽略，案件可能已被并发删除）: case_id=%s", obj.pk, exc_info=True)

        super().save_model(request, obj, form, change)  # type: ignore[misc]

        try:
            service = self._get_case_admin_service()
            filing_number = service.handle_case_filing_change(case_id=obj.id, is_filed=obj.is_filed)

            if filing_number:
                obj.filing_number = filing_number
                logger.info(
                    "案件 %s 建档编号已处理: %s",
                    obj.id,
                    filing_number,
                    extra={
                        "case_id": obj.id,
                        "filing_number": filing_number,
                        "is_filed": obj.is_filed,
                    },
                )
        except Exception as e:
            logger.error(
                "处理案件 %s 建档编号失败: %s",
                obj.id,
                e,
                extra={"case_id": obj.id},
                exc_info=True,
            )
            messages.error(request, "处理建档编号失败: %s" % str(e))

        case_type_changed = old_case_type != obj.case_type
        stage_changed = old_current_stage != obj.current_stage

        if case_type_changed or stage_changed or not change:
            try:
                binding_service = self._get_case_template_binding_service()
                binding_service.sync_auto_recommendations(obj.id)
                logger.info(
                    "案件 %s 模板绑定已同步",
                    obj.id,
                    extra={
                        "case_id": obj.id,
                        "case_type_changed": case_type_changed,
                        "stage_changed": stage_changed,
                    },
                )
            except Exception as e:
                logger.error(
                    "同步案件 %s 模板绑定失败: %s",
                    obj.id,
                    e,
                    extra={"case_id": obj.id},
                    exc_info=True,
                )
                messages.warning(request, "同步模板绑定失败: %s" % str(e))

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
                    obj.id,
                    e,
                    extra={"case_id": obj.id},
                    exc_info=True,
                )
                messages.error(request, "同步律师指派失败: %s" % str(e))

    @transaction.atomic
    def save_formset(
        self, request: HttpRequest, form: ModelForm[Any], formset: Any, change: bool
    ) -> None:  # pragma: no cover
        from apps.contracts.models import ClientPaymentRecord

        instances = formset.save(commit=False)

        # 批量预查指派重复，避免循环内逐行 exists() 查询
        pending_assignment_pairs = {
            (obj.case_id, obj.lawyer_id)
            for obj in instances
            if isinstance(obj, CaseAssignment) and not obj.pk and obj.case_id and obj.lawyer_id
        }
        existing_assignment_pairs: set[tuple[int, int]] = set()
        if pending_assignment_pairs:
            case_ids = {case_id for case_id, _ in pending_assignment_pairs}
            existing_assignment_pairs = set(
                CaseAssignment.objects.filter(case_id__in=case_ids).values_list("case_id", "lawyer_id")
            )

        for obj in instances:
            if isinstance(obj, CaseLog) and not getattr(obj, "actor_id", None):
                user_id = getattr(request.user, "id", None)
                if user_id is not None:
                    obj.actor_id = user_id
            if isinstance(obj, CaseAssignment) and not obj.pk and obj.case_id and obj.lawyer_id:
                if (obj.case_id, obj.lawyer_id) in existing_assignment_pairs:
                    continue
                existing_assignment_pairs.add((obj.case_id, obj.lawyer_id))
            if isinstance(obj, ClientPaymentRecord):
                parent_case: Any = form.instance
                if parent_case and parent_case.pk:
                    if not obj.contract_id:
                        obj.contract_id = parent_case.contract_id
                    if not obj.case_id:
                        obj.case_id = parent_case.pk
                if not obj.contract_id:
                    continue
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            try:
                obj.delete()
            except Exception:
                logger.warning(
                    "删除关联对象失败: %s pk=%s", type(obj).__name__, getattr(obj, "pk", None), exc_info=True
                )


__all__: list[str] = ["CaseAdminSaveMixin"]
