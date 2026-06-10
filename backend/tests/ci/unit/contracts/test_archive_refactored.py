"""Tests for refactored pure functions from contracts/services/archive/."""

from __future__ import annotations

import pytest

from apps.contracts.services.archive.category_mapping import (
    ArchiveCategory,
    get_archive_category,
)


class TestArchiveCategory:
    """Tests for ArchiveCategory enum."""

    def test_non_litigation_value(self):
        assert ArchiveCategory.NON_LITIGATION == "non_litigation"

    def test_litigation_value(self):
        assert ArchiveCategory.LITIGATION == "litigation"

    def test_criminal_value(self):
        assert ArchiveCategory.CRIMINAL == "criminal"

    def test_non_litigation_label(self):
        assert ArchiveCategory.NON_LITIGATION.label == "法律顾问及非诉事务"

    def test_litigation_label(self):
        assert ArchiveCategory.LITIGATION.label == "诉讼/仲裁"

    def test_criminal_label(self):
        assert ArchiveCategory.CRIMINAL.label == "刑事案件"


class TestGetArchiveCategory:
    """Tests for get_archive_category pure function."""

    def test_advisor(self):
        assert get_archive_category("advisor") == "non_litigation"

    def test_special(self):
        assert get_archive_category("special") == "non_litigation"

    def test_civil(self):
        assert get_archive_category("civil") == "litigation"

    def test_intl(self):
        assert get_archive_category("intl") == "litigation"

    def test_labor(self):
        assert get_archive_category("labor") == "litigation"

    def test_administrative(self):
        assert get_archive_category("administrative") == "litigation"

    def test_criminal(self):
        assert get_archive_category("criminal") == "criminal"

    def test_unknown_defaults_to_litigation(self):
        assert get_archive_category("unknown") == "litigation"

    def test_empty_string_defaults_to_litigation(self):
        assert get_archive_category("") == "litigation"

    def test_none_defaults_to_litigation(self):
        assert get_archive_category(None) == "litigation"
