"""Module for choices."""

from django.db import models


class ExportType(models.TextChoices):
    PDF = "pdf", "PDF"
    DOCX = "docx", "Word"


class ExportStatus(models.TextChoices):
    PENDING = "pending", "待处理"
    RUNNING = "running", "处理中"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class ScreenshotSource(models.TextChoices):
    UNKNOWN = "unknown", "未知"
    EXTRACT = "extract", "视频抽帧"
    UPLOAD = "upload", "手动上传"


class ExtractStatus(models.TextChoices):
    PENDING = "pending", "待处理"
    RUNNING = "running", "处理中"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class ExtractStrategy(models.TextChoices):
    INTERVAL = "interval", "固定间隔"
    SCENE = "scene", "画面变化优先"
    SMART = "smart", "智能去重"
    KEYFRAME = "keyframe", "关键帧(I帧)"
    OCR = "ocr", "OCR 文本变化优先"
