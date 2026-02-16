# Re-export all models and choices for backward compatibility
# 保持向后兼容:from apps.chat_records.models import XXX 继续可用

from .choices import ExportStatus, ExportType, ExtractStatus, ExtractStrategy, ScreenshotSource
from .export_task import ChatRecordExportTask, _export_upload_to
from .project import ChatRecordProject
from .recording import ChatRecordRecording, _recording_upload_to
from .screenshot import ChatRecordScreenshot, _screenshot_upload_to

__all__ = [
    # Choices
    "ExportType",
    "ExportStatus",
    "ScreenshotSource",
    "ExtractStatus",
    "ExtractStrategy",
    # Models
    "ChatRecordProject",
    "ChatRecordScreenshot",
    "ChatRecordRecording",
    "ChatRecordExportTask",
    # Upload path helpers (needed for migrations)
    "_screenshot_upload_to",
    "_recording_upload_to",
    "_export_upload_to",
]
