"""Extended tests for chat_records services - extraction helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.chat_records.services.extraction.extract_helpers import (
    DedupState,
    ExtractParams,
    jaccard_sets,
    safe_float,
    safe_int,
    shingles,
)


class TestSafeInt:
    def test_valid_int(self):
        assert safe_int(42, 0) == 42

    def test_string_int(self):
        assert safe_int("42", 0) == 42

    def test_none(self):
        assert safe_int(None, 10) == 10

    def test_invalid_string(self):
        assert safe_int("abc", 5) == 5

    def test_float_string(self):
        # int("3.14") raises ValueError, so safe_int returns default
        assert safe_int("3.14", 0) == 0

    def test_empty_string(self):
        assert safe_int("", 7) == 7


class TestSafeFloat:
    def test_valid_float(self):
        assert safe_float(3.14, 0.0) == 3.14

    def test_string_float(self):
        assert safe_float("3.14", 0.0) == 3.14

    def test_none(self):
        assert safe_float(None, 1.0) == 1.0

    def test_invalid_string(self):
        assert safe_float("abc", 2.5) == 2.5

    def test_with_lo_clamp(self):
        assert safe_float(0.5, 1.0, lo=1.0) == 1.0

    def test_with_hi_clamp(self):
        assert safe_float(2.0, 1.0, hi=1.5) == 1.5

    def test_with_both_clamps(self):
        assert safe_float(0.5, 1.0, lo=0.0, hi=1.0) == 0.5


class TestShingles:
    def test_empty(self):
        assert shingles("") == set()

    def test_none(self):
        assert shingles(None) == set()  # type: ignore[arg-type]

    def test_short_string(self):
        result = shingles("ab", n=3)
        assert result == {"ab"}

    def test_normal_string(self):
        result = shingles("abcdef", n=3)
        assert "abc" in result
        assert "bcd" in result
        assert "cde" in result
        assert "def" in result
        assert len(result) == 4

    def test_custom_n(self):
        result = shingles("abcde", n=2)
        assert "ab" in result
        assert "bc" in result
        assert len(result) == 4


class TestJaccardSets:
    def test_both_empty(self):
        assert jaccard_sets(set(), set()) == 0.0

    def test_one_empty(self):
        assert jaccard_sets({"a"}, set()) == 0.0

    def test_identical(self):
        assert jaccard_sets({"a", "b"}, {"a", "b"}) == 1.0

    def test_no_overlap(self):
        assert jaccard_sets({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        result = jaccard_sets({"a", "b"}, {"b", "c"})
        assert abs(result - 1 / 3) < 0.01


class TestExtractParams:
    def test_defaults(self):
        params = ExtractParams()
        assert params.interval_seconds == 1.0
        assert params.strategy == "interval"
        assert params.dedup_threshold == 8

    def test_from_recording(self):
        recording = MagicMock()
        recording.extract_strategy = "ocr"
        recording.extract_dedup_threshold = 10
        recording.extract_ocr_similarity_threshold = 0.95
        recording.extract_ocr_min_new_chars = 12
        params = ExtractParams.from_recording(recording, 2.0)
        assert params.interval_seconds == 2.0
        assert params.strategy == "ocr"
        assert params.interval_based is True
        assert params.dedup_threshold == 10
        assert params.ocr_similarity_threshold == 0.95
        assert params.ocr_min_new_chars == 12

    def test_from_recording_with_none_values(self):
        recording = MagicMock()
        recording.extract_strategy = None
        recording.extract_dedup_threshold = None
        recording.extract_ocr_similarity_threshold = None
        recording.extract_ocr_min_new_chars = None
        params = ExtractParams.from_recording(recording, None)
        assert params.strategy == "interval"
        assert params.dedup_threshold == 8

    def test_from_recording_interval_based_false(self):
        recording = MagicMock()
        recording.extract_strategy = "manual"
        recording.extract_dedup_threshold = None
        recording.extract_ocr_similarity_threshold = None
        recording.extract_ocr_min_new_chars = None
        params = ExtractParams.from_recording(recording, 1.0)
        assert params.interval_based is False


class TestDedupState:
    def test_defaults(self):
        state = DedupState()
        assert state.existing_sha256 == set()
        assert state.seen_sha256 == set()
        assert state.created_count == 0
        assert state.processed_count == 0
        assert state.ocr_calls == 0
        assert state.ocr_disabled is False
