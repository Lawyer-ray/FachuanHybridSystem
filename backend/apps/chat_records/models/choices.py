"""Module for choices."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class ExportType(models.TextChoices):
    PDF = "pdf", _("PDF")
    DOCX = "docx", _("Word")


class ExportStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    RUNNING = "running", _("处理中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class ScreenshotSource(models.TextChoices):
    UNKNOWN = "unknown", _("未知")
    EXTRACT = "extract", _("视频抽帧")
    UPLOAD = "upload", _("手动上传")


class ExtractStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    RUNNING = "running", _("处理中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class ExtractStrategy(models.TextChoices):
    INTERVAL = "interval", _("固定间隔")
    SCENE = "scene", _("画面变化优先")
    SMART = "smart", _("智能去重")
    KEYFRAME = "keyframe", _("关键帧(I帧)")
    OCR = "ocr", _("OCR 文本变化优先")
