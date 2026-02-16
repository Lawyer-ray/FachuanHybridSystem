"""Module for signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import ChatRecordExportTask, ChatRecordRecording, ChatRecordScreenshot


def _safe_prune_empty_parents(file_path: str | None) -> None:
    if not file_path:
        return
    try:
        p = Path(file_path).resolve()
    except Exception:
        # 静默处理:路径解析失败不影响主流程
        return
    try:
        media_root = Path(settings.MEDIA_ROOT).resolve()
    except Exception:
        # 静默处理:MEDIA_ROOT 解析失败不影响主流程
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
        old_path = None
    try:
        field_file.delete(save=False)
    except Exception:
        # 静默处理:文件删除失败不影响主流程
        return
    _safe_prune_empty_parents(old_path)


@receiver(post_delete, sender=ChatRecordRecording)
def _delete_recording_file(sender: Any, instance: ChatRecordRecording, **kwargs: Any) -> None:
    _delete_field_file(getattr(instance, "video", None))


@receiver(post_delete, sender=ChatRecordScreenshot)
def _delete_screenshot_file(sender: Any, instance: ChatRecordScreenshot, **kwargs: Any) -> None:
    _delete_field_file(getattr(instance, "image", None))


@receiver(post_delete, sender=ChatRecordExportTask)
def _delete_export_file(sender: Any, instance: ChatRecordExportTask, **kwargs: Any) -> None:
    _delete_field_file(getattr(instance, "output_file", None))


@receiver(pre_save, sender=ChatRecordRecording)
def _delete_old_recording_on_change(sender: Any, instance: ChatRecordRecording, **kwargs: Any) -> None:
    if not instance.pk:
        return
    try:
        old = ChatRecordRecording.objects.get(pk=instance.pk)
    except ChatRecordRecording.DoesNotExist:
        return
    old_video = getattr(old, "video", None)
    instance_video = getattr(instance, "video", None)
    if old_video and instance_video and old_video.name != instance_video.name:
        _delete_field_file(old_video)


@receiver(pre_save, sender=ChatRecordScreenshot)
def _delete_old_screenshot_on_change(sender: Any, instance: ChatRecordScreenshot, **kwargs: Any) -> None:
    if not instance.pk:
        return
    try:
        old = ChatRecordScreenshot.objects.get(pk=instance.pk)
    except ChatRecordScreenshot.DoesNotExist:
        return
    old_image = getattr(old, "image", None)
    instance_image = getattr(instance, "image", None)
    if old_image and instance_image and old_image.name != instance_image.name:
        _delete_field_file(old_image)


@receiver(pre_save, sender=ChatRecordExportTask)
def _delete_old_export_on_change(sender: Any, instance: ChatRecordExportTask, **kwargs: Any) -> None:
    if not instance.pk:
        return
    try:
        old = ChatRecordExportTask.objects.get(pk=instance.pk)
    except ChatRecordExportTask.DoesNotExist:
        return
    old_output = getattr(old, "output_file", None)
    instance_output = getattr(instance, "output_file", None)
    if old_output and instance_output and old_output.name != instance_output.name:
        _delete_field_file(old_output)
