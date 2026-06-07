"""image_rotation 模块单元测试（orientation, transform, preprocessor, facade, channel, pdf_extraction）。"""

from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


def _make_test_image(width: int = 100, height: int = 100, color: str = "white") -> bytes:
    """Create a simple test PNG image."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_test_jpeg() -> bytes:
    img = Image.new("RGB", (100, 100), "red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ── transform tests ─────────────────────────────────────────────


class TestRemoveExifOrientation:
    def test_no_exif(self) -> None:
        from apps.image_rotation.services.transform.image_transform import remove_exif_orientation

        img = Image.new("RGB", (100, 100))
        result = remove_exif_orientation(img, exif_orientation_tag=0x0112)
        assert result is not None

    def test_orientation_1(self) -> None:
        from apps.image_rotation.services.transform.image_transform import remove_exif_orientation

        img = Image.new("RGB", (100, 100))
        exif = img.getexif()
        exif[0x0112] = 1
        img.info["exif"] = exif.tobytes()
        result = remove_exif_orientation(img, exif_orientation_tag=0x0112)
        assert result is not None


class TestCleanImage:
    def test_jpeg_passthrough(self) -> None:
        from apps.image_rotation.services.transform.image_transform import clean_image

        jpeg_data = _make_test_jpeg()
        result = clean_image(jpeg_data, img_format="jpeg", exif_orientation_tag=0x0112)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_png_format(self) -> None:
        from apps.image_rotation.services.transform.image_transform import clean_image

        png_data = _make_test_image()
        result = clean_image(png_data, img_format="png", exif_orientation_tag=0x0112)
        assert isinstance(result, bytes)

    def test_rgba_to_jpeg(self) -> None:
        from apps.image_rotation.services.transform.image_transform import clean_image

        img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = clean_image(buf.getvalue(), img_format="jpeg", exif_orientation_tag=0x0112)
        assert isinstance(result, bytes)


class TestResizeToPaperSize:
    def test_resize_a4(self) -> None:
        from apps.image_rotation.services.transform.image_transform import resize_to_paper_size

        img_data = _make_test_image(500, 500)
        sizes = {"a4": (210, 297)}
        result = resize_to_paper_size(img_data, paper_size="a4", paper_sizes=sizes, dpi=150)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_resize_landscape(self) -> None:
        from apps.image_rotation.services.transform.image_transform import resize_to_paper_size

        img_data = _make_test_image(800, 400)
        sizes = {"a4": (210, 297)}
        result = resize_to_paper_size(img_data, paper_size="a4", paper_sizes=sizes, dpi=150)
        assert isinstance(result, bytes)


class TestRotateImageForOutput:
    def test_rotate_0(self) -> None:
        from apps.image_rotation.services.transform.image_transform import rotate_image_for_output

        result = rotate_image_for_output(_make_test_image(), rotation=0, img_format="png")
        assert isinstance(result, bytes)

    def test_rotate_90(self) -> None:
        from apps.image_rotation.services.transform.image_transform import rotate_image_for_output

        result = rotate_image_for_output(_make_test_image(), rotation=90, img_format="jpeg")
        assert isinstance(result, bytes)

    def test_rotate_180(self) -> None:
        from apps.image_rotation.services.transform.image_transform import rotate_image_for_output

        result = rotate_image_for_output(_make_test_image(), rotation=180, img_format="png")
        assert isinstance(result, bytes)

    def test_rotate_270(self) -> None:
        from apps.image_rotation.services.transform.image_transform import rotate_image_for_output

        result = rotate_image_for_output(_make_test_image(), rotation=270, img_format="jpeg")
        assert isinstance(result, bytes)

    def test_invalid_rotation(self) -> None:
        from apps.image_rotation.services.transform.image_transform import rotate_image_for_output

        result = rotate_image_for_output(_make_test_image(), rotation=45, img_format="png")
        assert isinstance(result, bytes)


# ── preprocessor tests ──────────────────────────────────────────


class TestPreprocessConfig:
    def test_defaults(self) -> None:
        from apps.image_rotation.services.rename_ocr.preprocessor import PreprocessConfig

        cfg = PreprocessConfig()
        assert cfg.sharpen_radius == 2.0
        assert cfg.contrast_factor == 1.5
        assert cfg.enable_binarize is False

    def test_enhanced_config(self) -> None:
        from apps.image_rotation.services.rename_ocr.preprocessor import ENHANCED_CONFIG

        assert ENHANCED_CONFIG.contrast_factor == 2.0
        assert ENHANCED_CONFIG.enable_binarize is True


class TestImagePreprocessor:
    def test_preprocess_basic(self) -> None:
        from apps.image_rotation.services.rename_ocr.preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.preprocess(_make_test_image())
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_preprocess_with_config(self) -> None:
        from apps.image_rotation.services.rename_ocr.preprocessor import ImagePreprocessor, PreprocessConfig

        proc = ImagePreprocessor()
        cfg = PreprocessConfig(enable_binarize=True)
        result = proc.preprocess(_make_test_image(), cfg)
        assert isinstance(result, bytes)

    def test_preprocess_small_image_upscale(self) -> None:
        from apps.image_rotation.services.rename_ocr.preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        small_img = _make_test_image(50, 50)
        result = proc.preprocess(small_img)
        assert isinstance(result, bytes)

    def test_preprocess_exception_returns_original(self) -> None:
        from apps.image_rotation.services.rename_ocr.preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.preprocess(b"not an image")
        assert result == b"not an image"


# ── orientation detection tests ─────────────────────────────────


class TestOrientationDetectionService:
    def test_no_ocr_service(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.object(type(svc), "ocr_service", new_callable=lambda: property(lambda self: None)):
            result = svc.detect_orientation(_make_test_image())
            assert result["rotation"] == 0

    def test_detect_orientation_with_text_no_ocr(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.object(type(svc), "ocr_service", new_callable=lambda: property(lambda self: None)):
            result = svc.detect_orientation_with_text(_make_test_image())
            assert result["rotation"] == 0
            assert result["ocr_text"] == ""

    def test_detect_batch(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.object(type(svc), "ocr_service", new_callable=lambda: property(lambda self: None)):
            img_b64 = base64.b64encode(_make_test_image()).decode()
            results = svc.detect_batch([{"filename": "test.png", "data": img_b64}])
            assert len(results) == 1
            assert results[0]["filename"] == "test.png"

    def test_detect_batch_with_data_url_prefix(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.object(type(svc), "ocr_service", new_callable=lambda: property(lambda self: None)):
            img_b64 = "data:image/png;base64," + base64.b64encode(_make_test_image()).decode()
            results = svc.detect_batch([{"filename": "test.png", "data": img_b64}])
            assert len(results) == 1


# ── channel tests ───────────────────────────────────────────────


class TestOCRResult:
    def test_creation(self) -> None:
        from apps.image_rotation.services.rename_ocr.channel import OCRResult

        r = OCRResult(text="hello", text_blocks=["hello"], scores=[0.9], overall_confidence=0.9)
        assert r.text == "hello"


class TestRenameOCRChannel:
    def test_init(self) -> None:
        from apps.image_rotation.services.rename_ocr.channel import RenameOCRChannel

        ch = RenameOCRChannel()
        assert ch._ocr is None
        assert ch._init_failed is False

    def test_rotate_image_0(self) -> None:
        from apps.image_rotation.services.rename_ocr.channel import RenameOCRChannel

        ch = RenameOCRChannel()
        result = ch._rotate_image(_make_test_image(), 0)
        assert result == _make_test_image()

    def test_rotate_image_90(self) -> None:
        from apps.image_rotation.services.rename_ocr.channel import RenameOCRChannel

        ch = RenameOCRChannel()
        result = ch._rotate_image(_make_test_image(), 90)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_recognize_init_failed(self) -> None:
        from apps.image_rotation.services.rename_ocr.channel import RenameOCRChannel

        ch = RenameOCRChannel()
        ch._init_failed = True
        assert ch.recognize(_make_test_image()) is None


# ── facade tests ────────────────────────────────────────────────


class TestImageRotationService:
    def test_export_images_empty(self) -> None:
        from apps.image_rotation.services.facade import ImageRotationService

        svc = ImageRotationService()
        result = svc.export_images([])
        assert result["success"] is False

    def test_export_as_pdf_empty(self) -> None:
        from apps.image_rotation.services.facade import ImageRotationService

        svc = ImageRotationService()
        result = svc.export_as_pdf([])
        assert result["success"] is False

    def test_get_unique_filename_new(self) -> None:
        from apps.image_rotation.services.facade import ImageRotationService

        svc = ImageRotationService()
        used: dict[str, int] = {}
        result = svc._get_unique_filename("test.jpg", used)
        assert result == "test.jpg"
        assert used["test.jpg"] == 1

    def test_get_unique_filename_duplicate(self) -> None:
        from apps.image_rotation.services.facade import ImageRotationService

        svc = ImageRotationService()
        used: dict[str, int] = {"test.jpg": 1}
        result = svc._get_unique_filename("test.jpg", used)
        assert result == "test_1.jpg"

    def test_get_unique_filename_empty(self) -> None:
        from apps.image_rotation.services.facade import ImageRotationService

        svc = ImageRotationService()
        used: dict[str, int] = {}
        result = svc._get_unique_filename("", used)
        assert result.endswith(".jpg")

    def test_process_page_for_pdf_rotation_normalize(self) -> None:
        from apps.image_rotation.services.facade import ImageRotationService

        svc = ImageRotationService()
        img_b64 = base64.b64encode(_make_test_image()).decode()
        result = svc._process_page_for_pdf({"data": img_b64, "rotation": 45})
        assert result is not None
        _, rotation = result
        assert rotation == 0  # invalid rotation normalized to 0


# ── pdf_extraction tests ────────────────────────────────────────


class TestPDFExtractionService:
    def test_init(self) -> None:
        from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService

        svc = PDFExtractionService()
        assert svc.MAX_PDF_SIZE == 50 * 1024 * 1024

    def test_validate_page_count_too_many(self) -> None:
        from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService

        svc = PDFExtractionService()
        result = svc._validate_page_count(200, "test.pdf")
        assert result is not None
        assert "超过" in result["message"]

    def test_validate_page_count_zero(self) -> None:
        from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService

        svc = PDFExtractionService()
        result = svc._validate_page_count(0, "test.pdf")
        assert result is not None
        assert "没有页面" in result["message"]

    def test_validate_page_count_ok(self) -> None:
        from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService

        svc = PDFExtractionService()
        result = svc._validate_page_count(5, "test.pdf")
        assert result is None

    def test_detect_single_page_orientation_error(self) -> None:
        from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService

        svc = PDFExtractionService()
        result = svc.detect_single_page_orientation("not_valid_base64!!!")
        assert result["rotation"] == 0
        assert result["method"] == "error"
