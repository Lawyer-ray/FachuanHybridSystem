"""Coverage tests for frame_processing_service."""
from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService
from apps.chat_records.services.extraction.extract_helpers import DedupState, ExtractParams


class TestIsDhashDuplicate:
    def test_duplicate_found(self):
        svc = FrameProcessingService()
        mock_selection = MagicMock()
        mock_selection.hamming_distance_hex.return_value = 3
        result = svc.is_dhash_duplicate(mock_selection, "abc", ["def", "ghi"], window=5, threshold=5)
        assert result is True

    def test_no_duplicate(self):
        svc = FrameProcessingService()
        mock_selection = MagicMock()
        mock_selection.hamming_distance_hex.return_value = 20
        result = svc.is_dhash_duplicate(mock_selection, "abc", ["def"], window=5, threshold=5)
        assert result is False

    def test_none_distance(self):
        svc = FrameProcessingService()
        mock_selection = MagicMock()
        mock_selection.hamming_distance_hex.return_value = None
        result = svc.is_dhash_duplicate(mock_selection, "abc", ["def"], window=5, threshold=5)
        assert result is False

    def test_empty_kept_list(self):
        svc = FrameProcessingService()
        mock_selection = MagicMock()
        result = svc.is_dhash_duplicate(mock_selection, "abc", [], window=5, threshold=5)
        assert result is False


class TestIsPixelDuplicate:
    def test_duplicate_found(self):
        svc = FrameProcessingService()
        mock_selection = MagicMock()
        mock_selection.mean_abs_diff.return_value = 0.05
        result = svc.is_pixel_duplicate(mock_selection, b"thumb", [b"prev"], window=5, threshold=0.1)
        assert result is True

    def test_no_duplicate(self):
        svc = FrameProcessingService()
        mock_selection = MagicMock()
        mock_selection.mean_abs_diff.return_value = 0.5
        result = svc.is_pixel_duplicate(mock_selection, b"thumb", [b"prev"], window=5, threshold=0.1)
        assert result is False

    def test_none_diff(self):
        svc = FrameProcessingService()
        mock_selection = MagicMock()
        mock_selection.mean_abs_diff.return_value = None
        result = svc.is_pixel_duplicate(mock_selection, b"thumb", [b"prev"], window=5, threshold=0.1)
        assert result is False


