"""Module for save."""

import logging
from typing import Any

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.documents.models import LIST_TYPE_PREVIOUS, EvidenceItem, EvidenceList, ListType

from .views import EvidenceListAdminServiceMixin

logger = logging.getLogger(__name__)


class EvidenceListAdminSaveMixin(EvidenceListAdminServiceMixin):
    def save_model(self, request: Any, obj: Any, form: Any, change: Any) -> None:
        from django.contrib import messages

        if not change:
            existing_types = set(EvidenceList.objects.filter(case=obj.case).values_list("list_type", flat=True))

            next_type = None
            for list_type, _label in ListType.choices:
                if list_type not in existing_types:
                    next_type = list_type
                    break

            if next_type:
                obj.list_type = next_type
            else:
                messages.error(request, "该案件已创建所有证据清单类型(最多6个)")
                return

            if hasattr(request, "user"):
                try:
                    from apps.core.interfaces import ServiceLocator

                    user = getattr(request, "user", None)
                    if not user or not getattr(user, "is_authenticated", False):
                        raise ValueError("unauthenticated user")

                    org_service = ServiceLocator.get_organization_service()
                    lawyer_dto = org_service.get_lawyer_by_id_internal(getattr(user, "id", None))
                    if (
                        lawyer_dto
                        and getattr(user, "_meta", None)
                        and getattr(user._meta, "label_lower", "") == "organization.lawyer"
                    ):
                        obj.created_by = user
                except Exception:
                    logger.exception("操作失败")

        required_previous_type = LIST_TYPE_PREVIOUS.get(obj.list_type)
        if required_previous_type:
            previous_list = EvidenceList.objects.filter(case=obj.case, list_type=required_previous_type).first()
            obj.previous_list = previous_list
        else:
            obj.previous_list = None

        super().save_model(request, obj, form, change)

    def save_formset(self, request: Any, form: Any, formset: Any, change: Any) -> None:
        import traceback

        from django.contrib import messages

        try:
            instances = formset.save(commit=False)
            self._report_formset_errors(request, form, formset, messages)

            evidence_list = form.instance
            max_order = evidence_list.items.aggregate(max_order=models.Max("order"))["max_order"] or 0
            items_need_page_count: list[Any] = []

            max_order = self._save_instances(instances, max_order, items_need_page_count, request, messages, traceback)
            self._count_pdf_pages(items_need_page_count, request, messages)
            self._delete_removed_objects(formset, request, messages)
            self._handle_file_cleared(formset)
            self._reorder_items_after_delete(evidence_list)
            self._recalculate_list_pages(evidence_list)
            formset.save_m2m()

        except Exception as e:
            logger.error("保存过程出错", extra={"error": str(e), "traceback": traceback.format_exc()}, exc_info=True)
            messages.error(request, _("保存过程出错: %(e)s") % {"e": e})
            raise

    @staticmethod
    def _report_formset_errors(request: Any, form: Any, formset: Any, messages: Any) -> None:
        if formset.errors:
            for i, err in enumerate(formset.errors):
                if err:
                    messages.error(request, _("表单 %(i)s 错误: %(err)s") % {"i": i, "err": err})
        if form.errors:
            logger.warning("EvidenceListAdmin form errors", extra={"errors": form.errors})

    def _save_instances(self, instances: Any, max_order: int, items_need_page_count: list[Any], request: Any, messages: Any, traceback: Any) -> Any:
        for obj in instances:
            if isinstance(obj, EvidenceItem):
                self._prepare_evidence_item(obj, max_order, items_need_page_count)
                max_order = max(max_order, obj.order)
            try:
                obj.save()
            except Exception as e:
                logger.error("保存失败", extra={"error": str(e), "traceback": traceback.format_exc()}, exc_info=True)
                messages.error(request, _("保存失败: %(e)s") % {"e": e})
                raise
        return max_order

    @staticmethod
    def _delete_removed_objects(formset: Any, request: Any, messages: Any) -> None:
        for obj in formset.deleted_objects:
            try:
                obj.delete()
            except Exception as e:
                logger.warning("删除失败", extra={"error": str(e)}, exc_info=True)
                messages.error(request, _("删除失败: %(e)s") % {"e": e})

    @staticmethod
    def _prepare_evidence_item(obj: Any, max_order: int, items_need_page_count: list[Any]) -> None:
        """准备证据项:设置排序、文件信息、页数"""
        from pathlib import Path

        if obj.pk is None:
            max_order += 1
            obj.order = max_order

        if obj.file:
            file_name = obj.file.name
            ext = Path(file_name).suffix.lower()

            obj.file_name = Path(file_name).name
            try:
                obj.file_size = obj.file.size
            except Exception as e:
                logger.warning("获取文件大小失败", extra={"file_name": file_name, "error": str(e)}, exc_info=True)
                obj.file_size = 0

            if ext == ".pdf":
                items_need_page_count.append(obj)
            obj.page_count = 1

    @staticmethod
    def _count_pdf_pages(items: list[Any], request: Any, messages: Any) -> None:
        """识别 PDF 页数"""
        for obj in items:
            try:
                from apps.documents.services.pdf_utils import get_pdf_page_count_with_error

                page_count, error = get_pdf_page_count_with_error(obj.file, default=1)
                if page_count != obj.page_count:
                    obj.page_count = page_count
                    obj.save(update_fields=["page_count"])
                if error:
                    messages.warning(
                        request,
                        _("文件 %(n)s 页数识别失败,将按 %(p)s 页处理:%(e)s") % {
                            "n": obj.file_name or obj.file,
                            "p": page_count,
                            "e": error,
                        },
                    )
            except Exception as e:
                logger.warning(
                    "计算页数失败",
                    extra={"file_name": getattr(obj.file, "name", None), "error": str(e)},
                    exc_info=True,
                )
                messages.warning(request, _("文件 %(n)s 页数识别失败: %(e)s") % {"n": obj.file_name, "e": e})

    def _handle_file_cleared(self, formset: Any) -> None:
        for form in formset.forms:
            if form.instance.pk and not form.cleaned_data.get("DELETE", False):
                instance = form.instance
                instance.refresh_from_db()

                if not instance.file and (instance.page_count != 0 or instance.file_name or instance.file_size):
                    instance.page_count = 0
                    instance.file_name = ""
                    instance.file_size = 0
                    instance.page_start = None
                    instance.page_end = None
                    instance.save(update_fields=["page_count", "file_name", "file_size", "page_start", "page_end"])

    def _reorder_items_after_delete(self, evidence_list: EvidenceList) -> None:
        items = evidence_list.items.order_by("order")
        for index, item in enumerate(items, start=1):
            if item.order != index:
                item.order = index
                item.save(update_fields=["order"])

    def _recalculate_list_pages(self, evidence_list: EvidenceList) -> None:
        evidence_list.refresh_from_db()
        items = evidence_list.items.all()
        total_pages = sum(item.page_count or 0 for item in items)

        if evidence_list.total_pages != total_pages:
            evidence_list.total_pages = total_pages
            evidence_list.save(update_fields=["total_pages"])


__all__: list[str] = ["EvidenceListAdminSaveMixin"]
