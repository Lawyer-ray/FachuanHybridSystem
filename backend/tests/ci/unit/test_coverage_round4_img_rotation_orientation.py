"""Coverage round 4: image_rotation orientation/service.py + facade.py uncovered branches."""
from __future__ import annotations

import base64
import io
import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException


# ============================================================
# orientation/service.py
# ============================================================

class TestOrientationDetectionService:
    def _make_service(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService.__new__(OrientationDetectionService)
        svc._ocr_service = None
        return svc

    def test_detect_orientation_no_ocr(self):
        svc = self._make_service()
        svc._ocr_service = None
        with patch.object(type(svc), 'ocr_service', new_callable=lambda: property(lambda self: None)):
            result = svc.detect_orientation(b"fake_image")
        assert result["rotation"] == 0
        assert result["method"] == "none"

    def test_detect_orientation_with_text_no_ocr(self):
        svc = self._make_service()
        with patch.object(type(svc), 'ocr_service', new_callable=lambda: property(lambda self: None)):
            result = svc.detect_orientation_with_text(b"fake_image")
        assert result["rotation"] == 0
        assert result["ocr_text"] == ""

    def test_detect_orientation_success(self):
        svc = self._make_service()
        mock_ocr = MagicMock()
        ocr_result = MagicMock()
        # Need score > 10.0: text_count * avg_confidence
        # 12 texts * 0.9 avg = 10.8 > 10.0
        ocr_result.txts = [f"text{i}" for i in range(12)]
        ocr_result.scores = [0.9] * 12
        mock_ocr.ocr.return_value = ocr_result
        svc._ocr_service = mock_ocr

        # Create a small valid image
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        result = svc.detect_orientation(image_bytes)
        assert "rotation" in result
        assert "confidence" in result
        assert result["method"] == "ocr_voting"

    def test_detect_orientation_low_score(self):
        svc = self._make_service()
        mock_ocr = MagicMock()
        ocr_result = MagicMock()
        ocr_result.txts = ["x"]
        ocr_result.scores = [0.01]
        mock_ocr.ocr.return_value = ocr_result
        svc._ocr_service = mock_ocr

        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        result = svc.detect_orientation(image_bytes)
        assert result["method"] == "ocr_voting_low_score"
        assert result["rotation"] == 0

    def test_detect_orientation_with_text_success(self):
        svc = self._make_service()
        mock_ocr = MagicMock()
        ocr_result = MagicMock()
        ocr_result.txts = [f"text{i}" for i in range(12)]
        ocr_result.scores = [0.9] * 12
        mock_ocr.ocr.return_value = ocr_result
        svc._ocr_service = mock_ocr

        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        result = svc.detect_orientation_with_text(image_bytes)
        assert "ocr_text" in result
        assert result["method"] == "ocr_voting"

    def test_detect_orientation_with_text_low_score(self):
        svc = self._make_service()
        mock_ocr = MagicMock()
        ocr_result = MagicMock()
        ocr_result.txts = ["x"]
        ocr_result.scores = [0.01]
        mock_ocr.ocr.return_value = ocr_result
        svc._ocr_service = mock_ocr

        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        result = svc.detect_orientation_with_text(image_bytes)
        assert result["method"] == "ocr_voting_low_score"
        assert result["rotation"] == 0

    def test_detect_orientation_exception(self):
        svc = self._make_service()
        mock_ocr = MagicMock()
        mock_ocr.ocr.side_effect = RuntimeError("ocr fail")
        svc._ocr_service = mock_ocr

        # Need a valid image so PIL opens it, then OCR fails
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        result = svc.detect_orientation(image_bytes)
        assert result["rotation"] == 0
        assert result["method"] == "none"
        assert "ocr fail" in result["error"]

    def test_detect_orientation_with_text_exception(self):
        svc = self._make_service()
        mock_ocr = MagicMock()
        mock_ocr.ocr.side_effect = RuntimeError("ocr fail")
        svc._ocr_service = mock_ocr

        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        result = svc.detect_orientation_with_text(image_bytes)
        assert result["rotation"] == 0
        assert result["ocr_text"] == ""

    def test_detect_orientation_no_results(self):
        svc = self._make_service()
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = None
        svc._ocr_service = mock_ocr

        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        # With no results, all scores are 0, so method will be ocr_voting_low_score
        result = svc.detect_orientation(image_bytes)
        assert result["rotation"] == 0

    def test_detect_batch_success(self):
        svc = self._make_service()
        svc._ocr_service = MagicMock()
        with patch.object(svc, 'detect_orientation_with_text', return_value={"rotation": 0, "confidence": 0.5, "method": "ocr_voting", "ocr_text": "text"}):
            img_data = base64.b64encode(b"fake").decode()
            result = svc.detect_batch([{"data": img_data, "filename": "test.jpg"}])
        assert len(result) == 1
        assert result[0]["filename"] == "test.jpg"

    def test_detect_batch_with_data_prefix(self):
        svc = self._make_service()
        svc._ocr_service = MagicMock()
        with patch.object(svc, 'detect_orientation_with_text', return_value={"rotation": 0, "confidence": 0.5, "method": "ocr_voting", "ocr_text": "text"}):
            img_data = "data:image/jpeg;base64," + base64.b64encode(b"fake").decode()
            result = svc.detect_batch([{"data": img_data, "filename": "test.jpg"}])
        assert len(result) == 1

    def test_detect_batch_exception(self):
        svc = self._make_service()
        svc._ocr_service = MagicMock()
        with patch.object(svc, 'detect_orientation_with_text', side_effect=RuntimeError("fail")):
            img_data = base64.b64encode(b"fake").decode()
            result = svc.detect_batch([{"data": img_data, "filename": "bad.jpg"}])
        assert len(result) == 1
        assert "fail" in result[0]["error"]


# ============================================================
# facade.py – export_images / export_as_pdf
# ============================================================

class TestImageRotationServiceExport:
    def _make_service(self):
        from apps.image_rotation.services.facade import ImageRotationService
        return ImageRotationService()

    def test_export_images_empty(self):
        svc = self._make_service()
        result = svc.export_images([])
        assert result["success"] is False
        assert "没有图片" in result["message"]

    def test_export_as_pdf_empty(self):
        svc = self._make_service()
        result = svc.export_as_pdf([])
        assert result["success"] is False
        assert "没有页面" in result["message"]

    def test_export_images_all_fail(self):
        svc = self._make_service()
        with patch.object(svc, '_process_all_images', return_value=([], ["error1"])):
            result = svc.export_images([{"data": "fake"}])
        assert result["success"] is False
        assert "所有图片" in result["message"]

    def test_export_as_pdf_all_fail(self):
        svc = self._make_service()
        with patch.object(svc, '_process_page_for_pdf', side_effect=RuntimeError("fail")):
            result = svc.export_as_pdf([{"data": base64.b64encode(b"x").decode()}])
        assert result["success"] is False

    def test_export_images_success(self):
        svc = self._make_service()
        processed = [("img.jpg", b"fake_bytes", "jpeg")]
        with patch.object(svc, '_process_all_images', return_value=(processed, [])):
            with patch("apps.image_rotation.services.facade.generate_zip", return_value="/zip/url"):
                with patch.object(svc, '_get_output_dir', return_value="/tmp"):
                    result = svc.export_images([{"data": "x"}])
        assert result["success"] is True
        assert result["zip_url"] == "/zip/url"

    def test_export_images_with_warnings(self):
        svc = self._make_service()
        processed = [("img.jpg", b"fake_bytes", "jpeg")]
        with patch.object(svc, '_process_all_images', return_value=(processed, ["warn1"])):
            with patch("apps.image_rotation.services.facade.generate_zip", return_value="/zip/url"):
                with patch.object(svc, '_get_output_dir', return_value="/tmp"):
                    result = svc.export_images([{"data": "x"}])
        assert result["success"] is True
        assert "warnings" in result

    def test_export_images_zip_fail(self):
        svc = self._make_service()
        processed = [("img.jpg", b"fake_bytes", "jpeg")]
        with patch.object(svc, '_process_all_images', return_value=(processed, [])):
            with patch("apps.image_rotation.services.facade.generate_zip", side_effect=RuntimeError("zip err")):
                with patch.object(svc, '_get_output_dir', return_value="/tmp"):
                    result = svc.export_images([{"data": "x"}])
        assert result["success"] is False

    def test_export_as_pdf_success(self):
        svc = self._make_service()
        with patch.object(svc, '_process_page_for_pdf', return_value=(b"pdf_data", 0)):
            with patch("apps.image_rotation.services.facade.generate_pdf", return_value="/pdf/url"):
                with patch.object(svc, '_get_output_dir', return_value="/tmp"):
                    result = svc.export_as_pdf([{"data": base64.b64encode(b"x").decode()}])
        assert result["success"] is True
        assert result["pdf_url"] == "/pdf/url"

    def test_export_as_pdf_with_warnings(self):
        svc = self._make_service()
        call_count = [0]
        def side_effect(page_item, paper_size):
            call_count[0] += 1
            if call_count[0] == 1:
                return (b"data", 0)
            raise ValidationException("bad page")
        with patch.object(svc, '_process_page_for_pdf', side_effect=side_effect):
            with patch("apps.image_rotation.services.facade.generate_pdf", return_value="/pdf/url"):
                with patch.object(svc, '_get_output_dir', return_value="/tmp"):
                    result = svc.export_as_pdf([{"data": "d"}, {"data": "d"}])
        assert result["success"] is True
        assert "warnings" in result

    def test_export_as_pdf_generate_fail(self):
        svc = self._make_service()
        with patch.object(svc, '_process_page_for_pdf', return_value=(b"data", 0)):
            with patch("apps.image_rotation.services.facade.generate_pdf", side_effect=RuntimeError("gen fail")):
                with patch.object(svc, '_get_output_dir', return_value="/tmp"):
                    result = svc.export_as_pdf([{"data": base64.b64encode(b"x").decode()}])
        assert result["success"] is False


class TestProcessAllImages:
    def _make_service(self):
        from apps.image_rotation.services.facade import ImageRotationService
        return ImageRotationService()

    def test_rename_map_applied(self):
        svc = self._make_service()
        with patch.object(svc, '_process_single_image', return_value=("old.jpg", b"data", "jpeg")):
            processed, errors = svc._process_all_images(
                [{"data": "x"}], "original", {"old.jpg": "new.jpg"}
            )
        assert processed[0][0] == "new.jpg"

    def test_validation_error_captured(self):
        svc = self._make_service()
        with patch.object(svc, '_process_single_image', side_effect=ValidationException("bad format")):
            with patch("apps.image_rotation.services.facade.logger"):
                processed, errors = svc._process_all_images(
                    [{"data": "x", "filename": "bad.jpg"}], "original", None
                )
        assert len(processed) == 0
        assert len(errors) == 1

    def test_generic_error_captured(self):
        svc = self._make_service()
        with patch.object(svc, '_process_single_image', side_effect=RuntimeError("unexpected")):
            with patch("apps.image_rotation.services.facade.logger") as mock_logger:
                processed, errors = svc._process_all_images(
                    [{"data": "x", "filename": "bad.jpg"}], "original", None
                )
        assert len(processed) == 0
        assert len(errors) == 1

    def test_process_returns_none(self):
        svc = self._make_service()
        with patch.object(svc, '_process_single_image', return_value=None):
            processed, errors = svc._process_all_images(
                [{"data": "x"}], "original", None
            )
        assert len(processed) == 0


class TestProcessPageForPdf:
    def _make_service(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService.__new__(ImageRotationService)
        svc.SUPPORTED_FORMATS = {"jpeg", "jpg", "png"}
        svc.MAX_FILE_SIZE = 20 * 1024 * 1024
        svc.PAPER_SIZES = {"original": None, "a4": (210, 297)}
        svc.DEFAULT_DPI = 150
        return svc

    def test_invalid_rotation_zero(self):
        svc = self._make_service()
        with patch("apps.image_rotation.services.facade.validation") as mock_val:
            mock_val.decode_base64_payload.return_value = b"fake"
            result = svc._process_page_for_pdf({"data": base64.b64encode(b"x").decode(), "rotation": 45})
        assert result[1] == 0

    def test_valid_rotation_90(self):
        svc = self._make_service()
        with patch("apps.image_rotation.services.facade.validation") as mock_val:
            mock_val.decode_base64_payload.return_value = b"fake"
            result = svc._process_page_for_pdf({"data": base64.b64encode(b"x").decode(), "rotation": 90})
        assert result[1] == 90

    def test_with_paper_size(self):
        svc = self._make_service()
        with patch("apps.image_rotation.services.facade.validation") as mock_val:
            with patch("apps.image_rotation.services.facade.resize_to_paper_size", return_value=b"resized"):
                mock_val.decode_base64_payload.return_value = b"fake"
                result = svc._process_page_for_pdf({"data": base64.b64encode(b"x").decode(), "rotation": 0}, paper_size="a4")
        assert result[0] == b"resized"
