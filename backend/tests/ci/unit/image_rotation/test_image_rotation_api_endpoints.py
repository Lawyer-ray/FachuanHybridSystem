"""Tests for image_rotation/api/image_rotation_api.py — endpoint functions.

Covers: extract_pdf_fast, detect_page_orientation, detect_orientation,
        extract_text, suggest_rename, export_pdf, export_images,
        _handle_multipart_export_pdf, _handle_multipart_export,
        create_job, list_jobs, get_job_detail, run_job_ocr,
        update_job_pages, save_export_url, update_job_name, delete_job.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.image_rotation.api.image_rotation_api import (
    _get_pdf_service,
    _get_rename_service,
    _get_rotation_service,
    _ALLOWED_IMAGE_TYPES,
    _MAX_UPLOAD_SIZE,
)


# ── Constants ────────────────────────────────────────────────────


class TestModuleConstants:
    def test_allowed_image_types(self) -> None:
        assert "image/jpeg" in _ALLOWED_IMAGE_TYPES
        assert "image/png" in _ALLOWED_IMAGE_TYPES
        assert "image/webp" in _ALLOWED_IMAGE_TYPES
        assert "image/tiff" in _ALLOWED_IMAGE_TYPES
        assert "image/gif" not in _ALLOWED_IMAGE_TYPES

    def test_max_upload_size(self) -> None:
        assert _MAX_UPLOAD_SIZE == 20 * 1024 * 1024


# ── extract_pdf_fast ─────────────────────────────────────────────


class TestExtractPdfFast:
    def test_no_data(self) -> None:
        from apps.image_rotation.api.image_rotation_api import extract_pdf_fast

        req = MagicMock()
        req.body = json.dumps({"filename": "test.pdf"}).encode()
        result = extract_pdf_fast(req)
        assert result["success"] is False
        assert "缺少 data 参数" in result["message"]

    def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import extract_pdf_fast

        req = MagicMock()
        req.body = json.dumps({"filename": "test.pdf", "data": "base64data"}).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_pdf_service") as mock_svc:
            mock_svc.return_value.extract_pages.return_value = {"success": True, "pages": []}
            result = extract_pdf_fast(req)
            assert result["success"] is True

    def test_exception_handling(self) -> None:
        from apps.image_rotation.api.image_rotation_api import extract_pdf_fast

        req = MagicMock()
        req.body = json.dumps({"data": "base64data"}).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_pdf_service") as mock_svc:
            mock_svc.return_value.extract_pages.side_effect = RuntimeError("boom")
            result = extract_pdf_fast(req)
            assert result["success"] is False
            assert "boom" in result["message"]


# ── detect_page_orientation ──────────────────────────────────────


class TestDetectPageOrientation:
    def test_no_data(self) -> None:
        from apps.image_rotation.api.image_rotation_api import detect_page_orientation

        req = MagicMock()
        req.body = json.dumps({}).encode()
        result = detect_page_orientation(req)
        assert result["rotation"] == 0
        assert result["confidence"] == 0

    def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import detect_page_orientation

        req = MagicMock()
        req.body = json.dumps({"data": "imgdata"}).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_pdf_service") as mock_svc:
            mock_svc.return_value.detect_single_page_orientation.return_value = {
                "rotation": 90,
                "confidence": 0.95,
            }
            result = detect_page_orientation(req)
            assert result["rotation"] == 90
            assert "elapsed_ms" in result

    def test_exception(self) -> None:
        from apps.image_rotation.api.image_rotation_api import detect_page_orientation

        req = MagicMock()
        req.body = json.dumps({"data": "bad"}).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_pdf_service") as mock_svc:
            mock_svc.return_value.detect_single_page_orientation.side_effect = RuntimeError("err")
            result = detect_page_orientation(req)
            assert result["rotation"] == 0


# ── detect_orientation ───────────────────────────────────────────


class TestDetectOrientation:
    @pytest.mark.asyncio
    async def test_no_images(self) -> None:
        from apps.image_rotation.api.image_rotation_api import detect_orientation

        req = MagicMock()
        req.body = json.dumps({}).encode()
        result = await detect_orientation(req)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_onnx_method(self) -> None:
        from apps.image_rotation.api.image_rotation_api import detect_orientation

        img_data = base64.b64encode(b"fakeimg").decode()
        req = MagicMock()
        req.body = json.dumps({"images": [{"data": img_data, "filename": "a.jpg"}], "method": "onnx"}).encode()
        with patch("apps.image_rotation.services.orientation.onnx_service.get_onnx_orientation_service") as mock_onnx:
            mock_onnx.return_value.detect_orientation.return_value = {
                "rotation": 180,
                "confidence": 0.9,
                "ocr_text": "",
            }
            result = await detect_orientation(req)
            assert result["success"] is True
            assert result["results"][0]["rotation"] == 180

    @pytest.mark.asyncio
    async def test_ocr_voting_method(self) -> None:
        from apps.image_rotation.api.image_rotation_api import detect_orientation

        img_data = base64.b64encode(b"fakeimg").decode()
        req = MagicMock()
        req.body = json.dumps(
            {
                "images": [{"data": img_data, "filename": "b.jpg"}],
                "method": "ocr_voting",
            }
        ).encode()
        with patch("apps.image_rotation.services.orientation.service.OrientationDetectionService") as mock_od:
            mock_od.return_value.detect_orientation_with_text.return_value = {
                "rotation": 0,
                "confidence": 0.8,
                "ocr_text": "text",
            }
            result = await detect_orientation(req)
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_exception_in_image(self) -> None:
        from apps.image_rotation.api.image_rotation_api import detect_orientation

        req = MagicMock()
        req.body = json.dumps(
            {
                "images": [{"data": "invalid_b64!!!", "filename": "bad.jpg"}],
                "method": "onnx",
            }
        ).encode()
        result = await detect_orientation(req)
        assert result["success"] is True
        assert result["results"][0]["rotation"] == 0  # fallback


# ── extract_text ─────────────────────────────────────────────────


class TestExtractText:
    @pytest.mark.asyncio
    async def test_no_images(self) -> None:
        from apps.image_rotation.api.image_rotation_api import extract_text

        req = MagicMock()
        req.body = json.dumps({}).encode()
        result = await extract_text(req)
        assert result["success"] is True
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import extract_text

        img_data = base64.b64encode(b"img").decode()
        req = MagicMock()
        req.body = json.dumps({"images": [{"data": img_data, "filename": "a.jpg"}]}).encode()
        with patch("apps.automation.services.ocr.ocr_service.OCRService") as MockOCR:
            mock_result = MagicMock()
            mock_result.text = "hello"
            mock_result.raw_texts = ["hello"]
            MockOCR.return_value.extract_text.return_value = mock_result
            result = await extract_text(req)
            assert result["success"] is True
            assert result["results"][0]["ocr_text"] == "hello"

    @pytest.mark.asyncio
    async def test_exception(self) -> None:
        from apps.image_rotation.api.image_rotation_api import extract_text

        req = MagicMock()
        req.body = json.dumps({"images": [{"data": "bad!!!", "filename": "x.jpg"}]}).encode()
        result = await extract_text(req)
        assert result["success"] is True
        assert result["results"][0]["ocr_text"] == ""


# ── suggest_rename ───────────────────────────────────────────────


class TestSuggestRename:
    @pytest.mark.asyncio
    async def test_no_items(self) -> None:
        from apps.image_rotation.api.image_rotation_api import suggest_rename

        req = MagicMock()
        req.body = json.dumps({}).encode()
        result = await suggest_rename(req)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import suggest_rename

        req = MagicMock()
        req.body = json.dumps(
            {
                "items": [{"filename": "old.jpg", "ocr_text": "text"}],
            }
        ).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_rename_service") as mock_svc:
            suggestion = SimpleNamespace(
                original_filename="old.jpg",
                suggested_filename="new.pdf",
                date="2025-01-01",
                amount=100,
                success=True,
            )
            mock_svc.return_value.suggest_rename_batch.return_value = [suggestion]
            result = await suggest_rename(req)
            assert result["success"] is True
            assert result["suggestions"][0]["suggested_filename"] == "new.pdf"

    @pytest.mark.asyncio
    async def test_with_image_data(self) -> None:
        from apps.image_rotation.api.image_rotation_api import suggest_rename

        img_b64 = base64.b64encode(b"raw").decode()
        req = MagicMock()
        req.body = json.dumps(
            {
                "items": [{"filename": "a.jpg", "image_data": img_b64, "rotation": 90}],
            }
        ).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_rename_service") as mock_svc:
            suggestion = SimpleNamespace(
                original_filename="a.jpg",
                suggested_filename="a.pdf",
                date="",
                amount=0,
                success=True,
            )
            mock_svc.return_value.suggest_rename_batch.return_value = [suggestion]
            result = await suggest_rename(req)
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_bad_image_data_still_works(self) -> None:
        from apps.image_rotation.api.image_rotation_api import suggest_rename

        req = MagicMock()
        req.body = json.dumps(
            {
                "items": [{"filename": "a.jpg", "image_data": "not_valid_base64!!!"}],
            }
        ).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_rename_service") as mock_svc:
            mock_svc.return_value.suggest_rename_batch.return_value = []
            result = await suggest_rename(req)
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_exception(self) -> None:
        from apps.image_rotation.api.image_rotation_api import suggest_rename

        req = MagicMock()
        req.body = json.dumps({"items": [{"filename": "x.jpg"}]}).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_rename_service") as mock_svc:
            mock_svc.return_value.suggest_rename_batch.side_effect = RuntimeError("fail")
            result = await suggest_rename(req)
            assert result["success"] is False


# ── export_pdf (JSON body) ───────────────────────────────────────


class TestExportPdf:
    def test_no_pages(self) -> None:
        from apps.image_rotation.api.image_rotation_api import export_pdf

        req = MagicMock()
        req.body = json.dumps({}).encode()
        req.content_type = "application/json"
        result = export_pdf(req)
        assert result["success"] is False

    def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import export_pdf

        req = MagicMock()
        req.body = json.dumps({"pages": [{"data": "d"}]}).encode()
        req.content_type = "application/json"
        with patch("apps.image_rotation.api.image_rotation_api._get_rotation_service") as mock_svc:
            mock_svc.return_value.export_as_pdf.return_value = {"success": True}
            result = export_pdf(req)
            assert result["success"] is True

    def test_exception(self) -> None:
        from apps.image_rotation.api.image_rotation_api import export_pdf

        req = MagicMock()
        req.body = json.dumps({"pages": [{"data": "d"}]}).encode()
        req.content_type = "application/json"
        with patch("apps.image_rotation.api.image_rotation_api._get_rotation_service") as mock_svc:
            mock_svc.return_value.export_as_pdf.side_effect = RuntimeError("err")
            result = export_pdf(req)
            assert result["success"] is False

    def test_multipart_dispatch(self) -> None:
        from apps.image_rotation.api.image_rotation_api import export_pdf

        req = MagicMock()
        req.content_type = "multipart/form-data; boundary=xxx"
        with patch("apps.image_rotation.api.image_rotation_api._handle_multipart_export_pdf") as mock_mp:
            mock_mp.return_value = {"success": True}
            result = export_pdf(req)
            assert result["success"] is True


# ── export_images (JSON body) ────────────────────────────────────


class TestExportImages:
    def test_no_images(self) -> None:
        from apps.image_rotation.api.image_rotation_api import export_images

        req = MagicMock()
        req.body = json.dumps({}).encode()
        req.content_type = "application/json"
        result = export_images(req)
        assert result["success"] is False

    def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import export_images

        req = MagicMock()
        req.body = json.dumps({"images": [{"data": "d"}]}).encode()
        req.content_type = "application/json"
        with patch("apps.image_rotation.api.image_rotation_api._get_rotation_service") as mock_svc:
            mock_svc.return_value.export_images.return_value = {"success": True}
            result = export_images(req)
            assert result["success"] is True

    def test_exception(self) -> None:
        from apps.image_rotation.api.image_rotation_api import export_images

        req = MagicMock()
        req.body = json.dumps({"images": [{"data": "d"}]}).encode()
        req.content_type = "application/json"
        with patch("apps.image_rotation.api.image_rotation_api._get_rotation_service") as mock_svc:
            mock_svc.return_value.export_images.side_effect = RuntimeError("err")
            result = export_images(req)
            assert result["success"] is False


# ── _handle_multipart_export ─────────────────────────────────────


class TestHandleMultipartExport:
    def test_no_images(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _handle_multipart_export

        req = MagicMock()
        req.POST = {"paper_size": "original"}
        req.FILES = {}
        result = _handle_multipart_export(req)
        assert result["success"] is False

    def test_with_images(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _handle_multipart_export

        file_obj = MagicMock()
        file_obj.content_type = "image/jpeg"
        file_obj.size = 1024
        file_obj.read.return_value = b"raw_data"
        file_obj.name = "scan.jpg"

        req = MagicMock()
        req.POST = {
            "paper_size": "a4",
            "filename_0": "custom.jpg",
            "rotation_0": "90",
            "format_0": "png",
        }
        req.FILES = {"image_0": file_obj}

        with patch("apps.image_rotation.api.image_rotation_api._get_rotation_service") as mock_svc:
            mock_svc.return_value.export_images.return_value = {"success": True}
            result = _handle_multipart_export(req)
            assert result["success"] is True

    def test_exception(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _handle_multipart_export

        file_obj = MagicMock()
        file_obj.content_type = "image/jpeg"
        file_obj.size = 100
        file_obj.read.return_value = b"data"
        file_obj.name = "x.jpg"

        req = MagicMock()
        req.POST = {}
        req.FILES = {"image_0": file_obj}

        with patch("apps.image_rotation.api.image_rotation_api._get_rotation_service") as mock_svc:
            mock_svc.return_value.export_images.side_effect = RuntimeError("fail")
            result = _handle_multipart_export(req)
            assert result["success"] is False


# ── _handle_multipart_export_pdf ─────────────────────────────────


class TestHandleMultipartExportPdf:
    def test_no_pages(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _handle_multipart_export_pdf

        req = MagicMock()
        req.POST = {"paper_size": "original"}
        req.FILES = {}
        result = _handle_multipart_export_pdf(req)
        assert result["success"] is False

    def test_with_pages(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _handle_multipart_export_pdf

        file_obj = MagicMock()
        file_obj.content_type = "image/jpeg"
        file_obj.size = 1024
        file_obj.read.return_value = b"raw_data"
        file_obj.name = "page.jpg"

        req = MagicMock()
        req.POST = {"paper_size": "a4", "filename_0": "custom.jpg", "rotation_0": "90"}
        req.FILES = {"page_0": file_obj}

        with patch("apps.image_rotation.api.image_rotation_api._get_rotation_service") as mock_svc:
            mock_svc.return_value.export_as_pdf.return_value = {"success": True}
            result = _handle_multipart_export_pdf(req)
            assert result["success"] is True

    def test_exception(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _handle_multipart_export_pdf

        file_obj = MagicMock()
        file_obj.content_type = "image/jpeg"
        file_obj.size = 100
        file_obj.read.return_value = b"data"
        file_obj.name = "x.jpg"

        req = MagicMock()
        req.POST = {}
        req.FILES = {"page_0": file_obj}

        with patch("apps.image_rotation.api.image_rotation_api._get_rotation_service") as mock_svc:
            mock_svc.return_value.export_as_pdf.side_effect = RuntimeError("fail")
            result = _handle_multipart_export_pdf(req)
            assert result["success"] is False


# ── _validate_image_file (missing content_type) ──────────────────


class TestValidateImageFileEdge:
    def test_none_content_type(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        from apps.core.exceptions import ValidationException

        f = MagicMock()
        f.content_type = None
        f.size = 100
        with pytest.raises(ValidationException):
            _validate_image_file(f)

    def test_empty_content_type(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        from apps.core.exceptions import ValidationException

        f = MagicMock()
        f.content_type = ""
        f.size = 100
        with pytest.raises(ValidationException):
            _validate_image_file(f)

    def test_valid_webp(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _validate_image_file

        f = MagicMock()
        f.content_type = "image/webp"
        f.size = 100
        _validate_image_file(f)  # should not raise

    def test_valid_tiff(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _validate_image_file

        f = MagicMock()
        f.content_type = "image/tiff"
        f.size = 100
        _validate_image_file(f)


# ── list_jobs ────────────────────────────────────────────────────


class TestListJobs:
    def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import list_jobs

        req = MagicMock()
        req.GET = {"page": "1", "page_size": "10"}
        job = MagicMock()
        job.id = 1
        job.name = "Test"
        job.status = "completed"
        job.total_pages = 5
        job.export_zip_url = ""
        job.export_pdf_url = ""
        job.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.list_jobs.return_value = {
                "jobs": [job],
                "total_count": 1,
                "page": 1,
                "page_size": 10,
            }
            result = list_jobs(req)
            assert result["success"] is True
            assert len(result["jobs"]) == 1

    def test_exception(self) -> None:
        from apps.image_rotation.api.image_rotation_api import list_jobs

        req = MagicMock()
        req.GET = {}
        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.list_jobs.side_effect = RuntimeError("fail")
            result = list_jobs(req)
            assert result["success"] is False


# ── get_job_detail ───────────────────────────────────────────────


class TestGetJobDetail:
    def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import get_job_detail

        req = MagicMock()
        job = MagicMock()
        job.id = 1
        job.name = "Test"
        job.status = "done"
        job.total_pages = 1
        job.export_zip_url = ""
        job.export_pdf_url = ""
        job.created_at = None

        page = MagicMock()
        page.id = 1
        page.original_filename = "a.jpg"
        page.source_image = MagicMock()
        page.source_image.url = "/media/a.jpg"
        page.page_number = 1
        page.detected_rotation = 0
        page.onnx_rotation = 0
        page.detection_confidence = 1.0
        page.ocr_text = ""
        page.suggested_filename = ""
        page.source_type = "upload"

        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.get_job_detail.return_value = (job, [page])
            result = get_job_detail(req, "1")
            assert result["success"] is True

    def test_exception(self) -> None:
        from apps.image_rotation.api.image_rotation_api import get_job_detail

        req = MagicMock()
        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.get_job_detail.side_effect = RuntimeError("fail")
            result = get_job_detail(req, "1")
            assert result["success"] is False


# ── update_job_name ──────────────────────────────────────────────


class TestUpdateJobName:
    def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import update_job_name

        req = MagicMock()
        req.body = json.dumps({"name": "New Name"}).encode()
        job = MagicMock()
        job.name = "Old"
        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.get_job.return_value = job
            result = update_job_name(req, "1")
            assert result["success"] is True
            assert result["display_name"] == "New Name"

    def test_empty_name_fallback(self) -> None:
        from apps.image_rotation.api.image_rotation_api import update_job_name

        req = MagicMock()
        req.body = json.dumps({"name": ""}).encode()
        job = MagicMock()
        job.name = ""
        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.get_job.return_value = job
            result = update_job_name(req, "1")
            assert result["display_name"] == "未命名任务"


# ── delete_job ───────────────────────────────────────────────────


class TestDeleteJob:
    def test_success(self) -> None:
        from apps.image_rotation.api.image_rotation_api import delete_job

        req = MagicMock()
        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            result = delete_job(req, "1")
            assert result["status"] == "deleted"
            mock_svc.return_value.delete_job.assert_called_once_with("1")


# ── save_export_url ──────────────────────────────────────────────


class TestSaveExportUrl:
    def test_missing_params(self) -> None:
        from apps.image_rotation.api.image_rotation_api import save_export_url

        req = MagicMock()
        req.body = json.dumps({}).encode()
        result = save_export_url(req, "1")
        assert result["success"] is False

    def test_save_zip(self) -> None:
        from apps.image_rotation.api.image_rotation_api import save_export_url

        req = MagicMock()
        req.body = json.dumps({"file_type": "zip", "media_url": "http://x.zip"}).encode()
        job = MagicMock()
        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.get_job.return_value = job
            result = save_export_url(req, "1")
            assert result["success"] is True
            assert job.export_zip_url == "http://x.zip"

    def test_save_pdf(self) -> None:
        from apps.image_rotation.api.image_rotation_api import save_export_url

        req = MagicMock()
        req.body = json.dumps({"file_type": "pdf", "media_url": "http://x.pdf"}).encode()
        job = MagicMock()
        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.get_job.return_value = job
            result = save_export_url(req, "1")
            assert result["success"] is True
            assert job.export_pdf_url == "http://x.pdf"


# ── update_job_pages ─────────────────────────────────────────────


class TestUpdateJobPages:
    def test_no_updates(self) -> None:
        from apps.image_rotation.api.image_rotation_api import update_job_pages

        req = MagicMock()
        req.body = json.dumps({}).encode()
        result = update_job_pages(req, "1")
        assert result["success"] is True

    def test_update_rotation(self) -> None:
        from apps.image_rotation.api.image_rotation_api import update_job_pages

        page = MagicMock()
        page.id = 10
        page.detected_rotation = 0
        page.suggested_filename = ""
        page.ocr_text = ""

        job = MagicMock()
        job.pages.all.return_value = [page]

        req = MagicMock()
        req.body = json.dumps({"pages": [{"page_id": "10", "detected_rotation": 90}]}).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.get_job.return_value = job
            result = update_job_pages(req, "1")
            assert result["success"] is True
            assert page.detected_rotation == 90

    def test_nonexistent_page_skipped(self) -> None:
        from apps.image_rotation.api.image_rotation_api import update_job_pages

        job = MagicMock()
        job.pages.all.return_value = []

        req = MagicMock()
        req.body = json.dumps({"pages": [{"page_id": "999", "detected_rotation": 45}]}).encode()
        with patch("apps.image_rotation.api.image_rotation_api._get_job_service") as mock_svc:
            mock_svc.return_value.get_job.return_value = job
            result = update_job_pages(req, "1")
            assert result["success"] is True
