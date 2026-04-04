"""Module for signals."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import (
    BatchFillTask,
    DocumentTemplate,
    ExternalTemplate,
    FillRecord,
    FolderTemplate,
    GenerationTask,
    Placeholder,
    TemplateAuditAction,
)

logger = logging.getLogger(__name__)

# 线程安全的 pre_save 状态存储
_thread_local = threading.local()


def _get_pre_save_state() -> dict[str, Any]:
    if not hasattr(_thread_local, "pre_save_state"):
        _thread_local.pre_save_state: dict[str, Any] = {}
    result = _thread_local.pre_save_state
    if not isinstance(result, dict):
        raise TypeError(f"pre_save_state 不是 dict: {type(result)}")
    return result


def _get_audit_log_service() -> Any:
    """工厂函数：延迟导入并实例化 TemplateAuditLogService。"""
    try:
        from .services.template.template_audit_log_service import TemplateAuditLogService

        return TemplateAuditLogService()
    except (ImportError, ModuleNotFoundError):
        logger.debug("TemplateAuditLogService 不可用，跳过审计日志")
        return None


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
        DocumentTemplate: ["category", "file", "file_path", "case_types", "version"],
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

    svc = _get_audit_log_service()
    if svc is None:
        return

    svc.create_audit_log(content_type, instance.pk, str(instance)[:500], action, changes or {})


# ============================================================
# Pre-save signals - 保存修改前的状态
# ============================================================


@receiver(pre_save, sender=FolderTemplate)
@receiver(pre_save, sender=DocumentTemplate)
@receiver(pre_save, sender=Placeholder)
def capture_pre_save_state(sender: type[Any], instance: Any, **kwargs: Any) -> None:
    """捕获保存前的状态"""
    if instance.pk:
        svc = _get_audit_log_service()
        if svc is None:
            return
        old_instance = svc.get_instance_by_pk(sender, instance.pk)
        if old_instance is not None:
            _get_pre_save_state()[f"{sender.__name__}_{instance.pk}"] = old_instance


# ============================================================
# Post-save signals - 记录创建和更新
# ============================================================


@receiver(post_save, sender=FolderTemplate)
@receiver(post_save, sender=DocumentTemplate)
@receiver(post_save, sender=Placeholder)
def log_save(sender: type[Any], instance: Any, created: bool, **kwargs: Any) -> None:
    """记录创建和更新操作，并使相关缓存失效"""
    key = f"{sender.__name__}_{instance.pk}"
    old_instance = _get_pre_save_state().pop(key, None)

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

    # 使模板匹配缓存失效
    _invalidate_template_matching_cache(sender)


# ============================================================
# Post-delete signals - 记录删除
# ============================================================


@receiver(post_delete, sender=FolderTemplate)
@receiver(post_delete, sender=DocumentTemplate)
@receiver(post_delete, sender=Placeholder)
def log_delete(sender: type[Any], instance: Any, **kwargs: Any) -> None:
    """记录删除操作"""
    _create_audit_log(instance, TemplateAuditAction.DELETE)

    # 使模板匹配缓存失效（替代 Model 层的 delete() override）
    _invalidate_template_matching_cache(sender)


def _invalidate_template_matching_cache(sender: type[Any]) -> None:
    """根据 sender 类型递增对应的版本号缓存，使模板匹配缓存失效"""
    try:
        from apps.core.infrastructure import CacheKeys, CacheTimeout
        from apps.core.infrastructure.cache import bump_cache_version

        if sender is DocumentTemplate:
            version_key = CacheKeys.documents_matching_version_document_templates()
        elif sender is FolderTemplate:
            version_key = CacheKeys.documents_matching_version_folder_templates()
        else:
            return

        bump_cache_version(version_key, timeout=CacheTimeout.get_day())
        logger.debug("已递增模板匹配缓存版本号: %s", version_key)
    except Exception as e:
        logger.warning("清除模板匹配缓存失败: %s", e)


# ============================================================
# Post-delete signals - 物理文件清理
# ============================================================


def _delete_charfield_file(file_path_str: str | None) -> None:
    """删除 CharField 中存储的文件路径对应的物理文件"""
    if not file_path_str:
        return
    file_path = Path(file_path_str)
    if not file_path.is_absolute():
        file_path = Path(settings.MEDIA_ROOT) / file_path_str
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info("已清理文档物理文件", extra={"file_path": str(file_path)})
        except OSError as exc:
            logger.error("清理文档物理文件失败", extra={"file_path": str(file_path), "error": str(exc)})


def _delete_file_field(field_file: Any) -> None:
    """删除 FileField 对应的物理文件"""
    if field_file:
        try:
            field_file.delete(save=False)
            logger.info("已清理文档 FileField 物理文件", extra={"file_path": str(field_file)})
        except Exception:
            logger.exception("清理文档 FileField 失败")


@receiver(post_delete, dispatch_uid="cleanup_document_template_files")
def cleanup_document_template_files(sender: type[Any], instance: Any, **kwargs: object) -> None:
    """
    DocumentTemplate 有两个文件字段：
    - file (FileField): 上传的模板文件 → 用 .delete(save=False)
    - file_path (CharField): 引用静态目录的 docx 模板，不需要清理（非用户上传）
    """
    if sender is DocumentTemplate and instance.file:
        _delete_file_field(instance.file)


@receiver(post_delete, dispatch_uid="cleanup_generation_task_result")
def cleanup_generation_task_result(sender: type[Any], instance: Any, **kwargs: object) -> None:
    """GenerationTask.result_file (FileField): 文书生成结果文件"""
    if sender is GenerationTask:
        _delete_file_field(instance.result_file)


@receiver(post_delete, dispatch_uid="cleanup_external_template_file")
def cleanup_external_template_file(sender: type[Any], instance: Any, **kwargs: object) -> None:
    """ExternalTemplate.file_path (CharField): 外部上传的 Word 模板文件，存于 MEDIA_ROOT 下"""
    if sender is ExternalTemplate:
        _delete_charfield_file(instance.file_path)


@receiver(post_delete, dispatch_uid="cleanup_fill_record_file")
def cleanup_fill_record_file(sender: type[Any], instance: Any, **kwargs: object) -> None:
    """FillRecord.file_path (CharField): 填充生成的文件，存于 MEDIA_ROOT 下"""
    if sender is FillRecord:
        _delete_charfield_file(instance.file_path)


@receiver(post_delete, dispatch_uid="cleanup_batch_fill_task_zip")
def cleanup_batch_fill_task_zip(sender: type[Any], instance: Any, **kwargs: object) -> None:
    """BatchFillTask.zip_file_path (CharField): 批量填充 ZIP 压缩包"""
    if sender is BatchFillTask:
        _delete_charfield_file(instance.zip_file_path)
