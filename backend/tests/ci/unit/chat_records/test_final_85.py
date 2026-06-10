"""Coverage tests for chat_records services.

Targets uncovered lines in:
- extraction/frame_selection_service.py (73 uncovered)
- extraction/frame_processing_service.py (85 uncovered)
- export/docx_export_service.py (71 uncovered)
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.chat_records.services.extraction.frame_selection_service import FrameSelectionService


# ===================================================================
# FrameSelectionService: calc_dhash_hex
# ===================================================================
class TestCalcDhashHex:
    def test_empty_bytes_returns_empty(self):
        svc = FrameSelectionService()
        assert svc.calc_dhash_hex(b"") == ""

    def test_zero_hash_size_returns_empty(self):
        svc = FrameSelectionService()
        assert svc.calc_dhash_hex(b"\x00", hash_size=0) == ""

    def test_valid_image(self):
        from PIL import Image

        svc = FrameSelectionService()
        img = Image.new("L", (100, 100), color=128)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = svc.calc_dhash_hex(buf.getvalue())
        assert len(result) > 0

    def test_consistent_hash(self):
        from PIL import Image

        svc = FrameSelectionService()
        img = Image.new("L", (100, 100), color=128)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        assert svc.calc_dhash_hex(data) == svc.calc_dhash_hex(data)


# ===================================================================
# FrameSelectionService: hamming_distance_hex
# ===================================================================
class TestHammingDistanceHex:
    def test_empty_returns_none(self):
        svc = FrameSelectionService()
        assert svc.hamming_distance_hex("", "abc") is None
        assert svc.hamming_distance_hex("abc", "") is None

    def test_same_hash_returns_zero(self):
        svc = FrameSelectionService()
        assert svc.hamming_distance_hex("ff", "ff") == 0

    def test_different_hashes(self):
        svc = FrameSelectionService()
        result = svc.hamming_distance_hex("00", "ff")
        assert result is not None
        assert result > 0

    def test_invalid_hex_returns_none(self):
        svc = FrameSelectionService()
        assert svc.hamming_distance_hex("zz", "ff") is None


# ===================================================================
# FrameSelectionService: calc_thumb_bytes
# ===================================================================
class TestCalcThumbBytes:
    def test_empty_bytes(self):
        svc = FrameSelectionService()
        assert svc.calc_thumb_bytes(b"") == b""

    def test_zero_size(self):
        svc = FrameSelectionService()
        assert svc.calc_thumb_bytes(b"\x00", size=0) == b""

    def test_valid_image(self):
        from PIL import Image

        svc = FrameSelectionService()
        img = Image.new("L", (100, 100), color=128)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = svc.calc_thumb_bytes(buf.getvalue(), size=24)
        assert len(result) > 0


# ===================================================================
# FrameSelectionService: mean_abs_diff
# ===================================================================
class TestMeanAbsDiff:
    def test_empty_returns_none(self):
        svc = FrameSelectionService()
        assert svc.mean_abs_diff(b"", b"abc") is None
        assert svc.mean_abs_diff(b"abc", b"") is None

    def test_different_length_returns_none(self):
        svc = FrameSelectionService()
        assert svc.mean_abs_diff(b"ab", b"abc") is None

    def test_same_returns_zero(self):
        svc = FrameSelectionService()
        assert svc.mean_abs_diff(b"\x00\x01", b"\x00\x01") == 0.0

    def test_different_returns_positive(self):
        svc = FrameSelectionService()
        result = svc.mean_abs_diff(b"\x00", b"\xff")
        assert result == 255.0


# ===================================================================
# FrameSelectionService: crop_for_ocr_bytes
# ===================================================================
class TestCropForOcrBytes:
    def test_empty_bytes(self):
        svc = FrameSelectionService()
        assert svc.crop_for_ocr_bytes(b"") == b""

    def test_valid_image(self):
        from PIL import Image

        svc = FrameSelectionService()
        img = Image.new("RGB", (800, 600), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = svc.crop_for_ocr_bytes(buf.getvalue())
        assert len(result) > 0


# ===================================================================
# FrameSelectionService: crop_for_ocr_bytes_with_range
# ===================================================================
class TestCropForOcrBytesWithRange:
    def test_empty_bytes(self):
        svc = FrameSelectionService()
        result = svc.crop_for_ocr_bytes_with_range(b"")
        assert result == (b"", 0)

    def test_valid_image(self):
        from PIL import Image

        svc = FrameSelectionService()
        img = Image.new("RGB", (800, 600), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        cropped, y_start = svc.crop_for_ocr_bytes_with_range(buf.getvalue())
        assert len(cropped) > 0
        assert isinstance(y_start, int)


# ===================================================================
# FrameProcessingService: is_dhash_duplicate
# ===================================================================
class TestFrameProcessingIsDhashDuplicate:
    def test_no_duplicate(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        sel_svc = Mock()
        sel_svc.hamming_distance_hex.return_value = 50  # large distance
        result = svc.is_dhash_duplicate(sel_svc, "abc", ["def"], window=3, threshold=10)
        assert result is False

    def test_duplicate_found(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        sel_svc = Mock()
        sel_svc.hamming_distance_hex.return_value = 2  # small distance
        result = svc.is_dhash_duplicate(sel_svc, "abc", ["def"], window=3, threshold=10)
        assert result is True

    def test_empty_kept_hashes(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        sel_svc = Mock()
        result = svc.is_dhash_duplicate(sel_svc, "abc", [], window=3, threshold=10)
        assert result is False


# ===================================================================
# FrameProcessingService: is_pixel_duplicate
# ===================================================================
class TestFrameProcessingIsPixelDuplicate:
    def test_no_duplicate(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        sel_svc = Mock()
        sel_svc.mean_abs_diff.return_value = 50.0
        result = svc.is_pixel_duplicate(sel_svc, b"thumb", [b"prev"], window=3, threshold=5.0)
        assert result is False

    def test_duplicate_found(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        sel_svc = Mock()
        sel_svc.mean_abs_diff.return_value = 1.0
        result = svc.is_pixel_duplicate(sel_svc, b"thumb", [b"prev"], window=3, threshold=5.0)
        assert result is True

    def test_empty_kept_thumbs(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        sel_svc = Mock()
        result = svc.is_pixel_duplicate(sel_svc, b"thumb", [], window=3, threshold=5.0)
        assert result is False


# ===================================================================
# FrameProcessingService: check_ocr_similarity
# ===================================================================
class TestFrameProcessingCheckOcrSimilarity:
    def test_empty_ocr_text(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        state = SimpleNamespace(kept_ocr_texts=["prev text"])
        result = svc.check_ocr_similarity("", state, 0.8, 5)
        assert result is None

    def test_no_kept_texts(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        state = SimpleNamespace(kept_ocr_texts=[])
        result = svc.check_ocr_similarity("new text", state, 0.8, 5)
        assert result is None
