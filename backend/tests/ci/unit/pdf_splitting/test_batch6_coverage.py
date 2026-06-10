"""Batch 6 coverage tests for pdf_splitting module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestTemplateRegistry:
    def test_get_template_definition_default(self):
        from apps.pdf_splitting.services.template_registry import (
            get_template_definition,
        )

        template = get_template_definition("nonexistent")
        assert template.key == "filing_materials_v1"

    def test_get_template_definition_known(self):
        from apps.pdf_splitting.services.template_registry import (
            get_template_definition,
        )

        template = get_template_definition("filing_materials_v1")
        assert template.key == "filing_materials_v1"
        assert template.version == "1"
        assert len(template.rules) > 0

    def test_get_segment_label_known(self):
        from apps.pdf_splitting.services.template_registry import get_segment_label

        label = get_segment_label("complaint")
        assert label == "起诉状"

    def test_get_segment_label_evidence_list(self):
        from apps.pdf_splitting.services.template_registry import get_segment_label

        label = get_segment_label("evidence_list")
        assert label == "证据清单及明细"

    def test_get_segment_label_unrecognized(self):
        from apps.pdf_splitting.models import PdfSplitSegmentType
        from apps.pdf_splitting.services.template_registry import get_segment_label

        label = get_segment_label(PdfSplitSegmentType.UNRECOGNIZED)
        assert label == "未识别材料"

    def test_get_segment_label_unknown_type(self):
        from apps.pdf_splitting.services.template_registry import get_segment_label

        label = get_segment_label("unknown_type_xyz")
        assert label == "unknown_type_xyz"

    def test_get_default_filename_known(self):
        from apps.pdf_splitting.services.template_registry import (
            get_default_filename,
        )

        assert get_default_filename("complaint") == "起诉状"

    def test_get_default_filename_unknown(self):
        from apps.pdf_splitting.services.template_registry import (
            get_default_filename,
        )

        assert get_default_filename("unknown") == "未识别材料"

    def test_filing_materials_rules_have_keywords(self):
        from apps.pdf_splitting.services.template_registry import (
            FILING_MATERIALS_V1,
        )

        for rule in FILING_MATERIALS_V1.rules:
            assert len(rule.strong_keywords) > 0
            assert rule.label
            assert rule.default_filename


class TestPdfSplitStorage:
    def test_init_with_string_id(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        storage = PdfSplitStorage("test-id-123")
        assert storage._job_id == "test-id-123"

    def test_init_with_uuid(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        job_id = uuid4()
        storage = PdfSplitStorage(job_id)
        assert storage._job_id == str(job_id)

    def test_dir_properties(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        storage = PdfSplitStorage("test-job")
        assert "pdf_splitting" in str(storage.job_root)
        assert storage.source_dir.name == "source"
        assert storage.analysis_dir.name == "analysis"
        assert storage.previews_dir.name == "previews"
        assert storage.exports_dir.name == "exports"

    def test_file_path_properties(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        storage = PdfSplitStorage("test-job")
        assert storage.source_pdf_path.name == "original.pdf"
        assert storage.pages_json_path.name == "pages.json"
        assert storage.segments_json_path.name == "segments.json"
        assert storage.export_zip_path.name == "split_result.zip"

    def test_preview_path(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        storage = PdfSplitStorage("test-job")
        path = storage.preview_path(1)
        assert path.name == "page_001.png"

        path = storage.preview_path(42)
        assert path.name == "page_042.png"

    def test_export_pdf_path(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        storage = PdfSplitStorage("test-job")
        path = storage.export_pdf_path("result.pdf")
        assert path.name == "result.pdf"

    def test_ensure_dirs(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("django.conf.settings.MEDIA_ROOT", tmpdir):
                storage = PdfSplitStorage("test-ensure")
                storage.ensure_dirs()
                assert storage.source_dir.exists()
                assert storage.analysis_dir.exists()
                assert storage.previews_dir.exists()
                assert storage.exports_dir.exists()

    def test_write_read_json(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("django.conf.settings.MEDIA_ROOT", tmpdir):
                storage = PdfSplitStorage("test-json")
                storage.ensure_dirs()
                data = {"key": "value", "items": [1, 2, 3]}
                storage.write_json(storage.pages_json_path, data)
                loaded = storage.read_json(storage.pages_json_path, {})
                assert loaded == data

    def test_read_json_default(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("django.conf.settings.MEDIA_ROOT", tmpdir):
                storage = PdfSplitStorage("test-default")
                result = storage.read_json(Path("/nonexistent/file.json"), {"default": True})
                assert result == {"default": True}

    def test_cleanup(self):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("django.conf.settings.MEDIA_ROOT", tmpdir):
                storage = PdfSplitStorage("test-cleanup")
                storage.ensure_dirs()
                assert storage.job_root.exists()
                storage.cleanup()
                assert not storage.job_root.exists()
