"""Module for signals."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ChatRecordExportTask, ChatRecordRecording, ChatRecordScreenshot

logger = logging.getLogger("apps.chat_records")


def _safe_prune_empty_parents(file_path: str | None) -> None:
    if not file_path:
        return
    try:
        p = Path(file_path).resolve()
    except Exception:
        # 静默处理:路径解析失败不影响主流程
        logger.debug("文件路径解析失败: %s", file_path)
        return
    try:
        media_root = Path(settings.MEDIA_ROOT).resolve()
    except Exception:
        # 静默处理:MEDIA_ROOT 解析失败不影响主流程
        logger.debug("MEDIA_ROOT 解析失败, 原始文件路径: %s", file_path)
        return

    if not p.is_absolute():
        return
    if media_root not in p.parents:
        return

    stop_at = (media_root / "chat_records").resolve()
    cur = p.parent
    while True:
        if cur in (media_root, stop_at):
            break
        try:
            cur.rmdir()
        except Exception:
            # 静默处理:目录删除失败(可能非空或权限问题)不影响主流程
            logger.debug("空目录清理失败: %s", cur)
            break
        cur = cur.parent


def _delete_field_file(field_file: Any) -> None:
    if not field_file:
        return
    old_path = None
    try:
        old_path = field_file.path
    except Exception:
        # 静默处理:获取文件路径失败不影响主流程
        logger.debug("获取文件路径失败: %s", field_file)
        old_path = None
    try:
        field_file.delete(save=False)
    except Exception:
        # 静默处理:文件删除失败不影响主流程
        logger.debug("文件删除失败: %s", old_path or field_file)
        return
    _safe_prune_empty_parents(old_path)


def _delete_field_file_by_name(old_name: str | None) -> None:
    """根据 FieldFile 存储的文件名字符串删除物理文件（供 django-lifecycle @hook 使用）"""
    if not old_name:
        return
    try:
        from django.core.files.storage import default_storage

        if default_storage.exists(old_name):
            default_storage.delete(old_name)
            logger.debug("已删除旧文件: %s", old_name)
            # 尝试清理空目录
            _safe_prune_empty_parents(default_storage.path(old_name) if hasattr(default_storage, "path") else None)
    except Exception:
        logger.debug("删除旧文件失败: %s", old_name)


@receiver(post_delete, sender=ChatRecordRecording)
def _delete_recording_file(sender: Any, instance: ChatRecordRecording, **kwargs: Any) -> None:
    _delete_field_file(getattr(instance, "video", None))


@receiver(post_delete, sender=ChatRecordScreenshot)
def _delete_screenshot_file(sender: Any, instance: ChatRecordScreenshot, **kwargs: Any) -> None:
    _delete_field_file(getattr(instance, "image", None))


@receiver(post_delete, sender=ChatRecordExportTask)
def _delete_export_file(sender: Any, instance: ChatRecordExportTask, **kwargs: Any) -> None:
    _delete_field_file(getattr(instance, "output_file", None))
