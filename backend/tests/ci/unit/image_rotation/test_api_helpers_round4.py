"""Tests for image_rotation/api/image_rotation_api.py — pure helper functions.

Covers: _validate_image_file, _body, _decode_image_data, _serialize_job,
_serialize_page, filter_valid_case_numbers from sms_matching_stage.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# image_rotation_api helpers
# ---------------------------------------------------------------------------


class TestValidateImageFile:
    def test_valid_jpeg(self):
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        f = MagicMock()
        f.content_type = "image/jpeg"
        f.size = 1024
        _validate_image_file(f)  # should not raise

    def test_valid_png(self):
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        f = MagicMock()
        f.content_type = "image/png"
        f.size = 1024
        _validate_image_file(f)

    def test_invalid_type(self):
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        from apps.core.exceptions import ValidationException
        f = MagicMock()
        f.content_type = "application/pdf"
        f.size = 1024
        with pytest.raises(ValidationException):
            _validate_image_file(f)

    def test_too_large(self):
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        from apps.core.exceptions import ValidationException
        f = MagicMock()
        f.content_type = "image/jpeg"
        f.size = 25 * 1024 * 1024  # 25MB
        with pytest.raises(ValidationException):
            _validate_image_file(f)

    def test_none_size_ok(self):
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        f = MagicMock()
        f.content_type = "image/jpeg"
        f.size = None
        _validate_image_file(f)  # should not raise


class TestBody:
    def test_parses_json(self):
        from apps.image_rotation.api.image_rotation_api import _body
        req = MagicMock()
        req.body = b'{"key": "value"}'
        result = _body(req)
        assert result == {"key": "value"}

    def test_empty_body(self):
        from apps.image_rotation.api.image_rotation_api import _body
        req = MagicMock()
        req.body = b""
        result = _body(req)
        assert result == {}

    def test_none_body(self):
        from apps.image_rotation.api.image_rotation_api import _body
        req = MagicMock()
        req.body = None
        result = _body(req)
        assert result == {}


class TestDecodeImageData:
    def test_plain_base64(self):
        from apps.image_rotation.api.image_rotation_api import _decode_image_data
        data = base64.b64encode(b"hello").decode()
        result = _decode_image_data(data)
        assert result == b"hello"

    def test_data_url_prefix(self):
        from apps.image_rotation.api.image_rotation_api import _decode_image_data
        raw = base64.b64encode(b"image data").decode()
        data_url = f"data:image/png;base64,{raw}"
        result = _decode_image_data(data_url)
        assert result == b"image data"


class TestSerializeJob:
    def test_serializes_job(self):
        from apps.image_rotation.api.image_rotation_api import _serialize_job
        job = MagicMock()
        job.id = 1
        job.name = "Test Job"
        job.status = "completed"
        job.total_pages = 5
        job.export_zip_url = "https://example.com/export.zip"
        job.export_pdf_url = ""
        job.created_at = MagicMock(isoformat=MagicMock(return_value="2025-06-01T10:00:00"))

        result = _serialize_job(job)
        assert result["id"] == "1"
        assert result["name"] == "Test Job"
        assert result["display_name"] == "Test Job"
        assert result["has_export_zip"] is True
        assert result["has_export_pdf"] is False

    def test_empty_name_fallback(self):
        from apps.image_rotation.api.image_rotation_api import _serialize_job
        job = MagicMock()
        job.id = 1
        job.name = ""
        job.status = "pending"
        job.total_pages = 0
        job.export_zip_url = ""
        job.export_pdf_url = ""
        job.created_at = None

        result = _serialize_job(job)
        assert result["display_name"] == "未命名任务"


class TestSerializePage:
    def test_serializes_page(self):
        from apps.image_rotation.api.image_rotation_api import _serialize_page
        page = MagicMock()
        page.id = 1
        page.original_filename = "scan.jpg"
        page.source_image = MagicMock()
        page.source_image.url = "/media/scan.jpg"
        page.page_number = 1
        page.detected_rotation = 90
        page.detection_confidence = 0.95123
        page.ocr_text = "text"
        page.suggested_filename = "文件.pdf"
        page.source_type = "upload"

        result = _serialize_page(page)
        assert result["id"] == "1"
        assert result["original_filename"] == "scan.jpg"
        assert result["detected_rotation"] == 90
        assert result["detection_confidence"] == 0.9512
        assert result["source_type"] == "upload"

    def test_no_source_image(self):
        from apps.image_rotation.api.image_rotation_api import _serialize_page
        page = MagicMock()
        page.id = 1
        page.original_filename = "scan.jpg"
        page.source_image = None
        page.page_number = 1
        page.detected_rotation = 0
        page.detection_confidence = 0.0
        page.ocr_text = ""
        page.suggested_filename = ""
        page.source_type = "pdf"

        result = _serialize_page(page)
        assert result["source_image_url"] == ""


# ---------------------------------------------------------------------------
# filter_valid_case_numbers from sms_matching_stage
# ---------------------------------------------------------------------------


class TestFilterValidCaseNumbers:
    def test_filters_date_format(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers
        result = filter_valid_case_numbers([
            "2025年6月1日",
            "（2025）粤01民初100号",
            "2025年12月17号",
        ])
        assert "（2025）粤01民初100号" in result
        assert len(result) == 1

    def test_empty_list(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers
        assert filter_valid_case_numbers([]) == []

    def test_all_valid(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers
        nums = ["（2025）粤01民初100号", "（2024）京0101民初50号"]
        result = filter_valid_case_numbers(nums)
        assert len(result) == 2

    def test_filters_year_month_day_pattern(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers
        result = filter_valid_case_numbers(["2025年6月1号", "正常案号"])
        assert "正常案号" in result
        assert len(result) == 1
