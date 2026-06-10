"""Batch7 coverage tests for apps.chat_records."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.chat_records.models.choices import (
    ExportStatus,
    ExportType,
    ExtractStatus,
    ExtractStrategy,
    ScreenshotSource,
)


# ── ExportType ──────────────────────────────────────────────────────────────


class TestExportType:
    def test_pdf(self) -> None:
        assert ExportType.PDF == "pdf"

    def test_docx(self) -> None:
        assert ExportType.DOCX == "docx"


# ── ExportStatus ────────────────────────────────────────────────────────────


class TestExportStatus:
    def test_pending(self) -> None:
        assert ExportStatus.PENDING == "pending"

    def test_running(self) -> None:
        assert ExportStatus.RUNNING == "running"

    def test_success(self) -> None:
        assert ExportStatus.SUCCESS == "success"

    def test_failed(self) -> None:
        assert ExportStatus.FAILED == "failed"


# ── ScreenshotSource ────────────────────────────────────────────────────────


class TestScreenshotSource:
    def test_unknown(self) -> None:
        assert ScreenshotSource.UNKNOWN == "unknown"

    def test_extract(self) -> None:
        assert ScreenshotSource.EXTRACT == "extract"

    def test_upload(self) -> None:
        assert ScreenshotSource.UPLOAD == "upload"


# ── ExtractStatus ───────────────────────────────────────────────────────────


class TestExtractStatus:
    def test_pending(self) -> None:
        assert ExtractStatus.PENDING == "pending"

    def test_running(self) -> None:
        assert ExtractStatus.RUNNING == "running"

    def test_success(self) -> None:
        assert ExtractStatus.SUCCESS == "success"

    def test_failed(self) -> None:
        assert ExtractStatus.FAILED == "failed"


# ── ExtractStrategy ─────────────────────────────────────────────────────────


class TestExtractStrategy:
    def test_interval(self) -> None:
        assert ExtractStrategy.INTERVAL == "interval"

    def test_scene(self) -> None:
        assert ExtractStrategy.SCENE == "scene"

    def test_smart(self) -> None:
        assert ExtractStrategy.SMART == "smart"

    def test_keyframe(self) -> None:
        assert ExtractStrategy.KEYFRAME == "keyframe"

    def test_ocr(self) -> None:
        assert ExtractStrategy.OCR == "ocr"
