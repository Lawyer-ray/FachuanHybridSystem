"""pdf_splitting services 补充覆盖测试 (job_service + split_service)。"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


# ── PdfSplitJobService ────────────────────────────────────────────


class TestNormalizeSplitMode:
    def test_valid_mode(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.PdfSplitMode") as mock_mode:
            mock_mode.choices = [("content_analysis", "CA"), ("page_split", "PS")]
            mock_mode.CONTENT_ANALYSIS = "content_analysis"
            assert svc._normalize_split_mode("page_split") == "page_split"

    def test_invalid_mode_falls_back(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.PdfSplitMode") as mock_mode:
            mock_mode.choices = [("content_analysis", "CA")]
            mock_mode.CONTENT_ANALYSIS = "content_analysis"
            assert svc._normalize_split_mode("invalid") == "content_analysis"

    def test_none_mode_falls_back(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.PdfSplitMode") as mock_mode:
            mock_mode.choices = [("content_analysis", "CA")]
            mock_mode.CONTENT_ANALYSIS = "content_analysis"
            assert svc._normalize_split_mode(None) == "content_analysis"


class TestNormalizeOcrProfile:
    def test_valid_profile(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.PdfSplitOcrProfile") as mock_profile:
            mock_profile.choices = [("balanced", "B"), ("fast", "F")]
            mock_profile.BALANCED = "balanced"
            assert svc._normalize_ocr_profile("fast") == "fast"

    def test_invalid_profile_falls_back(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.PdfSplitOcrProfile") as mock_profile:
            mock_profile.choices = [("balanced", "B")]
            mock_profile.BALANCED = "balanced"
            assert svc._normalize_ocr_profile("invalid") == "balanced"


class TestIsAbsolutePath:
    def test_unix_path(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        assert svc._is_absolute_path("/tmp/test.pdf") is True

    def test_relative_path(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        assert svc._is_absolute_path("tmp/test.pdf") is False

    def test_windows_path(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        assert svc._is_absolute_path("C:\\Users\\test.pdf") is True

    def test_backslash_path(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        assert svc._is_absolute_path("\\\\server\\share") is True


class TestValidateLocalPdfPath:
    def test_empty_path_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with pytest.raises(ValidationException, match="不能为空"):
            svc._validate_local_pdf_path("")

    def test_smb_path_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with pytest.raises(ValidationException, match="smb"):
            svc._validate_local_pdf_path("smb://server/share")

    def test_relative_path_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with pytest.raises(ValidationException, match="绝对路径"):
            svc._validate_local_pdf_path("relative/path.pdf")

    def test_nonexistent_path_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with pytest.raises(ValidationException, match="不存在"):
            svc._validate_local_pdf_path("/nonexistent/path/to/file.pdf")

    @patch("apps.pdf_splitting.services.job_service.os.access", return_value=False)
    def test_non_readable_path_raises(self, mock_access):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.Path") as mock_path:
            mock_resolved = MagicMock()
            mock_resolved.exists.return_value = True
            mock_resolved.is_file.return_value = True
            mock_resolved.suffix = ".pdf"
            mock_path.return_value.expanduser.return_value.resolve.return_value = mock_resolved
            with pytest.raises(ValidationException, match="不可读"):
                svc._validate_local_pdf_path("/tmp/test.pdf")


class TestSaveUploadedPdf:
    def test_non_pdf_extension_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        file = MagicMock()
        file.name = "test.docx"
        with pytest.raises(ValidationException, match="PDF"):
            svc._save_uploaded_pdf(file, Path("/tmp/test.pdf"))

    def test_empty_file_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        file = MagicMock()
        file.name = "test.pdf"
        file.size = 0
        with pytest.raises(ValidationException, match="空"):
            svc._save_uploaded_pdf(file, Path("/tmp/test.pdf"))

    def test_oversized_file_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        file = MagicMock()
        file.name = "test.pdf"
        file.size = 200 * 1024 * 1024  # 200MB
        with pytest.raises(ValidationException, match="大小"):
            svc._save_uploaded_pdf(file, Path("/tmp/test.pdf"))

    def test_successful_save(self):
        from django.conf import settings

        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        file = MagicMock()
        file.name = "test.pdf"
        file.size = 1024
        file.read.return_value = b"PDF content"

        target = Path(settings.MEDIA_ROOT) / "test_successful_save" / "test.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            mock_storage = MagicMock()
            with patch("django.core.files.storage.default_storage", mock_storage), \
                 patch("django.core.files.base.ContentFile") as mock_cf:
                mock_cf.return_value = MagicMock()
                result = svc._save_uploaded_pdf(file, target)
                assert result.endswith(".pdf")
                mock_storage.save.assert_called_once()
        finally:
            import shutil
            shutil.rmtree(target.parent, ignore_errors=True)


class TestGetJob:
    @pytest.mark.django_db
    def test_not_found_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with pytest.raises(NotFoundError):
            svc.get_job(uuid.uuid4())


class TestBuildJobPayload:
    def test_basic_payload(self):
        from apps.pdf_splitting.models import PdfSplitJobStatus
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        job = MagicMock()
        job.id = uuid.uuid4()
        job.status = PdfSplitJobStatus.REVIEW_REQUIRED
        job.split_mode = "content_analysis"
        job.ocr_profile = "balanced"
        job.progress = 100
        job.total_pages = 10
        job.processed_pages = 10
        job.current_page = 10
        job.summary_payload = {"key": "value"}
        job.error_message = ""
        job.export_zip_relpath = ""

        job.segments.order_by.return_value = []

        payload = svc.build_job_payload(job)
        assert payload["status"] == PdfSplitJobStatus.REVIEW_REQUIRED
        assert payload["total_pages"] == 10
        assert "segments" in payload

    def test_completed_with_download(self):
        from apps.pdf_splitting.models import PdfSplitJobStatus
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        job = MagicMock()
        job.id = uuid.uuid4()
        job.status = PdfSplitJobStatus.COMPLETED
        job.split_mode = "content_analysis"
        job.ocr_profile = "balanced"
        job.progress = 100
        job.total_pages = 5
        job.processed_pages = 5
        job.current_page = 5
        job.summary_payload = {}
        job.error_message = ""
        job.export_zip_relpath = "exports/test.zip"

        job.segments.order_by.return_value = []

        payload = svc.build_job_payload(job)
        assert "/download" in payload["download_url"]


class TestNormalizeConfirmedSegments:
    def test_empty_items_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with pytest.raises(ValidationException, match="至少保留"):
            svc._normalize_confirmed_segments(items=[], total_pages=10)

    def test_non_integer_page_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with pytest.raises(ValidationException, match="整数"):
            svc._normalize_confirmed_segments(
                items=[{"page_start": "abc", "page_end": 5, "segment_type": "contract"}],
                total_pages=10,
            )

    def test_page_range_invalid_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with pytest.raises(ValidationException, match="片段页码非法"):
            svc._normalize_confirmed_segments(
                items=[{"page_start": 5, "page_end": 3, "segment_type": "contract"}],
                total_pages=10,
            )

    def test_overlapping_pages_raises(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(
                items=[
                    {"page_start": 1, "page_end": 5, "segment_type": "contract"},
                    {"page_start": 3, "page_end": 8, "segment_type": "complaint"},
                ],
                total_pages=10,
            )

    def test_gap_fills_unrecognized(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.PdfSplitSegmentType") as mock_type, \
             patch("apps.pdf_splitting.services.job_service.PdfSplitReviewFlag") as mock_flag, \
             patch("apps.pdf_splitting.services.job_service.sanitize_upload_filename", side_effect=lambda x: x), \
             patch("apps.pdf_splitting.services.job_service.get_default_filename", return_value="default.pdf"):
            mock_type.choices = [("contract", "C"), ("complaint", "Co"), ("unrecognized", "U")]
            mock_type.UNRECOGNIZED = "unrecognized"
            mock_flag.NORMAL = "normal"
            mock_flag.UNRECOGNIZED = "unrecognized_flag"

            result = svc._normalize_confirmed_segments(
                items=[{"page_start": 3, "page_end": 5, "segment_type": "contract"}],
                total_pages=10,
            )
            # Should have gap fill for 1-2, actual 3-5, and gap fill for 6-10
            assert len(result) == 3
            assert result[0]["source_method"] == "gap_fill"
            assert result[2]["source_method"] == "gap_fill"

    def test_trailing_gap_fill(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.PdfSplitSegmentType") as mock_type, \
             patch("apps.pdf_splitting.services.job_service.PdfSplitReviewFlag") as mock_flag, \
             patch("apps.pdf_splitting.services.job_service.sanitize_upload_filename", side_effect=lambda x: x), \
             patch("apps.pdf_splitting.services.job_service.get_default_filename", return_value="default.pdf"):
            mock_type.choices = [("contract", "C"), ("unrecognized", "U")]
            mock_type.UNRECOGNIZED = "unrecognized"
            mock_flag.NORMAL = "normal"
            mock_flag.UNRECOGNIZED = "unrecognized_flag"

            result = svc._normalize_confirmed_segments(
                items=[{"page_start": 1, "page_end": 5, "segment_type": "contract"}],
                total_pages=10,
            )
            # Gap 6-10
            assert result[-1]["page_start"] == 6
            assert result[-1]["page_end"] == 10

    def test_invalid_segment_type_falls_back(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.PdfSplitSegmentType") as mock_type, \
             patch("apps.pdf_splitting.services.job_service.PdfSplitReviewFlag") as mock_flag, \
             patch("apps.pdf_splitting.services.job_service.sanitize_upload_filename", side_effect=lambda x: x), \
             patch("apps.pdf_splitting.services.job_service.get_default_filename", return_value="default.pdf"):
            mock_type.choices = [("contract", "C"), ("unrecognized", "U")]
            mock_type.UNRECOGNIZED = "unrecognized"
            mock_flag.NORMAL = "normal"
            mock_flag.UNRECOGNIZED = "unrecognized_flag"

            result = svc._normalize_confirmed_segments(
                items=[{"page_start": 1, "page_end": 5, "segment_type": "invalid_type"}],
                total_pages=5,
            )
            # Should fall back to unrecognized
            assert result[0]["segment_type"] == "unrecognized"

    def test_unrecognized_flag_set_for_unrecognized(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        with patch("apps.pdf_splitting.services.job_service.PdfSplitSegmentType") as mock_type, \
             patch("apps.pdf_splitting.services.job_service.PdfSplitReviewFlag") as mock_flag, \
             patch("apps.pdf_splitting.services.job_service.sanitize_upload_filename", side_effect=lambda x: x), \
             patch("apps.pdf_splitting.services.job_service.get_default_filename", return_value="default.pdf"):
            mock_type.choices = [("unrecognized", "U")]
            mock_type.UNRECOGNIZED = "unrecognized"
            mock_flag.NORMAL = "normal"
            mock_flag.UNRECOGNIZED = "unrecognized_flag"

            result = svc._normalize_confirmed_segments(
                items=[{"page_start": 1, "page_end": 5, "segment_type": "unrecognized"}],
                total_pages=5,
            )
            assert result[0]["review_flag"] == "unrecognized_flag"


class TestSerializeSegment:
    def test_basic(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        segment = MagicMock()
        segment.id = 1
        segment.order = 1
        segment.page_start = 1
        segment.page_end = 5
        segment.segment_type = "contract"
        segment.filename = "contract.pdf"
        segment.confidence = 0.95
        segment.review_flag = "normal"
        segment.get_review_flag_display.return_value = "正常"
        segment.source_method = "text"

        with patch("apps.pdf_splitting.services.job_service.get_segment_label", return_value="合同"):
            result = svc._serialize_segment(segment)
            assert result["order"] == 1
            assert result["confidence"] == 0.95


class TestMarkCompletedFailed:
    @pytest.mark.django_db
    def test_mark_completed(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        job_id = uuid.uuid4()
        svc.mark_completed(job_id=job_id, export_zip_relpath="test.zip")
        # Should not raise even if job doesn't exist (filter().update() is a no-op)

    @pytest.mark.django_db
    def test_mark_failed(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        svc = PdfSplitJobService()
        job_id = uuid.uuid4()
        svc.mark_failed(job_id=job_id, error_message="Something went wrong")
        # Should not raise even if job doesn't exist (filter().update() is a no-op)


# ── PdfSplitService internals ─────────────────────────────────────

class TestBuildPageSplitDrafts:
    def test_generates_drafts(self):
        from apps.pdf_splitting.services.split.service import PdfSplitService

        svc = PdfSplitService()
        with patch("apps.pdf_splitting.services.split.service.sanitize_upload_filename", side_effect=lambda x: x):
            drafts = svc._build_page_split_drafts(total_pages=3, source_name="test.pdf")
            assert len(drafts) == 3
            assert drafts[0].page_start == 1
            assert drafts[2].page_end == 3

    def test_default_filename(self):
        from apps.pdf_splitting.services.split.service import PdfSplitService

        svc = PdfSplitService()
        with patch("apps.pdf_splitting.services.split.service.sanitize_upload_filename", side_effect=lambda x: x):
            drafts = svc._build_page_split_drafts(total_pages=2, source_name="")
            assert "第001页" in drafts[0].filename


class TestShouldCheckCancel:
    def test_multiple_of_five(self):
        from apps.pdf_splitting.services.split.service import PdfSplitService

        svc = PdfSplitService()
        assert svc._should_check_cancel(5) is True
        assert svc._should_check_cancel(10) is True
        assert svc._should_check_cancel(3) is False

    def test_zero(self):
        from apps.pdf_splitting.services.split.service import PdfSplitService

        svc = PdfSplitService()
        assert svc._should_check_cancel(0) is True


class TestUpdateProgress:
    @pytest.mark.django_db
    def test_updates_on_every_fifth(self):
        from apps.pdf_splitting.services.split.service import PdfSplitService

        svc = PdfSplitService()
        svc._update_progress(job_id=uuid.uuid4(), resolved_pages=5, total_pages=20)
        # Should not raise

    @pytest.mark.django_db
    def test_updates_on_last_page(self):
        from apps.pdf_splitting.services.split.service import PdfSplitService

        svc = PdfSplitService()
        svc._update_progress(job_id=uuid.uuid4(), resolved_pages=20, total_pages=20)
        # Should not raise

    @pytest.mark.django_db
    def test_no_update_on_non_fifth(self):
        from apps.pdf_splitting.services.split.service import PdfSplitService

        svc = PdfSplitService()
        svc._update_progress(job_id=uuid.uuid4(), resolved_pages=3, total_pages=20)
        # Should not raise (no-op)

    @pytest.mark.django_db
    def test_zero_total_pages(self):
        from apps.pdf_splitting.services.split.service import PdfSplitService

        svc = PdfSplitService()
        svc._update_progress(job_id=uuid.uuid4(), resolved_pages=0, total_pages=0)
        # Should not raise


class TestBuildDescriptor:
    def test_basic(self):
        from apps.pdf_splitting.services.split.service import PdfSplitService

        svc = PdfSplitService()
        with patch.object(svc._segment_detector, "normalize_text", return_value="normalized"), \
             patch.object(svc._segment_detector, "score_page", return_value=[]):
            desc = svc._build_descriptor(
                page_no=1,
                text="Hello World",
                source_method="text",
                ocr_failed=False,
                template_key="civil_lawsuit",
            )
            assert desc.page_no == 1
            assert desc.source_method == "text"
            assert desc.ocr_failed is False
