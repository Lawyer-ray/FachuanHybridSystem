from __future__ import annotations

import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.client.services.id_card_merge.facade import IdCardMergeService
from apps.core.exceptions import ValidationException


def _make_service():
    return IdCardMergeService()


def _mock_uploaded_file(name="test.jpg", content_type="image/jpeg"):
    f = MagicMock()
    f.name = name
    f.content_type = content_type
    return f


class TestConstants:

    def test_aspect_ratio(self):
        svc = _make_service()
        assert abs(svc.ID_CARD_ASPECT_RATIO - 85.6 / 54.0) < 0.001

    def test_supported_formats(self):
        svc = _make_service()
        assert "image/jpeg" in svc.SUPPORTED_FORMATS
        assert "image/png" in svc.SUPPORTED_FORMATS

    def test_supported_extensions(self):
        svc = _make_service()
        assert ".jpg" in svc.SUPPORTED_EXTENSIONS
        assert ".png" in svc.SUPPORTED_EXTENSIONS

    def test_min_image_size(self):
        svc = _make_service()
        assert svc.MIN_IMAGE_SIZE == 200


class TestLoadAndValidateImages:

    def test_format_error_returns_dict(self):
        svc = _make_service()
        front = _mock_uploaded_file(name="test.bmp", content_type="image/bmp")
        back = _mock_uploaded_file()
        with patch.object(svc, "_validate_image_format", return_value={"error": "INVALID_IMAGE_FORMAT"}):
            result = svc._load_and_validate_images(front, back)
            assert isinstance(result, dict)
            assert result.get("error") == "INVALID_IMAGE_FORMAT"

    def test_front_read_failure(self):
        svc = _make_service()
        front = _mock_uploaded_file()
        back = _mock_uploaded_file()
        with patch.object(svc, "_validate_image_format", return_value=None):
            with patch.object(svc, "_read_uploaded_image", side_effect=[None, np.zeros((300, 300, 3), dtype=np.uint8)]):
                result = svc._load_and_validate_images(front, back)
                assert isinstance(result, dict)
                assert "正面" in result["message"]

    def test_back_read_failure(self):
        svc = _make_service()
        front = _mock_uploaded_file()
        back = _mock_uploaded_file()
        with patch.object(svc, "_validate_image_format", return_value=None):
            with patch.object(svc, "_read_uploaded_image", side_effect=[np.zeros((300, 300, 3), dtype=np.uint8), None]):
                result = svc._load_and_validate_images(front, back)
                assert isinstance(result, dict)
                assert "反面" in result["message"]

    def test_size_error(self):
        svc = _make_service()
        front = _mock_uploaded_file()
        back = _mock_uploaded_file()
        small_img = np.zeros((50, 50, 3), dtype=np.uint8)
        with patch.object(svc, "_validate_image_format", return_value=None):
            with patch.object(svc, "_read_uploaded_image", return_value=small_img):
                with patch.object(svc, "_validate_image_size", return_value={"error": "IMAGE_TOO_SMALL"}):
                    result = svc._load_and_validate_images(front, back)
                    assert isinstance(result, dict)

    def test_success_returns_tuple(self):
        svc = _make_service()
        front = _mock_uploaded_file()
        back = _mock_uploaded_file()
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        with patch.object(svc, "_validate_image_format", return_value=None):
            with patch.object(svc, "_read_uploaded_image", return_value=img):
                with patch.object(svc, "_validate_image_size", return_value=None):
                    result = svc._load_and_validate_images(front, back)
                    assert isinstance(result, tuple)
                    assert len(result) == 2


class TestMergeIdCard:

    def test_validation_error_propagates(self):
        svc = _make_service()
        error = {"success": False, "error": "INVALID_IMAGE_FORMAT"}
        with patch.object(svc, "_load_and_validate_images", return_value=error):
            result = svc.merge_id_card(_mock_uploaded_file(), _mock_uploaded_file())
            assert result == error

    def test_success(self):
        svc = _make_service()
        front = np.zeros((300, 300, 3), dtype=np.uint8)
        back = np.zeros((300, 300, 3), dtype=np.uint8)
        with patch.object(svc, "_load_and_validate_images", return_value=(front, back)):
            with patch.object(svc, "_generate_pdf", return_value="id_card_merged/test.pdf"):
                result = svc.merge_id_card(_mock_uploaded_file(), _mock_uploaded_file())
                assert result["success"] is True
                assert result["pdf_path"] == "id_card_merged/test.pdf"


