"""Module for signals."""

from __future__ import annotations

"""
文书生成系统 Django Signals

实现模板修改的审计日志自动记录.

Requirements: 6.6
"""

import logging
from typing import Any

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import DocumentTemplate, FolderTemplate, Placeholder, TemplateAuditAction, TemplateAuditLog

logger = logging.getLogger(__name__)

# 用于存储对象修改前的状态
_pre_save_state = {}


def _get_content_type(model_class: type[Any]) -> str | None:
    """获取模型对应的 content_type 字符串"""
    mapping = {
        FolderTemplate: "folder_template",
        DocumentTemplate: "document_template",
        Placeholder: "placeholder",
    }
    return mapping.get(model_class)


def _get_tracked_fields(model_class: type[Any]) -> list[str]:
    """获取需要追踪的字段列表"""
    common_fields = ["name", "is_active"]

    specific_fields = {
        FolderTemplate: ["case_type", "case_stage", "structure", "is_default"],
        DocumentTemplate: ["description", "category", "file", "file_path", "case_types", "version"],
        Placeholder: ["key", "display_name", "example_value"],
    }

    return common_fields + specific_fields.get(model_class, [])


def _serialize_value(value: Any) -> Any:
    """序列化字段值为可存储格式"""
    if value is None:
        return None
    if hasattr(value, "pk"):
        return value.pk
    if hasattr(value, "name"):
        return str(value.name)
    return str(value)


def _get_changes(old_instance: Any, new_instance: Any, model_class: type[Any]) -> dict[str, dict[str, Any]]:
    """比较新旧实例,获取变更内容"""
    changes: dict[str, Any] = {}
    tracked_fields = _get_tracked_fields(model_class)

    for field in tracked_fields:
        old_value = getattr(old_instance, field, None) if old_instance else None
        new_value = getattr(new_instance, field, None)

        old_serialized = _serialize_value(old_value)
        new_serialized = _serialize_value(new_value)

        if old_serialized != new_serialized:
            changes[field] = {
                "old": old_serialized,
                "new": new_serialized,
            }

    return changes


def _create_audit_log(instance: Any, action: str, changes: dict[str, Any] | None = None, is_new: bool = False) -> None:
    """创建审计日志记录"""
    model_class = instance.__class__
    content_type = _get_content_type(model_class)

    if not content_type:
        return

    try:
        TemplateAuditLog.objects.create(
            content_type=content_type,
            object_id=instance.pk,
            object_repr=str(instance)[:500],
            action=action,
            changes=changes or {},
        )
        logger.debug(f"审计日志已记录: {content_type} #{instance.pk} - {action}")
    except Exception as e:
        logger.error(f"创建审计日志失败: {e}")


# ============================================================
# Pre-save signals - 保存修改前的状态
# ============================================================


@receiver(pre_save, sender=FolderTemplate)
@receiver(pre_save, sender=DocumentTemplate)
@receiver(pre_save, sender=Placeholder)
def capture_pre_save_state(sender: type[Any], instance: Any, **kwargs: Any) -> None:
    """捕获保存前的状态"""
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            _pre_save_state[f"{sender.__name__}_{instance.pk}"] = old_instance
        except sender.DoesNotExist:
            pass


# ============================================================
# Post-save signals - 记录创建和更新
# ============================================================


@receiver(post_save, sender=FolderTemplate)
@receiver(post_save, sender=DocumentTemplate)
@receiver(post_save, sender=Placeholder)
def log_save(sender: type[Any], instance: Any, created: bool, **kwargs: Any) -> None:
    """记录创建和更新操作"""
    key = f"{sender.__name__}_{instance.pk}"
    old_instance = _pre_save_state.pop(key, None)

    if created:
        _create_audit_log(instance, TemplateAuditAction.CREATE, is_new=True)
    else:
        changes = _get_changes(old_instance, instance, sender)
        if changes:
            # 检查是否是启用/禁用操作
            if "is_active" in changes and len(changes) == 1:
                action = TemplateAuditAction.ACTIVATE if instance.is_active else TemplateAuditAction.DEACTIVATE
            elif "is_default" in changes and len(changes) == 1 and getattr(instance, "is_default", False):
                action = TemplateAuditAction.SET_DEFAULT
            else:
                action = TemplateAuditAction.UPDATE
            _create_audit_log(instance, action, changes)


# ============================================================
# Post-delete signals - 记录删除
# ============================================================


@receiver(post_delete, sender=FolderTemplate)
@receiver(post_delete, sender=DocumentTemplate)
@receiver(post_delete, sender=Placeholder)
def log_delete(sender: type[Any], instance: Any, **kwargs: Any) -> None:
    """记录删除操作"""
    _create_audit_log(instance, TemplateAuditAction.DELETE)