class TestCheckOcrSimilarity:
    def test_empty_ocr_text(self):
        svc = FrameProcessingService()
        state = DedupState()
        result = svc.check_ocr_similarity("", state, 0.8, 10)
        assert result is None

    def test_no_kept_texts(self):
        svc = FrameProcessingService()
        state = DedupState()
        result = svc.check_ocr_similarity("hello", state, 0.8, 10)
        assert result is None

    def test_similar_text_skipped(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.kept_ocr_texts = ["hello world"]
        state.kept_ocr_shingles = [{"hel", "ell", "llo"}]
        result = svc.check_ocr_similarity("hello world", state, 0.5, 10)
        assert result is not None
        assert result < 1.0

    def test_different_text_not_skipped(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.kept_ocr_texts = ["completely different text"]
        state.kept_ocr_shingles = [{"com", "omp", "mpl"}]
        result = svc.check_ocr_similarity("xyz", state, 0.95, 10)
        assert result is None

    def test_empty_prev_text_skipped(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.kept_ocr_texts = [""]
        state.kept_ocr_shingles = [set()]
        result = svc.check_ocr_similarity("hello", state, 0.8, 10)
        assert result is None


class TestGetOcrFrameScore:
    def test_empty_text(self):
        svc = FrameProcessingService()
        state = DedupState()
        assert svc.get_ocr_frame_score(0.0, "", state) == 0.0

    def test_no_kept_texts(self):
        svc = FrameProcessingService()
        state = DedupState()
        assert svc.get_ocr_frame_score(0.0, "hello", state) == 0.0

    def test_with_kept_texts(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.kept_ocr_texts = ["prev text"]
        state.kept_ocr_shingles = [{"pre", "rev"}]
        result = svc.get_ocr_frame_score(0.0, "new text here", state)
        assert result >= 0.0


class TestCollectFrameFiles:
    def test_collects_jpg_files(self, tmp_path):
        svc = FrameProcessingService()
        (tmp_path / "frame_001.jpg").write_bytes(b"jpg1")
        (tmp_path / "frame_002.jpg").write_bytes(b"jpg2")
        (tmp_path / "other.txt").write_bytes(b"txt")

        result = svc.collect_frame_files(str(tmp_path))
        assert len(result) == 2
        assert all(f.endswith(".jpg") for f in result)

    def test_empty_dir(self, tmp_path):
        svc = FrameProcessingService()
        result = svc.collect_frame_files(str(tmp_path))
        assert result == []


class TestCalcCaptureTime:
    def test_interval_based(self):
        svc = FrameProcessingService()
        params = ExtractParams(interval_based=True, interval_seconds=2.0)
        info = MagicMock()
        info.time_base_seconds = None
        result = svc.calc_capture_time("frame_003.jpg", 3, params, info)
        assert result == 4.0  # (3-1) * 2.0

    def test_frame_based_with_time_base(self):
        svc = FrameProcessingService()
        params = ExtractParams(interval_based=False, interval_seconds=0)
        info = MagicMock()
        info.time_base_seconds = 0.04
        result = svc.calc_capture_time("frame_000042.jpg", 1, params, info)
        assert result is not None
        assert abs(result - 42 * 0.04) < 0.001

    def test_frame_based_no_match(self):
        svc = FrameProcessingService()
        params = ExtractParams(interval_based=False, interval_seconds=0)
        info = MagicMock()
        info.time_base_seconds = 0.04
        result = svc.calc_capture_time("no_numbers.jpg", 1, params, info)
        assert result is None


class TestUpdateDedupState:
    def test_basic_update(self):
        svc = FrameProcessingService()
        state = DedupState()
        svc.update_dedup_state(
            state, "digest1", "dhash1", b"thumb", "ocr text",
            MagicMock(), 0.1, MagicMock(), b"content"
        )
        assert state.created_count == 1
        assert "digest1" in state.seen_sha256
        assert "dhash1" in state.kept_dhashes

    def test_update_without_ocr(self):
        svc = FrameProcessingService()
        state = DedupState()
        svc.update_dedup_state(
            state, "digest1", "dhash1", b"", "ocr text",
            None, 0.1, MagicMock(), b"content"
        )
        assert state.created_count == 1
        assert len(state.kept_ocr_texts) == 0

    def test_update_with_pixel_threshold(self):
        svc = FrameProcessingService()
        state = DedupState()
        mock_sel = MagicMock()
        mock_sel.calc_thumb_bytes.return_value = b"thumb_data"
        svc.update_dedup_state(
            state, "digest1", "dhash1", b"", "",
            None, 0.1, mock_sel, b"content"
        )
        assert len(state.kept_thumbs) == 1


class TestIsFrameDuplicate:
    def test_sha256_duplicate(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.existing_sha256.add("abc123")
        is_dup, thumb = svc.is_frame_duplicate(
            b"content", "abc123", "dhash", state,
            ExtractParams(), MagicMock(), 5, 0.1
        )
        assert is_dup is True

    def test_seen_sha256_duplicate(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.seen_sha256.add("abc123")
        is_dup, thumb = svc.is_frame_duplicate(
            b"content", "abc123", "dhash", state,
            ExtractParams(), MagicMock(), 5, 0.1
        )
        assert is_dup is True

    def test_dhash_duplicate(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.kept_dhashes = ["prev_dhash"]
        mock_sel = MagicMock()
        mock_sel.hamming_distance_hex.return_value = 2
        params = ExtractParams(dedup_threshold=5)
        is_dup, thumb = svc.is_frame_duplicate(
            b"content", "new_digest", "new_dhash", state,
            params, mock_sel, 5, 0.0
        )
        assert is_dup is True

    def test_pixel_duplicate(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.kept_thumbs = [b"prev_thumb"]
        mock_sel = MagicMock()
        mock_sel.calc_thumb_bytes.return_value = b"new_thumb"
        mock_sel.mean_abs_diff.return_value = 0.01
        params = ExtractParams(dedup_threshold=0)
        is_dup, thumb = svc.is_frame_duplicate(
            b"content", "new_digest", "dhash", state,
            params, mock_sel, 5, 0.1
        )
        assert is_dup is True

    def test_not_duplicate(self):
        svc = FrameProcessingService()
        state = DedupState()
        params = ExtractParams(dedup_threshold=0)
        is_dup, thumb = svc.is_frame_duplicate(
            b"content", "new_digest", "dhash", state,
            params, MagicMock(), 5, 0.0
        )
        assert is_dup is False


class TestProcessOcrForFrame:
    def test_no_ocr_service(self):
        svc = FrameProcessingService()
        state = DedupState()
        params = ExtractParams()
        ocr_text, score, skip = svc.process_ocr_for_frame(
            b"content", None, MagicMock(), state, params, 99999.0, MagicMock()
        )
        assert ocr_text == ""
        assert skip is False

    def test_timeout_degrades(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.ocr_disabled = False
        params = ExtractParams()
        mock_updater = MagicMock()
        ocr_text, score, skip = svc.process_ocr_for_frame(
            b"content", MagicMock(), MagicMock(), state, params, -1.0, mock_updater
        )
        assert state.ocr_disabled is True
        assert skip is False

    def test_empty_ocr_created_count_zero(self):
        svc = FrameProcessingService()
        state = DedupState()
        state.created_count = 0
        state.ocr_disabled = False
        params = ExtractParams()
        mock_sel = MagicMock()
        mock_sel.crop_for_ocr_bytes_with_range.return_value = (b"", 0)
        mock_ocr = MagicMock()

        ocr_text, score, skip = svc.process_ocr_for_frame(
            b"content", mock_ocr, mock_sel, state, params, 99999.0, MagicMock()
        )
        assert skip is False  # created_count == 0

    def test_empty_ocr_created_count_positive(self):
        import time
        svc = FrameProcessingService()
        state = DedupState()
        state.created_count = 5
        state.ocr_disabled = False
        params = ExtractParams(ocr_similarity_threshold=0.8, ocr_min_new_chars=10)
        mock_sel = MagicMock()
        mock_sel.crop_for_ocr_bytes_with_range.return_value = (b"", 0)
        mock_ocr = MagicMock()

        ocr_text, score, skip = svc.process_ocr_for_frame(
            b"content", mock_ocr, mock_sel, state, params,
            time.monotonic() + 9999.0,  # far future deadline
            MagicMock()
        )
        # When crop is empty, ocr_text stays empty, created_count > 0 -> skip
        assert ocr_text == ""
        assert state.ocr_skipped >= 1


class TestReorderScreenshots:
    def test_calls_callback(self):
        svc = FrameProcessingService()
        callback = MagicMock()
        svc.reorder_screenshots(42, callback)
        callback.assert_called_once_with(42)