class TestMergeIdCardWithDetection:

    def test_validation_error(self):
        svc = _make_service()
        error = {"success": False, "error": "FORMAT"}
        with patch.object(svc, "_load_and_validate_images", return_value=error):
            result = svc.merge_id_card_with_detection(_mock_uploaded_file(), _mock_uploaded_file())
            assert result == error

    def test_auto_detect_failed(self):
        svc = _make_service()
        front = np.zeros((300, 300, 3), dtype=np.uint8)
        back = np.zeros((300, 300, 3), dtype=np.uint8)
        with patch.object(svc, "_load_and_validate_images", return_value=(front, back)):
            with patch.object(svc, "_detect_id_card", return_value=None):
                with patch.object(svc, "_save_temp_image", return_value="temp/front.jpg"):
                    result = svc.merge_id_card_with_detection(_mock_uploaded_file(), _mock_uploaded_file())
                    assert result["success"] is False
                    assert result["error"] == "AUTO_DETECT_FAILED"

    def test_success(self):
        svc = _make_service()
        front = np.zeros((300, 300, 3), dtype=np.uint8)
        back = np.zeros((300, 300, 3), dtype=np.uint8)
        corners = np.array([[0, 0], [100, 0], [100, 63], [0, 63]], dtype=np.float32)
        with patch.object(svc, "_load_and_validate_images", return_value=(front, back)):
            with patch.object(svc, "_detect_id_card", return_value=corners):
                with patch.object(svc, "_perspective_transform", return_value=front):
                    with patch.object(svc, "_generate_pdf", return_value="merged/test.pdf"):
                        result = svc.merge_id_card_with_detection(
                            _mock_uploaded_file(), _mock_uploaded_file()
                        )
                        assert result["success"] is True


class TestMergeIdCardManual:

    def test_invalid_corners(self):
        svc = _make_service()
        with patch.object(svc, "_validate_corners", return_value="角点无效"):
            result = svc.merge_id_card_manual(
                "/media/test.jpg", "/media/test.jpg", [[0, 0]], [[0, 0]]
            )
            assert result["success"] is False
            assert "INVALID_CORNERS" in result["error"]

    def test_image_not_found(self):
        svc = _make_service()
        with patch.object(svc, "_validate_corners", return_value=None):
            with patch.object(svc, "_resolve_image_path", return_value=(Path("/nonexistent"), "nonexistent")):
                with patch.object(type(Path("/nonexistent")), "exists", return_value=False):
                    result = svc.merge_id_card_manual(
                        "/media/test.jpg", "/media/test.jpg",
                        [[0, 0], [100, 0], [100, 63], [0, 63]],
                        [[0, 0], [100, 0], [100, 63], [0, 63]],
                    )
                    assert result["success"] is False


class TestResolveImagePath:

    def test_strips_leading_slash(self):
        svc = _make_service()
        media_root = Path("/media")
        with patch("apps.client.services.id_card_merge.facade.get_media_root", return_value=media_root):
            full, rel = svc._resolve_image_path("/uploads/test.jpg", media_root)
            assert rel == "uploads/test.jpg"

    def test_strips_media_prefix(self):
        svc = _make_service()
        media_root = Path("/media")
        full, rel = svc._resolve_image_path("media/uploads/test.jpg", media_root)
        assert rel == "uploads/test.jpg"

    def test_raises_on_path_traversal(self):
        svc = _make_service()
        media_root = Path("/media")
        with pytest.raises(ValidationException):
            svc._resolve_image_path("/../../../etc/passwd", media_root)


class TestSuccessResult:

    def test_format(self):
        svc = _make_service()
        result = svc._success_result("id_card_merged/test.pdf")
        assert result["success"] is True
        assert result["pdf_path"] == "id_card_merged/test.pdf"
        assert result["pdf_url"] == "/media/id_card_merged/test.pdf"
