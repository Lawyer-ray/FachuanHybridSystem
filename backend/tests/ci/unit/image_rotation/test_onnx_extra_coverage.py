"""Additional coverage tests for onnx_service and image_rotation modules."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest
from PIL import Image


def _make_test_image(width: int = 100, height: int = 100, color: str = "white", fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestONNXServiceRound2:
    def test_init_custom_path(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService(model_path="/custom/model.onnx")
        assert svc._model_path == "/custom/model.onnx"

    def test_session_not_loaded_returns_none(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService(model_path="/nonexistent/model.onnx")
        with patch("apps.image_rotation.services.orientation.onnx_service.Path") as mock_path_cls:
            mock_path_cls.return_value.exists.return_value = False
            result = svc.session
            assert result is None

    def test_session_import_error(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService(model_path="/nonexistent.onnx")
        with patch.dict("sys.modules", {"onnxruntime": None}):
            with patch("apps.image_rotation.services.orientation.onnx_service.Path") as mock_path_cls:
                mock_path_cls.return_value.exists.return_value = False
                result = svc.session
                assert result is None

    def test_session_load_error(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService(model_path="/bad/model.onnx")
        with patch("apps.image_rotation.services.orientation.onnx_service.Path") as mock_path_cls:
            mock_path_cls.return_value.exists.return_value = True
            mock_ort = MagicMock()
            mock_ort.InferenceSession.side_effect = RuntimeError("load fail")
            with patch.dict("sys.modules", {"onnxruntime": mock_ort}):
                result = svc.session
                assert result is None

    def test_session_caches(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        mock_session = MagicMock()
        svc._session = mock_session
        assert svc.session is mock_session

    def test_download_from_hub_import_error(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            svc._download_from_hub()  # should not raise

    def test_download_from_hub_exception(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        mock_hub = MagicMock()
        mock_hub.hf_hub_download.side_effect = RuntimeError("download fail")
        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            svc._download_from_hub()  # should not raise

    def test_preprocess_image(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        img_data = _make_test_image(200, 200)
        result = svc.preprocess_image(img_data)
        assert result.shape == (1, 3, 384, 384)
        assert result.dtype == np.float32

    def test_preprocess_image_rgba(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = svc.preprocess_image(buf.getvalue())
        assert result.shape == (1, 3, 384, 384)

    def test_detect_orientation_no_session(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        svc._session = None
        with patch.object(type(svc), "session", new_callable=PropertyMock, return_value=None):
            result = svc.detect_orientation(_make_test_image())
            assert result["method"] == "onnx_unavailable"

    def test_detect_orientation_success(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        mock_session = MagicMock()
        logits = np.array([[2.0, 0.5, 0.3, 0.1]], dtype=np.float32)
        mock_session.run.return_value = [logits]
        svc._session = mock_session
        result = svc.detect_orientation(_make_test_image())
        assert result["method"] == "onnx_classifier"
        assert "rotation" in result
        assert "confidence" in result
        assert "probabilities" in result

    def test_detect_orientation_high_conf_nonzero_rotation(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        mock_session = MagicMock()
        logits = np.array([[0.1, 5.0, 0.1, 0.1]], dtype=np.float32)
        mock_session.run.return_value = [logits]
        svc._session = mock_session
        result = svc.detect_orientation(_make_test_image())
        assert result["can_auto_rotate"] is True
        assert result["rotation"] == 180

    def test_detect_orientation_exception(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        mock_session = MagicMock()
        mock_session.run.side_effect = RuntimeError("inference fail")
        svc._session = mock_session
        result = svc.detect_orientation(b"bad data")
        assert result["method"] == "onnx_error"

    def test_detect_orientation_from_file(self):
        from apps.image_rotation.services.orientation.onnx_service import ONNXOrientationService
        svc = ONNXOrientationService()
        svc._session = None
        with patch.object(type(svc), "session", new_callable=PropertyMock, return_value=None):
            with patch("builtins.open", MagicMock()):
                result = svc.detect_orientation_from_file("/fake/path.jpg")
                assert result["method"] == "onnx_unavailable"

    def test_get_onnx_orientation_service_singleton(self):
        import apps.image_rotation.services.orientation.onnx_service as mod
        mod._onnx_service = None
        svc = mod.get_onnx_orientation_service()
        assert svc is not None
        svc2 = mod.get_onnx_orientation_service()
        assert svc is svc2
        mod._onnx_service = None  # cleanup

    def test_orientation_labels_and_mappings(self):
        from apps.image_rotation.services.orientation.onnx_service import (
            ORIENTATION_LABELS,
            ORIENTATION_TO_ROTATION,
        )
        assert len(ORIENTATION_LABELS) == 4
        assert len(ORIENTATION_TO_ROTATION) == 4
        assert ORIENTATION_TO_ROTATION[0] == 0
        assert ORIENTATION_TO_ROTATION[1] == 180
