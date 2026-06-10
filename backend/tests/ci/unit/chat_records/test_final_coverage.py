"""Final coverage tests for chat_records module — extract_helpers and frame_processing."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

import pytest

from apps.chat_records.services.extraction.extract_helpers import (
    DedupState,
    ExtractParams,
    jaccard_sets,
    safe_float,
    safe_int,
    shingles,
)
from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService


# ============================================================================
# safe_int tests
# ============================================================================


class TestSafeInt:
    def test_valid_int(self):
        assert safe_int(42, 0) == 42

    def test_string_int(self):
        assert safe_int("123", 0) == 123

    def test_none_returns_default(self):
        assert safe_int(None, 10) == 10

    def test_invalid_string_returns_default(self):
        assert safe_int("abc", 5) == 5

    def test_float_string_returns_default(self):
        # int("3.14") raises ValueError, so safe_int returns default
        assert safe_int("3.14", 0) == 0

    def test_empty_string_returns_default(self):
        assert safe_int("", 7) == 7

    def test_bool_value(self):
        # bool is subclass of int
        assert safe_int(True, 0) == 1
        assert safe_int(False, 0) == 0


# ============================================================================
# safe_float tests
# ============================================================================


class TestSafeFloat:
    def test_valid_float(self):
        assert safe_float(3.14, 0.0) == 3.14

    def test_string_float(self):
        assert safe_float("2.5", 0.0) == 2.5

    def test_none_returns_default(self):
        assert safe_float(None, 1.0) == 1.0

    def test_invalid_returns_default(self):
        assert safe_float("abc", 0.5) == 0.5

    def test_lo_clamp(self):
        assert safe_float(0.5, 1.0, lo=1.0) == 1.0

    def test_hi_clamp(self):
        assert safe_float(5.0, 1.0, hi=3.0) == 3.0

    def test_in_range(self):
        assert safe_float(2.0, 1.0, lo=0.0, hi=5.0) == 2.0

    def test_int_input(self):
        assert safe_float(3, 0.0) == 3.0

    def test_lo_and_hi(self):
        assert safe_float(10.0, 1.0, lo=0.0, hi=5.0) == 5.0


# ============================================================================
# shingles tests
# ============================================================================


class TestShingles:
    def test_empty_string(self):
        assert shingles("") == set()

    def test_short_string(self):
        result = shingles("ab", n=3)
        assert result == {"ab"}

    def test_normal_string(self):
        result = shingles("abcde", n=3)
        assert "abc" in result
        assert "bcd" in result
        assert "cde" in result
        assert len(result) == 3

    def test_none_input(self):
        assert shingles(None) == set()

    def test_custom_n(self):
        result = shingles("abcdef", n=2)
        assert "ab" in result
        assert len(result) == 5

    def test_exact_length(self):
        result = shingles("abc", n=3)
        assert result == {"abc"}


# ============================================================================
# jaccard_sets tests
# ============================================================================


class TestJaccardSets:
    def test_identical_sets(self):
        sa = {"a", "b", "c"}
        assert jaccard_sets(sa, sa.copy()) == 1.0

    def test_disjoint_sets(self):
        sa = {"a", "b"}
        sb = {"c", "d"}
        assert jaccard_sets(sa, sb) == 0.0

    def test_partial_overlap(self):
        sa = {"a", "b", "c"}
        sb = {"b", "c", "d"}
        result = jaccard_sets(sa, sb)
        assert abs(result - 0.5) < 0.001  # 2/4

    def test_empty_sets(self):
        assert jaccard_sets(set(), set()) == 0.0
        assert jaccard_sets({"a"}, set()) == 0.0
        assert jaccard_sets(set(), {"a"}) == 0.0


# ============================================================================
# ExtractParams tests
# ============================================================================


class TestExtractParams:
    def test_defaults(self):
        params = ExtractParams()
        assert params.interval_seconds == 1.0
        assert params.strategy == "interval"
        assert params.interval_based is True
        assert params.dedup_threshold == 8

    def test_from_recording(self):
        recording = MagicMock()
        recording.extract_strategy = "ocr"
        recording.extract_dedup_threshold = 10
        recording.extract_ocr_similarity_threshold = 0.85
        recording.extract_ocr_min_new_chars = 12
        params = ExtractParams.from_recording(recording, 2.0)
        assert params.interval_seconds == 2.0
        assert params.strategy == "ocr"
        assert params.interval_based is True
        assert params.dedup_threshold == 10
        assert params.ocr_similarity_threshold == 0.85
        assert params.ocr_min_new_chars == 12

    def test_from_recording_none_attrs(self):
        recording = MagicMock(spec=[])  # no attributes
        params = ExtractParams.from_recording(recording, None)
        assert params.interval_seconds == 1.0
        assert params.strategy == "interval"

    def test_from_recording_invalid_interval(self):
        recording = MagicMock(spec=[])
        params = ExtractParams.from_recording(recording, "invalid")
        assert params.interval_seconds == 1.0

    def test_from_recording_non_interval_strategy(self):
        recording = MagicMock()
        recording.extract_strategy = "scene_change"
        recording.extract_dedup_threshold = None
        recording.extract_ocr_similarity_threshold = None
        recording.extract_ocr_min_new_chars = None
        params = ExtractParams.from_recording(recording, 1.0)
        assert params.interval_based is False


# ============================================================================
# DedupState tests
# ============================================================================


class TestDedupState:
    def test_defaults(self):
        state = DedupState()
        assert state.existing_sha256 == set()
        assert state.seen_sha256 == set()
        assert state.kept_dhashes == []
        assert state.created_count == 0
        assert state.ocr_disabled is False

    def test_custom_values(self):
        state = DedupState(created_count=5, processed_count=10, ocr_calls=3)
        assert state.created_count == 5
        assert state.processed_count == 10
        assert state.ocr_calls == 3


# ============================================================================
# FrameProcessingService is_dhash_duplicate tests
# ============================================================================


class TestFrameProcessingIsDhashDuplicate:
    def setup_method(self):
        self.service = FrameProcessingService()
        self.selection = MagicMock()

    def test_no_previous_hashes(self):
        self.selection.hamming_distance_hex.return_value = 0
        result = self.service.is_dhash_duplicate(self.selection, "abc", [], 5, 8)
        assert result is False

    def test_duplicate_found(self):
        self.selection.hamming_distance_hex.return_value = 2
        result = self.service.is_dhash_duplicate(self.selection, "abc", ["def"], 5, 8)
        assert result is True

    def test_not_duplicate(self):
        self.selection.hamming_distance_hex.return_value = 20
        result = self.service.is_dhash_duplicate(self.selection, "abc", ["def"], 5, 8)
        assert result is False

    def test_none_distance(self):
        self.selection.hamming_distance_hex.return_value = None
        result = self.service.is_dhash_duplicate(self.selection, "abc", ["def"], 5, 8)
        assert result is False

    def test_window_limits_search(self):
        self.selection.hamming_distance_hex.return_value = 2
        hashes = ["a", "b", "c", "d", "e"]
        # window=2 should only check last 2
        result = self.service.is_dhash_duplicate(self.selection, "new", hashes, 2, 8)
        assert result is True


# ============================================================================
# FrameProcessingService is_pixel_duplicate tests
# ============================================================================


class TestFrameProcessingIsPixelDuplicate:
    def setup_method(self):
        self.service = FrameProcessingService()
        self.selection = MagicMock()

    def test_no_previous_thumbs(self):
        result = self.service.is_pixel_duplicate(self.selection, b"thumb", [], 5, 0.1)
        assert result is False

    def test_duplicate_found(self):
        self.selection.mean_abs_diff.return_value = 0.05
        result = self.service.is_pixel_duplicate(self.selection, b"thumb", [b"prev"], 5, 0.1)
        assert result is True

    def test_not_duplicate(self):
        self.selection.mean_abs_diff.return_value = 0.5
        result = self.service.is_pixel_duplicate(self.selection, b"thumb", [b"prev"], 5, 0.1)
        assert result is False

    def test_none_diff(self):
        self.selection.mean_abs_diff.return_value = None
        result = self.service.is_pixel_duplicate(self.selection, b"thumb", [b"prev"], 5, 0.1)
        assert result is False


# ============================================================================
# FrameProcessingService check_ocr_similarity tests
# ============================================================================


class TestFrameProcessingCheckOcrSimilarity:
    def setup_method(self):
        self.service = FrameProcessingService()

    def test_empty_ocr_text(self):
        state = DedupState(kept_ocr_texts=["text"])
        result = self.service.check_ocr_similarity("", state, 0.9, 5)
        assert result is None

    def test_no_kept_texts(self):
        state = DedupState(kept_ocr_texts=[])
        result = self.service.check_ocr_similarity("text", state, 0.9, 5)
        assert result is None
