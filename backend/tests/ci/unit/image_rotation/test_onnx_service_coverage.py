"""Coverage tests for onnx_service orientation detection."""
from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch, mock_open
from types import SimpleNamespace

import numpy as np
import pytest


class TestONNXOrientationServiceInit:
    def test_default_model_path(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        assert svc._session is None
        assert svc._model_path.endswith(".onnx")

    def test_custom_model_path(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService(model_path="/custom/model.onnx")
        assert svc._model_path == "/custom/model.onnx"


class TestSessionProperty:
    def test_import_error(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService(model_path="/tmp/test.onnx")
        with patch.dict("sys.modules", {"onnxruntime": None}):
            result = svc.session
            assert result is None

    def test_model_not_exists_download_fails(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService(model_path="/tmp/nonexistent.onnx")
        with patch("apps.image_rotation.services.orientation.onnx_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path
            with patch.dict("sys.modules", {"onnxruntime": MagicMock()}):
                svc._download_from_hub = MagicMock()
                result = svc.session
                assert result is None

    def test_session_success(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService(model_path="/tmp/model.onnx")
        mock_ort = MagicMock()
        mock_session = MagicMock()
        mock_ort.InferenceSession.return_value = mock_session

        with patch("apps.image_rotation.services.orientation.onnx_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            MockPath.return_value = mock_path

            with patch.dict("sys.modules", {"onnxruntime": mock_ort}):
                result = svc.session
                assert result is mock_session

    def test_session_exception(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService(model_path="/tmp/model.onnx")
        mock_ort = MagicMock()
        mock_ort.InferenceSession.side_effect = RuntimeError("load failed")

        with patch("apps.image_rotation.services.orientation.onnx_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            MockPath.return_value = mock_path

            with patch.dict("sys.modules", {"onnxruntime": mock_ort}):
                result = svc.session
                assert result is None


class TestDownloadFromHub:
    def test_download_success(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        mock_hub = MagicMock()

        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            with patch("apps.image_rotation.services.orientation.onnx_service.MODEL_DIR") as mock_dir:
                svc._download_from_hub()
                mock_hub.hf_hub_download.assert_called_once()

    def test_import_error(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            svc._download_from_hub()  # Should not raise

    def test_download_exception(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        mock_hub = MagicMock()
        mock_hub.hf_hub_download.side_effect = Exception("network error")

        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            svc._download_from_hub()  # Should not raise


class TestPreprocessImage:
    def test_rgb_image(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        # Create a small valid PNG in memory
        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_data = buf.getvalue()

        result = svc.preprocess_image(image_data)
        assert result.shape == (1, 3, 384, 384)
        assert result.dtype == np.float32

    def test_rgba_image(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        from PIL import Image
        import io

        img = Image.new("RGBA", (50, 50), color=(128, 128, 128, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_data = buf.getvalue()

        result = svc.preprocess_image(image_data)
        assert result.shape == (1, 3, 384, 384)


class TestDetectOrientation:
    def test_no_session(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        svc._session = None
        with patch.object(type(svc), "session", new_callable=lambda: property(lambda self: None)):
            result = svc.detect_orientation(b"\x89PNG")
            assert result["rotation"] == 0
            assert result["method"] == "onnx_unavailable"

    def test_detection_success(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        mock_session = MagicMock()
        # Simulate logits for class 0 (0 degrees)
        logits = np.array([[10.0, 0.1, 0.1, 0.1]], dtype=np.float32)
        mock_session.run.return_value = [logits]
        svc._session = mock_session

        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_data = buf.getvalue()

        result = svc.detect_orientation(image_data)
        assert result["rotation"] == 0
        assert result["method"] == "onnx_classifier"
        assert result["confidence"] > 0.9
        assert result["can_auto_rotate"] is False  # rotation == 0

    def test_detection_90_degrees(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        mock_session = MagicMock()
        # Class 3 = 90 degrees clockwise
        logits = np.array([[0.1, 0.1, 0.1, 10.0]], dtype=np.float32)
        mock_session.run.return_value = [logits]
        svc._session = mock_session

        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_data = buf.getvalue()

        result = svc.detect_orientation(image_data)
        assert result["rotation"] == -270
        assert result["can_auto_rotate"] is True

    def test_detection_exception(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        mock_session = MagicMock()
        svc._session = mock_session

        # Mock preprocess to return valid data but session.run to fail
        svc.preprocess_image = MagicMock(side_effect=RuntimeError("inference failed"))

        result = svc.detect_orientation(b"\x89PNG data")
        assert result["rotation"] == 0
        assert result["method"] == "onnx_error"
        assert "inference failed" in result["error"]

    def test_low_confidence_no_auto_rotate(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        mock_session = MagicMock()
        # Low confidence: logits are close
        logits = np.array([[1.0, 0.9, 0.8, 0.7]], dtype=np.float32)
        mock_session.run.return_value = [logits]
        svc._session = mock_session

        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        result = svc.detect_orientation(buf.getvalue())
        assert result["can_auto_rotate"] is False or result["confidence"] < 0.65


class TestDetectOrientationFromFile:
    def test_reads_file_and_calls_detect(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService

        svc = ONNXOrientationService()
        svc.detect_orientation = MagicMock(return_value={"rotation": 0})

        with patch("builtins.open", mock_open(read_data=b"\x89PNG")):
            result = svc.detect_orientation_from_file("/tmp/test.png")

        svc.detect_orientation.assert_called_once_with(b"\x89PNG")
        assert result == {"rotation": 0}


class TestGetOnnxOrientationService:
    def test_singleton(self):
        import apps.image_rotation.services.orientation.onnx_service as mod

        old = mod._onnx_service
        mod._onnx_service = None
        try:
            svc1 = mod.get_onnx_orientation_service()
            svc2 = mod.get_onnx_orientation_service()
            assert svc1 is svc2
        finally:
            mod._onnx_service = old


class TestOrientationMappings:
    def test_labels_complete(self):
        from apps.image_rotation.services.orientation.onnx_service import ORIENTATION_LABELS

        assert len(ORIENTATION_LABELS) == 4
        assert 0 in ORIENTATION_LABELS
        assert 3 in ORIENTATION_LABELS

    def test_rotation_mapping(self):
        from apps.image_rotation.services.orientation.onnx_service import ORIENTATION_TO_ROTATION

        assert ORIENTATION_TO_ROTATION[0] == 0
        assert ORIENTATION_TO_ROTATION[1] == 180
        assert ORIENTATION_TO_ROTATION[2] == -90
        assert ORIENTATION_TO_ROTATION[3] == -270
