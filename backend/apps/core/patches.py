"""
第三方库兼容性补丁

修复 django-nested-admin 与 Django 6.0 的兼容性问题
"""

import contextlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_pk_value(form: Any, pk_name: str) -> Any:
    """从表单中获取原始 PK 值"""
    if not hasattr(form, "_raw_value"):
        return form.fields[pk_name].widget.value_from_datadict(form.data, form.files, form.add_prefix(pk_name))
    return form._raw_value(pk_name)


def _clean_pk_or_save_new(
    formset: Any, form: Any, pk_name: str, raw_pk_value: Any, saved_instances: list[Any], commit: bool
) -> tuple[Any, bool]:
    """尝试 clean PK,失败则作为新对象保存.返回 (pk_value, should_continue)"""
    from django.core.exceptions import ValidationError
    from nested_admin.formsets import mutable_querydict

    try:
        pk_value = form.fields[pk_name].clean(raw_pk_value)
    except ValidationError:
        with mutable_querydict(form.data):
            form.data[form.add_prefix(pk_name)] = ""
        if not form.has_changed():
            changed = form.changed_data
            if pk_name not in changed:
                changed.append(pk_name)
        saved_instances.extend(formset.save_new_objects([form], commit))
        return None, True
    return getattr(pk_value, "pk", pk_value), False


def _find_existing_object(formset: Any, form: Any, pk_value: Any) -> Any:
    """查找已有对象"""
    from django.utils.encoding import force_str

    obj = None
    if form.instance and pk_value:
        model_cls = form.instance.__class__
        try:
            obj = model_cls.objects.get(pk=pk_value)
        except model_cls.DoesNotExist:
            if pk_value and force_str(form.instance.pk) == force_str(pk_value):
                obj = form.instance
    if obj is None:
        obj = formset._existing_object(pk_value)
    return obj


def _handle_delete(formset: Any, form: Any, obj: Any, commit: bool) -> None:
    """处理删除表单"""
    from nested_admin.formsets import get_base_polymorphic_model

    formset.deleted_objects.append(obj)
    base_model_cls = get_base_polymorphic_model(type(obj))
    if not base_model_cls:
        formset.delete_existing(obj, commit=commit)
    else:
        with contextlib.suppress(base_model_cls.DoesNotExist):
            formset.delete_existing(obj, commit=commit)


def _handle_changed(formset: Any, form: Any, obj: Any, saved_instances: list[Any], commit: bool) -> None:
    """处理变更表单"""
    from django.contrib.contenttypes.models import ContentType

    old_ct_val = ct_val = ContentType.objects.get_for_model(formset.instance.__class__).pk
    old_fk_val = fk_val = formset.instance.pk
    if form.instance.pk:
        original_instance = formset.model.objects.get(pk=form.instance.pk)
        fk_field = getattr(formset, "fk", getattr(formset, "ct_fk_field", None))
        if fk_field:
            old_fk_val = getattr(original_instance, fk_field.get_attname())
        ct_field = getattr(formset, "ct_field", None)
        if ct_field:
            old_ct_val = getattr(original_instance, ct_field.get_attname())

    if form.has_changed() or fk_val != old_fk_val or ct_val != old_ct_val:
        formset.changed_objects.append((obj, form.changed_data))
        saved_instances.append(formset.save_existing(form, obj, commit=commit))
        if not commit:
            formset.saved_forms.append(form)


def patch_nested_admin() -> None:
    """
    修复 django-nested-admin 在 Django 6.0 中的 KeyError: 'changed_data' 问题

    Django 6.0 中 changed_data 是 @cached_property,不能通过 __dict__ 直接访问
    """
    try:
        import nested_admin.formsets as formsets

        def patched_save_existing_objects(
            self: Any, initial_forms: Any | None = None, commit: bool = True
        ) -> list[Any]:
            """修复版本的 save_existing_objects 方法,兼容 Django 6.0"""
            if not initial_forms:
                return []

            saved_instances: list[Any] = []
            forms_to_delete = self.deleted_forms

            for form in initial_forms:
                pk_name = self._pk_field.name
                raw_pk_value = _resolve_pk_value(form, pk_name)

                if self._should_delete_form(form):
                    pk_value = raw_pk_value
                else:
                    pk_value, should_continue = _clean_pk_or_save_new(
                        self, form, pk_name, raw_pk_value, saved_instances, commit
                    )
                    if should_continue:
                        continue

                obj = _find_existing_object(self, form, pk_value)
                if obj is None or not obj.pk:
                    continue

                if form in forms_to_delete:
                    _handle_delete(self, form, obj, commit)
                    continue

                _handle_changed(self, form, obj, saved_instances, commit)
            return saved_instances

        formsets.NestedInlineFormSet.save_existing_objects = patched_save_existing_objects

        if hasattr(formsets, "NestedBaseGenericInlineFormSet"):
            formsets.NestedBaseGenericInlineFormSet.save_existing_objects = patched_save_existing_objects

        logger.info("Successfully patched django-nested-admin for Django 6.0 compatibility")

    except Exception as e:
        logger.warning(f"Failed to patch django-nested-admin: {e}", exc_info=True)


def apply_all_patches() -> None:
    """应用所有补丁"""
    patch_nested_admin()
