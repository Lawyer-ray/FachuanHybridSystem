"""Comprehensive tests for extract_helpers, party_formatter, and folder_binding_base coverage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ===========================================================================
# extract_helpers tests
# ===========================================================================
class TestSafeInt:
    def test_valid_int(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_int
        assert safe_int(42, 0) == 42

    def test_string_int(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_int
        assert safe_int("100", 0) == 100

    def test_none(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_int
        assert safe_int(None, 10) == 10

    def test_invalid(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_int
        assert safe_int("abc", 5) == 5

    def test_float_string(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_int
        # int("3.14") raises ValueError, so returns default
        assert safe_int("3.14", 0) == 0


class TestSafeFloat:
    def test_valid_float(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_float
        assert safe_float(3.14, 0.0) == 3.14

    def test_string_float(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_float
        assert safe_float("2.5", 0.0) == 2.5

    def test_none(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_float
        assert safe_float(None, 1.0) == 1.0

    def test_invalid(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_float
        assert safe_float("abc", 0.5) == 0.5

    def test_clamp_low(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_float
        assert safe_float(0.01, 1.0, lo=0.1) == 0.1

    def test_clamp_high(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_float
        assert safe_float(2.0, 1.0, hi=1.5) == 1.5

    def test_clamp_both(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_float
        assert safe_float(5.0, 1.0, lo=0.0, hi=1.0) == 1.0

    def test_no_clamp(self):
        from apps.chat_records.services.extraction.extract_helpers import safe_float
        assert safe_float(0.5, 1.0, lo=0.0, hi=1.0) == 0.5


class TestShingles:
    def test_basic(self):
        from apps.chat_records.services.extraction.extract_helpers import shingles
        result = shingles("abcde", n=3)
        assert result == {"abc", "bcd", "cde"}

    def test_empty(self):
        from apps.chat_records.services.extraction.extract_helpers import shingles
        assert shingles("") == set()

    def test_none(self):
        from apps.chat_records.services.extraction.extract_helpers import shingles
        assert shingles(None) == set()  # type: ignore[arg-type]

    def test_shorter_than_n(self):
        from apps.chat_records.services.extraction.extract_helpers import shingles
        result = shingles("ab", n=3)
        assert result == {"ab"}

    def test_exact_length(self):
        from apps.chat_records.services.extraction.extract_helpers import shingles
        result = shingles("abc", n=3)
        assert result == {"abc"}


class TestJaccardSets:
    def test_identical(self):
        from apps.chat_records.services.extraction.extract_helpers import jaccard_sets
        assert jaccard_sets({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint(self):
        from apps.chat_records.services.extraction.extract_helpers import jaccard_sets
        assert jaccard_sets({"a"}, {"b"}) == 0.0

    def test_partial(self):
        from apps.chat_records.services.extraction.extract_helpers import jaccard_sets
        result = jaccard_sets({"a", "b"}, {"b", "c"})
        assert result == pytest.approx(1 / 3)

    def test_empty_sets(self):
        from apps.chat_records.services.extraction.extract_helpers import jaccard_sets
        assert jaccard_sets(set(), set()) == 0.0

    def test_one_empty(self):
        from apps.chat_records.services.extraction.extract_helpers import jaccard_sets
        assert jaccard_sets({"a"}, set()) == 0.0


class TestExtractParams:
    def test_defaults(self):
        from apps.chat_records.services.extraction.extract_helpers import ExtractParams
        params = ExtractParams()
        assert params.interval_seconds == 1.0
        assert params.strategy == "interval"
        assert params.interval_based is True

    def test_from_recording(self):
        from apps.chat_records.services.extraction.extract_helpers import ExtractParams
        recording = SimpleNamespace(
            extract_strategy="keyframe",
            extract_dedup_threshold="10",
            extract_ocr_similarity_threshold="0.85",
            extract_ocr_min_new_chars="5",
        )
        params = ExtractParams.from_recording(recording, 2.0)
        assert params.interval_seconds == 2.0
        assert params.strategy == "keyframe"
        assert params.interval_based is False
        assert params.dedup_threshold == 10

    def test_from_recording_defaults(self):
        from apps.chat_records.services.extraction.extract_helpers import ExtractParams
        recording = SimpleNamespace()
        params = ExtractParams.from_recording(recording, 0)
        assert params.interval_seconds == 1.0  # fallback
        assert params.strategy == "interval"
        assert params.interval_based is True

    def test_from_recording_ocr_strategy(self):
        from apps.chat_records.services.extraction.extract_helpers import ExtractParams
        recording = SimpleNamespace(
            extract_strategy="ocr",
            extract_dedup_threshold=None,
            extract_ocr_similarity_threshold=None,
            extract_ocr_min_new_chars=None,
        )
        params = ExtractParams.from_recording(recording, 1.0)
        assert params.interval_based is True


class TestDedupState:
    def test_defaults(self):
        from apps.chat_records.services.extraction.extract_helpers import DedupState
        state = DedupState()
        assert state.existing_sha256 == set()
        assert state.seen_sha256 == set()
        assert state.created_count == 0
        assert state.ocr_disabled is False


# ===========================================================================
# PartyFormatter tests
# ===========================================================================
class TestPartyFormatter:
    def _get_formatter(self):
        from apps.documents.services.placeholders.litigation.party_formatter import PartyFormatter
        return PartyFormatter()

    def test_is_natural_person_true(self):
        formatter = self._get_formatter()
        party = SimpleNamespace(client=SimpleNamespace(client_type="natural"))
        assert formatter.is_natural_person(party) is True

    def test_is_natural_person_false(self):
        formatter = self._get_formatter()
        party = SimpleNamespace(client=SimpleNamespace(client_type="legal"))
        assert formatter.is_natural_person(party) is False

    def test_is_natural_person_no_client(self):
        formatter = self._get_formatter()
        party = SimpleNamespace(client=None)
        assert formatter.is_natural_person(party) is False

    def test_is_natural_person_from_dict_true(self):
        formatter = self._get_formatter()
        assert formatter.is_natural_person_from_dict({"client_type": "natural"}) is True

    def test_is_natural_person_from_dict_false(self):
        formatter = self._get_formatter()
        assert formatter.is_natural_person_from_dict({"client_type": "legal"}) is False

    def test_is_natural_person_from_dict_empty(self):
        formatter = self._get_formatter()
        assert formatter.is_natural_person_from_dict({}) is False

    def test_is_natural_person_from_dict_none(self):
        formatter = self._get_formatter()
        assert formatter.is_natural_person_from_dict(None) is False  # type: ignore[arg-type]

    def test_get_role_label_single(self):
        formatter = self._get_formatter()
        assert formatter.get_role_label("原告", 0, 1) == "原告"

    def test_get_role_label_multiple_first(self):
        formatter = self._get_formatter()
        assert formatter.get_role_label("原告", 0, 3) == "原告一"

    def test_get_role_label_multiple_second(self):
        formatter = self._get_formatter()
        assert formatter.get_role_label("原告", 1, 3) == "原告二"

    def test_get_role_label_overflow(self):
        formatter = self._get_formatter()
        assert formatter.get_role_label("原告", 10, 15) == "原告11"


# ===========================================================================
# folder_binding_base format_path_for_display tests
# ===========================================================================
class TestFormatPathForDisplay:
    def test_short_path(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        assert svc.format_path_for_display("/short") == "/short"

    def test_empty_path(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        assert svc.format_path_for_display("") == ""

    def test_long_path(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        long_path = "/a" * 100
        result = svc.format_path_for_display(long_path, max_length=50)
        assert len(result) <= 50
        assert "..." in result

    def test_exact_max_length(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        path = "a" * 50
        assert svc.format_path_for_display(path, max_length=50) == path


class TestIsCloudStorage:
    def test_local(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        binding = SimpleNamespace(storage_type="local", storage_account=None)
        assert svc._is_cloud_storage(binding) is False

    def test_cloud_with_account(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        binding = SimpleNamespace(storage_type="s3", storage_account="bucket1")
        assert svc._is_cloud_storage(binding) is True

    def test_cloud_no_account(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        binding = SimpleNamespace(storage_type="s3", storage_account=None)
        assert svc._is_cloud_storage(binding) is False

    def test_no_storage_type_attr(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        binding = SimpleNamespace()
        assert svc._is_cloud_storage(binding) is False


class TestIsBrowsablePath:
    def test_normal_path(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        svc._path_validator = MagicMock()
        svc._path_validator.is_network_path.return_value = False
        is_browsable, msg = svc.is_browsable_path("/local/path")
        assert is_browsable is True
        assert msg is None

    def test_network_path(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        svc = BaseFolderBindingService.__new__(BaseFolderBindingService)
        svc._path_validator = MagicMock()
        svc._path_validator.is_network_path.return_value = True
        is_browsable, msg = svc.is_browsable_path("//server/share")
        assert is_browsable is False
        assert "网络路径" in (msg or "")
