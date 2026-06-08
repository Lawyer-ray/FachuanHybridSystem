"""OCRService 全覆盖测试。"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

from apps.automation.services.ocr.ocr_service import OCRService, OCRTextResult, _ocr_engine_cache


class TestOCRTextResult:
    """OCRTextResult 数据类测试。"""

    def test_creation(self) -> None:
        r = OCRTextResult(text="hello|world", raw_texts=["hello", "world"])
        assert r.text == "hello|world"
        assert r.raw_texts == ["hello", "world"]


class TestOCRService:
    """OCRService 测试。"""

    def _make_service(self, provider: str = "local") -> OCRService:
        svc = OCRService.__new__(OCRService)
        svc.use_v5 = False
        svc._provider = provider
        svc._ocr = MagicMock()
        svc._paddleocr_engine = None
        return svc

    # ─── provider property ───

    def test_provider_explicit(self) -> None:
        svc = self._make_service("paddleocr_api")
        assert svc.provider == "paddleocr_api"

    @patch("apps.automation.services.ocr.ocr_service._get_ocr_provider", return_value="local")
    def test_provider_from_config(self, mock_get: MagicMock) -> None:
        svc = OCRService.__new__(OCRService)
        svc.use_v5 = False
        svc._provider = None
        svc._ocr = MagicMock()
        svc._paddleocr_engine = None
        assert svc.provider == "local"

    # ─── ocr property ───

    def test_ocr_lazy_load(self) -> None:
        svc = OCRService.__new__(OCRService)
        svc.use_v5 = False
        svc._provider = "local"
        svc._ocr = MagicMock(return_value="result")
        assert svc.ocr() == "result"

    # ─── paddleocr_engine property ───

    def test_paddleocr_engine_lazy_load(self) -> None:
        svc = self._make_service("paddleocr_api")
        mock_engine_cls = MagicMock()
        with patch("apps.automation.services.ocr.ocr_service.OCRService.paddleocr_engine", new_callable=lambda: property(lambda self: mock_engine_cls())):
            pass
        # Test lazy loading
        svc._paddleocr_engine = MagicMock()
        assert svc.paddleocr_engine is not None

    # ─── recognize ───

    def test_recognize_local_success(self) -> None:
        svc = self._make_service("local")
        mock_result = MagicMock()
        mock_result.txts = ["hello", "world"]
        svc._ocr.return_value = mock_result
        text = svc.recognize("/path/to/image.png")
        assert text == "hello\nworld"

    def test_recognize_local_empty(self) -> None:
        svc = self._make_service("local")
        mock_result = MagicMock()
        mock_result.txts = []
        svc._ocr.return_value = mock_result
        text = svc.recognize("/path/to/image.png")
        assert text == ""

    def test_recognize_local_none_result(self) -> None:
        svc = self._make_service("local")
        svc._ocr.return_value = None
        text = svc.recognize("/path/to/image.png")
        assert text == ""

    def test_recognize_paddleocr_api(self) -> None:
        svc = self._make_service("paddleocr_api")
        svc._paddleocr_engine = MagicMock()
        svc._paddleocr_engine.recognize_bytes.return_value = MagicMock(text="result")
        with patch("pathlib.Path.read_bytes", return_value=b"fake"):
            text = svc._recognize_via_paddleocr_path("/path/to/image.png")
            assert text == "result"

    # ─── recognize_with_boxes ───

    def test_recognize_with_boxes_success(self) -> None:
        svc = self._make_service("local")
        mock_result = MagicMock()
        mock_result.boxes = ["box1", "box2"]
        mock_result.txts = ["t1", "t2"]
        mock_result.scores = [0.95, 0.90]
        svc._ocr.return_value = mock_result
        boxes, scores = svc.recognize_with_boxes("/img.png")
        assert boxes is not None
        assert len(boxes) == 2
        assert scores == [0.95, 0.90]

    def test_recognize_with_boxes_no_boxes(self) -> None:
        svc = self._make_service("local")
        mock_result = MagicMock()
        mock_result.boxes = None
        svc._ocr.return_value = mock_result
        boxes, scores = svc.recognize_with_boxes("/img.png")
        assert boxes is None

    def test_recognize_with_boxes_paddleocr_api_fallback(self) -> None:
        svc = self._make_service("paddleocr_api")
        mock_result = MagicMock()
        mock_result.boxes = ["box1"]
        mock_result.txts = ["t1"]
        mock_result.scores = [0.9]
        svc._ocr.return_value = mock_result
        boxes, scores = svc.recognize_with_boxes("/img.png")
        assert boxes is not None

    # ─── recognize_bytes ───

    def test_recognize_bytes_local(self) -> None:
        svc = self._make_service("local")
        mock_result = MagicMock()
        mock_result.txts = ["text1"]
        svc._ocr.return_value = mock_result
        text = svc.recognize_bytes(b"image bytes")
        assert text == "text1"

    def test_recognize_bytes_local_empty(self) -> None:
        svc = self._make_service("local")
        svc._ocr.return_value = None
        text = svc.recognize_bytes(b"")
        assert text == ""

    def test_recognize_bytes_paddleocr_api(self) -> None:
        svc = self._make_service("paddleocr_api")
        svc._paddleocr_engine = MagicMock()
        svc._paddleocr_engine.recognize_bytes.return_value = MagicMock(text="api result")
        text = svc.recognize_bytes(b"image bytes")
        assert text == "api result"

    # ─── _recognize_via_paddleocr_path ───

    def test_recognize_via_paddleocr_path_success(self) -> None:
        svc = self._make_service("paddleocr_api")
        svc._paddleocr_engine = MagicMock()
        svc._paddleocr_engine.recognize_bytes.return_value = MagicMock(text="path result")
        with patch("pathlib.Path.read_bytes", return_value=b"fake"):
            text = svc._recognize_via_paddleocr_path("/file.png")
            assert text == "path result"

    def test_recognize_via_paddleocr_path_fallback(self) -> None:
        svc = self._make_service("paddleocr_api")
        svc._paddleocr_engine = MagicMock()
        svc._paddleocr_engine.recognize_bytes.side_effect = OSError("network")
        mock_result = MagicMock()
        mock_result.txts = ["fallback"]
        svc._ocr.return_value = mock_result
        with patch("pathlib.Path.read_bytes", return_value=b"fake"):
            text = svc._recognize_via_paddleocr_path("/file.png")
            assert text == "fallback"

    def test_recognize_via_paddleocr_path_pdf(self) -> None:
        svc = self._make_service("paddleocr_api")
        svc._paddleocr_engine = MagicMock()
        svc._paddleocr_engine.recognize_bytes.return_value = MagicMock(text="pdf result")
        with patch("pathlib.Path.read_bytes", return_value=b"pdf fake"):
            text = svc._recognize_via_paddleocr_path("/file.pdf")
            svc._paddleocr_engine.recognize_bytes.assert_called_with(b"pdf fake", is_pdf=True)

    # ─── _recognize_via_paddleocr_bytes ───

    def test_recognize_via_paddleocr_bytes_success(self) -> None:
        svc = self._make_service("paddleocr_api")
        svc._paddleocr_engine = MagicMock()
        svc._paddleocr_engine.recognize_bytes.return_value = MagicMock(text="bytes result")
        text = svc._recognize_via_paddleocr_bytes(b"image")
        assert text == "bytes result"

    def test_recognize_via_paddleocr_bytes_fallback(self) -> None:
        svc = self._make_service("paddleocr_api")
        svc._paddleocr_engine = MagicMock()
        svc._paddleocr_engine.recognize_bytes.side_effect = ValueError("err")
        mock_result = MagicMock()
        mock_result.txts = ["fb"]
        svc._ocr.return_value = mock_result
        text = svc._recognize_via_paddleocr_bytes(b"img")
        assert text == "fb"

    # ─── _to_list ───

    def test_to_list_none(self) -> None:
        svc = self._make_service()
        assert svc._to_list(None) == []

    def test_to_list_with_tolist(self) -> None:
        svc = self._make_service()
        obj = MagicMock()
        obj.tolist.return_value = [1, 2, 3]
        assert svc._to_list(obj) == [1, 2, 3]

    def test_to_list_with_iterable(self) -> None:
        svc = self._make_service()
        assert svc._to_list([4, 5]) == [4, 5]

    def test_to_list_with_scalar(self) -> None:
        svc = self._make_service()
        result = svc._to_list(42)
        assert result == [42]

    # ─── _get_position_key ───

    def test_get_position_key_empty_box(self) -> None:
        svc = self._make_service()
        assert svc._get_position_key([]) == (0.0, 0.0)

    def test_get_position_key_none_box(self) -> None:
        svc = self._make_service()
        assert svc._get_position_key(None) == (0.0, 0.0)

    # ─── _is_timestamp_text ───

    def test_is_timestamp_hhmm(self) -> None:
        svc = self._make_service()
        assert svc._is_timestamp_text("12:30") is True
        assert svc._is_timestamp_text("9:05") is True

    def test_is_timestamp_date_dash(self) -> None:
        svc = self._make_service()
        assert svc._is_timestamp_text("2025-01-01") is True

    def test_is_timestamp_date_slash(self) -> None:
        svc = self._make_service()
        assert svc._is_timestamp_text("2025/1/1") is True

    def test_is_timestamp_chinese_date(self) -> None:
        svc = self._make_service()
        assert svc._is_timestamp_text("1月5日") is True

    def test_is_timestamp_normal_text(self) -> None:
        svc = self._make_service()
        assert svc._is_timestamp_text("判决书") is False

    # ─── extract_text ───

    def test_extract_text_empty_bytes(self) -> None:
        svc = self._make_service()
        result = svc.extract_text(b"")
        assert result.text == ""
        assert result.raw_texts == []

    def test_extract_text_paddleocr_api(self) -> None:
        svc = self._make_service("paddleocr_api")
        svc._paddleocr_engine = MagicMock()
        svc._paddleocr_engine.recognize_bytes.return_value = MagicMock(text="line1\nline2\n12:30")
        result = svc.extract_text(b"image")
        assert "line1" in result.raw_texts
        assert "line2" in result.raw_texts
        assert "12:30" not in result.raw_texts  # timestamp filtered

    def test_extract_text_paddleocr_api_fallback(self) -> None:
        svc = self._make_service("paddleocr_api")
        svc._paddleocr_engine = MagicMock()
        svc._paddleocr_engine.recognize_bytes.side_effect = Exception("fail")
        svc._ocr = MagicMock()
        mock_result = MagicMock()
        mock_result.txts = ["fallback_text"]
        mock_result.boxes = [[[0, 0], [1, 0], [1, 1], [0, 1]]]
        mock_result.scores = [0.95]
        svc._ocr.return_value = mock_result
        with patch("apps.automation.services.ocr.ocr_service.Image") as MockImage:
            MockImage.open.return_value.convert.return_value = MagicMock()
            result = svc.extract_text(b"image")
            assert "fallback_text" in result.raw_texts

    # ─── _extract_text_local ───

    def test_extract_text_local_with_filtering(self) -> None:
        svc = self._make_service("local")
        mock_result = MagicMock()
        mock_result.txts = ["判决书", "12:30", "", "low_conf", "hello"]
        mock_result.boxes = [
            [[10, 0], [20, 0], [20, 10], [10, 10]],
            [[10, 20], [20, 20], [20, 30], [10, 30]],
            [[10, 40], [20, 40], [20, 50], [10, 50]],
            [[10, 60], [20, 60], [20, 70], [10, 70]],
            [[10, 80], [20, 80], [20, 90], [10, 90]],
        ]
        mock_result.scores = [0.95, 0.90, 0.80, 0.30, 0.85]  # 0.30 < 0.50 filtered
        svc._ocr.return_value = mock_result
        with patch("apps.automation.services.ocr.ocr_service.Image") as MockImage:
            MockImage.open.return_value.convert.return_value = MagicMock()
            result = svc._extract_text_local(b"image")
            assert "判决书" in result.raw_texts
            assert "12:30" not in result.raw_texts
            assert "low_conf" not in result.raw_texts
            assert "hello" in result.raw_texts

    def test_extract_text_local_type_error(self) -> None:
        svc = self._make_service("local")
        svc._ocr.side_effect = TypeError("bad")
        with patch("apps.automation.services.ocr.ocr_service.Image") as MockImage:
            MockImage.open.return_value.convert.return_value = MagicMock()
            result = svc._extract_text_local(b"image")
            assert result.text == ""
