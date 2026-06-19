"""Coverage tests for evidence_sorting exporter and pdf_splitting o_handler."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =========================================================================
# evidence_sorting exporter
# =========================================================================


class TestExporterServiceHelpers:
    def test_get_ext_with_dot(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        assert ExporterService._get_ext("photo.jpg") == ".jpg"
        assert ExporterService._get_ext("doc.PDF") == ".PDF"

    def test_get_ext_no_dot(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        assert ExporterService._get_ext("noext") == ".jpg"

    def test_build_filename(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        result = ExporterService._build_filename()
        assert result.startswith("evidence_sorting_")
        assert result.endswith(".zip")

    def test_ensure_output_dir_no_media_root(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        with patch("django.conf.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = None
            with pytest.raises(RuntimeError, match="MEDIA_ROOT"):
                ExporterService._ensure_output_dir()

    def test_write_image_valid_base64(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        zf_mock = MagicMock()
        img_b64 = base64.b64encode(b"fake image").decode()
        ExporterService._write_image(zf_mock, "test/file.jpg", img_b64)
        zf_mock.writestr.assert_called_once()

    def test_write_image_with_data_url_prefix(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        zf_mock = MagicMock()
        img_b64 = base64.b64encode(b"fake").decode()
        ExporterService._write_image(zf_mock, "f.jpg", f"data:image/png;base64,{img_b64}")
        zf_mock.writestr.assert_called_once()

    def test_write_image_invalid_base64(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        zf_mock = MagicMock()
        ExporterService._write_image(zf_mock, "bad.jpg", "!!!invalid!!!")
        zf_mock.writestr.assert_not_called()


class TestExporterServiceWriteCategory:
    def test_write_category(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        svc = ExporterService()
        zf_mock = MagicMock()
        img_b64 = base64.b64encode(b"data").decode()
        items = [{"filename": "a.jpg", "image_data": img_b64}]
        svc._write_category(zf_mock, "receipts", items)
        zf_mock.writestr.assert_called_once()

    def test_write_category_empty_data(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        svc = ExporterService()
        zf_mock = MagicMock()
        items = [{"filename": "a.jpg", "image_data": ""}]
        svc._write_category(zf_mock, "receipts", items)
        zf_mock.writestr.assert_not_called()


class TestExporterServiceBuildDeliveryFilename:
    def test_basic(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        from apps.evidence_sorting.services.reconciler import DeliveryNote, STATUS_MATCHED
        svc = ExporterService()
        dn = DeliveryNote(
            filename="note.jpg",
            date="20250601",
            amount="1000",
            ocr_text="出库单内容",
            image_data="",
            match_status=STATUS_MATCHED,
        )
        counter: dict[str, int] = {}
        name = svc._build_delivery_filename(dn, counter)
        assert "20250601" in name
        assert "出库单" in name
        assert "_1000" in name

    def test_unmatched_with_remark(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        from apps.evidence_sorting.services.reconciler import DeliveryNote, STATUS_UNMATCHED
        svc = ExporterService()
        dn = DeliveryNote(
            filename="note.jpg",
            date="20250601",
            amount=None,
            ocr_text="内容",
            image_data="",
            match_status=STATUS_UNMATCHED,
            remark="特殊备注",
        )
        counter: dict[str, int] = {}
        name = svc._build_delivery_filename(dn, counter)
        assert "特殊备注" in name

    def test_no_date(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        from apps.evidence_sorting.services.reconciler import DeliveryNote, STATUS_MATCHED
        svc = ExporterService()
        dn = DeliveryNote(
            filename="note.jpg",
            date=None,
            amount=None,
            ocr_text="内容",
            image_data="",
            match_status=STATUS_MATCHED,
        )
        counter: dict[str, int] = {}
        name = svc._build_delivery_filename(dn, counter)
        assert "未知日期" in name

    def test_same_date_sequence(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        from apps.evidence_sorting.services.reconciler import DeliveryNote, STATUS_MATCHED
        svc = ExporterService()
        dn = DeliveryNote(
            filename="n.jpg", date="20250601", amount=None,
            ocr_text="内容", image_data="", match_status=STATUS_MATCHED,
        )
        counter: dict[str, int] = {}
        svc._build_delivery_filename(dn, counter)
        name2 = svc._build_delivery_filename(dn, counter)
        assert "_2" in name2


class TestExporterServiceWriteUnsigned:
    def test_write_unsigned(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        from apps.evidence_sorting.services.reconciler import StatementInfo
        svc = ExporterService()
        zf_mock = MagicMock()
        img_b64 = base64.b64encode(b"data").decode()
        st = StatementInfo(
            filename="stmt.jpg", month="2025-06", signed=False,
            total_amount="5000", image_data=img_b64,
        )
        svc._write_unsigned(zf_mock, [st])
        zf_mock.writestr.assert_called_once()

    def test_write_unsigned_no_image(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        from apps.evidence_sorting.services.reconciler import StatementInfo
        svc = ExporterService()
        zf_mock = MagicMock()
        st = StatementInfo(
            filename="stmt.jpg", month=None, signed=False,
            total_amount=None, image_data="",
        )
        svc._write_unsigned(zf_mock, [st])
        zf_mock.writestr.assert_not_called()


class TestExporterServiceExportZip:
    def test_export_os_error(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        svc = ExporterService()
        mock_result = MagicMock()
        mock_result.month_groups = []
        mock_result.unsigned_statements = []
        mock_result.receipts = []
        mock_result.others = []
        mock_result.unmatched_deliveries = []
        with patch.object(svc, "_ensure_output_dir", side_effect=OSError("disk full")):
            result = svc.export_zip(mock_result)
            assert result["success"] is False


# =========================================================================
# pdf_splitting ocr_handler
# =========================================================================


class TestOCRHandlerResolveProfile:
    def test_fast(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        from apps.pdf_splitting.models import PdfSplitOcrProfile
        handler = OCRHandler()
        profile = handler.resolve_runtime_profile(PdfSplitOcrProfile.FAST)
        assert profile.use_v5 is False
        assert profile.dpi == 140

    def test_balanced(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        from apps.pdf_splitting.models import PdfSplitOcrProfile
        handler = OCRHandler()
        profile = handler.resolve_runtime_profile(PdfSplitOcrProfile.BALANCED)
        assert profile.use_v5 is True
        assert profile.dpi == 200

    def test_accurate(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        from apps.pdf_splitting.models import PdfSplitOcrProfile
        handler = OCRHandler()
        profile = handler.resolve_runtime_profile(PdfSplitOcrProfile.ACCURATE)
        assert profile.use_v5 is True
        assert profile.dpi == 220

    def test_unknown_defaults_to_balanced(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        profile = handler.resolve_runtime_profile("unknown_key")
        assert profile.use_v5 is True
        assert profile.dpi == 200

    def test_empty_string(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        profile = handler.resolve_runtime_profile("")
        assert profile.use_v5 is True

    def test_none_input(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        profile = handler.resolve_runtime_profile(None)
        assert profile.use_v5 is True


class TestOCRHandlerChunkPages:
    def test_empty(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        result = handler._chunk_pages(page_numbers=[], chunk_count=3)
        assert result == []

    def test_single_chunk(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        result = handler._chunk_pages(page_numbers=[1, 2, 3], chunk_count=1)
        assert len(result) == 1
        assert result[0] == [1, 2, 3]

    def test_multiple_chunks(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        result = handler._chunk_pages(page_numbers=[1, 2, 3, 4, 5], chunk_count=2)
        assert len(result) == 2
        total = sum(len(c) for c in result)
        assert total == 5

    def test_more_chunks_than_pages(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        result = handler._chunk_pages(page_numbers=[1, 2], chunk_count=10)
        assert len(result) == 2


class TestOCRHandlerReadCache:
    def test_cache_miss(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        with patch("apps.pdf_splitting.services.split.ocr_handler.default_storage") as mock_storage:
            mock_storage.exists.return_value = False
            result = handler.read_ocr_cache(pdf_hash="abc", profile_key="fast", page_no=1)
            assert result is None

    def test_cache_hit(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        payload = {"text": "hello", "ocr_failed": False, "source_method": "ocr"}
        mock_file = MagicMock()
        mock_file.read.return_value = json.dumps(payload).encode("utf-8")
        with patch("apps.pdf_splitting.services.split.ocr_handler.default_storage") as mock_storage:
            mock_storage.exists.return_value = True
            mock_storage.open.return_value.__enter__ = MagicMock(return_value=mock_file)
            mock_storage.open.return_value.__exit__ = MagicMock(return_value=False)
            result = handler.read_ocr_cache(pdf_hash="abc", profile_key="fast", page_no=1)
            assert result is not None
            assert result.text == "hello"
            assert result.source_method == "ocr_cache"

    def test_cache_hit_empty_text(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        payload = {"text": "", "ocr_failed": True, "source_method": "ocr_failed"}
        mock_file = MagicMock()
        mock_file.read.return_value = json.dumps(payload).encode("utf-8")
        with patch("apps.pdf_splitting.services.split.ocr_handler.default_storage") as mock_storage:
            mock_storage.exists.return_value = True
            mock_storage.open.return_value.__enter__ = MagicMock(return_value=mock_file)
            mock_storage.open.return_value.__exit__ = MagicMock(return_value=False)
            result = handler.read_ocr_cache(pdf_hash="abc", profile_key="fast", page_no=1)
            assert result is not None
            assert result.source_method == "ocr_failed_cache"

    def test_cache_corrupt_json(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        handler = OCRHandler()
        mock_file = MagicMock()
        mock_file.read.return_value = b"not valid json!!!"
        with patch("apps.pdf_splitting.services.split.ocr_handler.default_storage") as mock_storage:
            mock_storage.exists.return_value = True
            mock_storage.open.return_value.__enter__ = MagicMock(return_value=mock_file)
            mock_storage.open.return_value.__exit__ = MagicMock(return_value=False)
            result = handler.read_ocr_cache(pdf_hash="abc", profile_key="fast", page_no=1)
            assert result is None


class TestOCRHandlerSha256:
    def test_sha256(self):
        from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
        import tempfile
        handler = OCRHandler()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"hello world")
            f.flush()
            result = handler.sha256_file(Path(f.name))
            assert len(result) == 64  # SHA256 hex digest
        import os
        os.unlink(f.name)
