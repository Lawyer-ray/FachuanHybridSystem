"""Tests for refactored pure functions from contracts/services/."""

from __future__ import annotations

import pytest

from apps.contracts.services.archive.constants import (
    ARCHIVE_CHECKLIST,
    ARCHIVE_SKIP_CODES,
    ARCHIVE_SKIP_TEMPLATES,
    ARCHIVE_FILE_NUMBERING,
    CASE_MATERIAL_KEYWORD_MAPPING,
    ARCHIVE_SUBITEM_ORDER_RULES,
    ChecklistItem,
)


class TestArchiveChecklist:
    """Tests for ARCHIVE_CHECKLIST constants."""

    def test_has_non_litigation(self):
        assert "non_litigation" in ARCHIVE_CHECKLIST

    def test_has_litigation(self):
        assert "litigation" in ARCHIVE_CHECKLIST

    def test_has_criminal(self):
        assert "criminal" in ARCHIVE_CHECKLIST

    def test_non_litigation_items_have_code(self):
        for item in ARCHIVE_CHECKLIST["non_litigation"]:
            assert "code" in item
            assert item["code"].startswith("nl_")

    def test_litigation_items_have_code(self):
        for item in ARCHIVE_CHECKLIST["litigation"]:
            assert "code" in item
            assert item["code"].startswith("lt_")

    def test_criminal_items_have_code(self):
        for item in ARCHIVE_CHECKLIST["criminal"]:
            assert "code" in item
            assert item["code"].startswith("cr_")

    def test_all_items_have_name(self):
        for category in ARCHIVE_CHECKLIST.values():
            for item in category:
                assert "name" in item
                assert len(item["name"]) > 0

    def test_all_items_have_source(self):
        valid_sources = {"template", "contract", "case", "manual"}
        for category in ARCHIVE_CHECKLIST.values():
            for item in category:
                assert item["source"] in valid_sources


class TestArchiveSkipCodes:
    """Tests for ARCHIVE_SKIP_CODES constants."""

    def test_contains_nl_codes(self):
        assert "nl_1" in ARCHIVE_SKIP_CODES
        assert "nl_2" in ARCHIVE_SKIP_CODES
        assert "nl_3" in ARCHIVE_SKIP_CODES

    def test_contains_lt_codes(self):
        assert "lt_1" in ARCHIVE_SKIP_CODES
        assert "lt_2" in ARCHIVE_SKIP_CODES
        assert "lt_3" in ARCHIVE_SKIP_CODES

    def test_contains_cr_codes(self):
        assert "cr_1" in ARCHIVE_SKIP_CODES
        assert "cr_2" in ARCHIVE_SKIP_CODES
        assert "cr_3" in ARCHIVE_SKIP_CODES

    def test_is_set(self):
        assert isinstance(ARCHIVE_SKIP_CODES, set)


class TestArchiveSkipTemplates:
    """Tests for ARCHIVE_SKIP_TEMPLATES constants."""

    def test_contains_expected_templates(self):
        assert "case_cover" in ARCHIVE_SKIP_TEMPLATES
        assert "closing_archive_register" in ARCHIVE_SKIP_TEMPLATES
        assert "inner_catalog" in ARCHIVE_SKIP_TEMPLATES

    def test_is_set(self):
        assert isinstance(ARCHIVE_SKIP_TEMPLATES, set)


class TestArchiveFileNumbering:
    """Tests for ARCHIVE_FILE_NUMBERING constants."""

    def test_has_entries(self):
        assert len(ARCHIVE_FILE_NUMBERING) > 0

    def test_keys_are_integers(self):
        for key in ARCHIVE_FILE_NUMBERING:
            assert isinstance(key, int)

    def test_values_are_tuples(self):
        for value in ARCHIVE_FILE_NUMBERING.values():
            assert isinstance(value, tuple)
            assert len(value) == 2

    def test_first_entry(self):
        code, name = ARCHIVE_FILE_NUMBERING[1]
        assert code == "case_cover"
        assert name == "案卷封面"


class TestCaseMaterialKeywordMapping:
    """Tests for CASE_MATERIAL_KEYWORD_MAPPING constants."""

    def test_has_all_categories(self):
        assert "non_litigation" in CASE_MATERIAL_KEYWORD_MAPPING
        assert "litigation" in CASE_MATERIAL_KEYWORD_MAPPING
        assert "criminal" in CASE_MATERIAL_KEYWORD_MAPPING

    def test_keywords_are_lists(self):
        for category in CASE_MATERIAL_KEYWORD_MAPPING.values():
            for code, keywords in category.items():
                assert isinstance(keywords, list)

    def test_keywords_are_strings(self):
        for category in CASE_MATERIAL_KEYWORD_MAPPING.values():
            for code, keywords in category.items():
                for kw in keywords:
                    assert isinstance(kw, str)

    def test_litigation_has_common_codes(self):
        lt_mapping = CASE_MATERIAL_KEYWORD_MAPPING["litigation"]
        assert "lt_20" in lt_mapping
        assert "lt_7" in lt_mapping
        assert "lt_17" in lt_mapping


class TestArchiveSubitemOrderRules:
    """Tests for ARCHIVE_SUBITEM_ORDER_RULES constants."""

    def test_has_entries(self):
        assert len(ARCHIVE_SUBITEM_ORDER_RULES) > 0

    def test_values_are_lists(self):
        for value in ARCHIVE_SUBITEM_ORDER_RULES.values():
            assert isinstance(value, list)

    def test_keywords_are_strings(self):
        for keywords in ARCHIVE_SUBITEM_ORDER_RULES.values():
            for kw in keywords:
                assert isinstance(kw, str)

    def test_nl_4_rule(self):
        assert "nl_4" in ARCHIVE_SUBITEM_ORDER_RULES
        assert "委托合同" in ARCHIVE_SUBITEM_ORDER_RULES["nl_4"]
