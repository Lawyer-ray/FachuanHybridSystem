"""Module for signals."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models.signals import post_delete
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
        FolderTemplate: ["case_types", "case_stages", "structure", "is_default"],
        DocumentTemplate: ["template_type", "contract_sub_type", "case_sub_type", "file", "file_path", "case_types", "case_stages", "contract_types"],
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


def _get_changes_from_lifecycle(instance: Any, model_class: type[Any]) -> dict[str, dict[str, Any]]:
    """利用 django-lifecycle 的 initial_value() 对比变更内容（替代 threading.local 模式）"""
    changes: dict[str, Any] = {}
    tracked_fields = _get_tracked_fields(model_class)

    for field in tracked_fields:
        if not instance.has_changed(field):
            continue

        old_val = instance.initial_value(field)
        new_value = getattr(instance, field, None)

        old_serialized = _serialize_value(old_val)
        new_serialized = _serialize_value(new_value)

        if old_serialized != new_serialized:
            changes[field] = {
                "old": old_serialized,
                "new": new_serialized,
            }

    return changes


def _get_changes(old_instance: Any, new_instance: Any, model_class: type[Any]) -> dict[str, dict[str, Any]]:
    """比较新旧实例,获取变更内容（兼容旧调用）"""
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
# Post-delete signals - 记录删除 & 物理文件清理
# ============================================================


@receiver(post_delete, sender=FolderTemplate)
@receiver(post_delete, sender=DocumentTemplate)
@receiver(post_delete, sender=Placeholder)
def log_delete(sender: type[Any], instance: Any, **kwargs: Any) -> None:
    """记录删除操作"""
    _create_audit_log(instance, TemplateAuditAction.DELETE)

    # 使模板匹配缓存失效（替代 Model 层的 delete() override）
    _invalidate_template_matching_cache(sender)


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
