"""Batch 6 coverage tests for chat_records module."""

from __future__ import annotations

import pytest


class TestChatRecordChoices:
    def test_export_type_values(self):
        from apps.chat_records.models.choices import ExportType

        assert ExportType.PDF == "pdf"
        assert ExportType.DOCX == "docx"

    def test_export_status_values(self):
        from apps.chat_records.models.choices import ExportStatus

        assert ExportStatus.PENDING == "pending"
        assert ExportStatus.RUNNING == "running"
        assert ExportStatus.SUCCESS == "success"
        assert ExportStatus.FAILED == "failed"

    def test_screenshot_source_values(self):
        from apps.chat_records.models.choices import ScreenshotSource

        assert ScreenshotSource.UNKNOWN == "unknown"
        assert ScreenshotSource.EXTRACT == "extract"
        assert ScreenshotSource.UPLOAD == "upload"

    def test_extract_status_values(self):
        from apps.chat_records.models.choices import ExtractStatus

        assert ExtractStatus.PENDING == "pending"
        assert ExtractStatus.SUCCESS == "success"

    def test_extract_strategy_values(self):
        from apps.chat_records.models.choices import ExtractStrategy

        assert ExtractStrategy.INTERVAL == "interval"
        assert ExtractStrategy.SCENE == "scene"
        assert ExtractStrategy.SMART == "smart"
        assert ExtractStrategy.KEYFRAME == "keyframe"
        assert ExtractStrategy.OCR == "ocr"
