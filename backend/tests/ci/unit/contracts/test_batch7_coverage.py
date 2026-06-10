"""Batch7 coverage tests for apps.contracts."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.archive.category_mapping import (
    ArchiveCategory,
    get_archive_category,
)
from apps.contracts.services.archive.constants import (
    ARCHIVE_CHECKLIST,
    ARCHIVE_FILE_NUMBERING,
    ARCHIVE_FOLDER_NAME,
    ARCHIVE_SKIP_CODES,
    ARCHIVE_SKIP_TEMPLATES,
    ARCHIVE_TEMPLATE_DOC_TYPES,
    CASE_MATERIAL_KEYWORD_MAPPING,
    CRIMINAL_CHECKLIST,
    LITIGATION_CHECKLIST,
    NON_LITIGATION_CHECKLIST,
)
from apps.contracts.services.contract.integrations.file_hash_utils import (
    compute_file_hash,
    compute_file_hash_from_bytes,
)


# ── get_archive_category ────────────────────────────────────────────────────


class TestGetArchiveCategory:
    def test_advisor_is_non_litigation(self) -> None:
        assert get_archive_category("advisor") == ArchiveCategory.NON_LITIGATION

    def test_special_is_non_litigation(self) -> None:
        assert get_archive_category("special") == ArchiveCategory.NON_LITIGATION

    def test_civil_is_litigation(self) -> None:
        assert get_archive_category("civil") == ArchiveCategory.LITIGATION

    def test_intl_is_litigation(self) -> None:
        assert get_archive_category("intl") == ArchiveCategory.LITIGATION

    def test_labor_is_litigation(self) -> None:
        assert get_archive_category("labor") == ArchiveCategory.LITIGATION

    def test_administrative_is_litigation(self) -> None:
        assert get_archive_category("administrative") == ArchiveCategory.LITIGATION

    def test_criminal_is_criminal(self) -> None:
        assert get_archive_category("criminal") == ArchiveCategory.CRIMINAL

    def test_unknown_defaults_to_litigation(self) -> None:
        assert get_archive_category("unknown_type") == ArchiveCategory.LITIGATION

    def test_empty_string_defaults_to_litigation(self) -> None:
        assert get_archive_category("") == ArchiveCategory.LITIGATION


# ── Archive constants ───────────────────────────────────────────────────────


class TestArchiveConstants:
    def test_non_litigation_checklist_count(self) -> None:
        assert len(NON_LITIGATION_CHECKLIST) == 12

    def test_litigation_checklist_count(self) -> None:
        assert len(LITIGATION_CHECKLIST) == 20

    def test_criminal_checklist_count(self) -> None:
        assert len(CRIMINAL_CHECKLIST) == 18

    def test_archive_checklist_keys(self) -> None:
        assert set(ARCHIVE_CHECKLIST.keys()) == {"non_litigation", "litigation", "criminal"}

    def test_archive_folder_name(self) -> None:
        assert ARCHIVE_FOLDER_NAME == "归档文件夹"

    def test_archive_template_doc_types(self) -> None:
        assert "case_cover" in ARCHIVE_TEMPLATE_DOC_TYPES
        assert "closing_archive_register" in ARCHIVE_TEMPLATE_DOC_TYPES
        assert "inner_catalog" in ARCHIVE_TEMPLATE_DOC_TYPES

    def test_archive_skip_codes_contain_expected(self) -> None:
        assert "nl_1" in ARCHIVE_SKIP_CODES
        assert "lt_1" in ARCHIVE_SKIP_CODES
        assert "cr_1" in ARCHIVE_SKIP_CODES

    def test_archive_skip_templates(self) -> None:
        assert "case_cover" in ARCHIVE_SKIP_TEMPLATES
        assert "closing_archive_register" in ARCHIVE_SKIP_TEMPLATES
        assert "inner_catalog" in ARCHIVE_SKIP_TEMPLATES

    def test_file_numbering_keys(self) -> None:
        assert 1 in ARCHIVE_FILE_NUMBERING
        assert 2 in ARCHIVE_FILE_NUMBERING
        assert 3 in ARCHIVE_FILE_NUMBERING
        assert 4 in ARCHIVE_FILE_NUMBERING

    def test_checklist_items_have_required_fields(self) -> None:
        for checklist in ARCHIVE_CHECKLIST.values():
            for item in checklist:
                assert "code" in item
                assert "name" in item
                assert "required" in item
                assert "source" in item

    def test_keyword_mapping_has_all_categories(self) -> None:
        assert "non_litigation" in CASE_MATERIAL_KEYWORD_MAPPING
        assert "litigation" in CASE_MATERIAL_KEYWORD_MAPPING
        assert "criminal" in CASE_MATERIAL_KEYWORD_MAPPING


# ── file_hash_utils ─────────────────────────────────────────────────────────


class TestFileHashUtils:
    def test_compute_hash_from_bytes(self) -> None:
        data = b"hello world"
        h = compute_file_hash_from_bytes(data)
        assert len(h) == 64  # SHA-256 hex digest length
        assert h != ""

    def test_compute_hash_consistency(self) -> None:
        data = b"test data"
        assert compute_file_hash_from_bytes(data) == compute_file_hash_from_bytes(data)

    def test_compute_hash_different_data(self) -> None:
        assert compute_file_hash_from_bytes(b"a") != compute_file_hash_from_bytes(b"b")

    def test_compute_hash_empty_bytes(self) -> None:
        h = compute_file_hash_from_bytes(b"")
        assert len(h) == 64

    def test_compute_file_hash_nonexistent(self) -> None:
        result = compute_file_hash(Path("/nonexistent/file.txt"))
        assert result == ""

    def test_compute_file_hash_real_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        result = compute_file_hash(f)
        assert len(result) == 64
        assert result == compute_file_hash_from_bytes(b"hello")


# ── contracts validators ────────────────────────────────────────────────────


from apps.contracts.domain.validators import (
    APPLICABLE_TYPES,
    normalize_representation_stages,
)


class TestContractValidators:
    def test_applicable_types_contains_expected(self) -> None:
        from apps.core.models.enums import CaseType

        assert CaseType.CIVIL in APPLICABLE_TYPES
        assert CaseType.CRIMINAL in APPLICABLE_TYPES

    def test_normalize_stages_empty(self) -> None:
        result = normalize_representation_stages("civil", [])
        assert result == []

    def test_normalize_stages_none_case_type(self) -> None:
        result = normalize_representation_stages(None, ["first_trial"])
        assert result == []

    def test_normalize_stages_non_applicable_type(self) -> None:
        result = normalize_representation_stages("special", ["first_trial"])
        assert result == []

    def test_normalize_stages_strict_raises_for_non_applicable(self) -> None:
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            normalize_representation_stages("special", ["first_trial"], strict=True)

    def test_normalize_stages_strict_empty_stages(self) -> None:
        result = normalize_representation_stages("special", [], strict=True)
        assert result == []


# ── supervision card extractor ──────────────────────────────────────────────


from apps.contracts.services.archive.supervision_card_extractor import (
    SupervisionCardExtractor,
    _SUPERVISION_CARD_KEYWORDS,
)


class TestSupervisionCardExtractor:
    def test_keywords_not_empty(self) -> None:
        assert len(_SUPERVISION_CARD_KEYWORDS) > 0

    def test_keywords_contain_expected(self) -> None:
        assert "监督卡" in _SUPERVISION_CARD_KEYWORDS
        assert "服务质量" in _SUPERVISION_CARD_KEYWORDS

    def test_resolve_file_path_absolute_nonexistent(self) -> None:
        extractor = SupervisionCardExtractor()
        result = extractor._resolve_file_path("/nonexistent/path/file.pdf")
        assert result is None

    def test_extract_page_invalid_number(self) -> None:
        extractor = SupervisionCardExtractor()
        import tempfile
        import fitz

        doc = fitz.open()
        doc.insert_page(0)
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        doc.save(tmp.name)
        doc.close()
        result = extractor._extract_page(Path(tmp.name), 0)
        assert result is None
        import os
        os.unlink(tmp.name)


# ── learning service extract_keywords ───────────────────────────────────────


from apps.contracts.services.archive.learning_service import (
    extract_keywords,
    _contains_document_keyword,
    _strip_non_keyword_parts,
    _is_non_keyword_attachment,
)


class TestLearningServiceKeywords:
    def test_extract_keywords_simple(self) -> None:
        keywords = extract_keywords("案卷封面.pdf")
        assert isinstance(keywords, list)

    def test_extract_keywords_empty_filename(self) -> None:
        keywords = extract_keywords("")
        assert keywords == []

    def test_contains_document_keyword_true(self) -> None:
        assert _contains_document_keyword("起诉状") is True
        assert _contains_document_keyword("某某起诉状副本") is True

    def test_contains_document_keyword_false(self) -> None:
        assert _contains_document_keyword("张福裕案件") is False

    def test_strip_non_keyword_parts_exact_match(self) -> None:
        assert _strip_non_keyword_parts("起诉状") == "起诉状"

    def test_strip_non_keyword_parts_with_prefix(self) -> None:
        result = _strip_non_keyword_parts("张三起诉状")
        assert result == "起诉状"

    def test_is_non_keyword_attachment_empty(self) -> None:
        assert _is_non_keyword_attachment("") is False

    def test_is_non_keyword_attachment_with_keyword(self) -> None:
        assert _is_non_keyword_attachment("起诉状") is False

    def test_is_non_keyword_attachment_name(self) -> None:
        assert _is_non_keyword_attachment("张三") is True


# ── override service ────────────────────────────────────────────────────────


from apps.contracts.services.archive import override_service


class TestOverrideService:
    def test_get_override_returns_none_for_missing(self, db: None) -> None:
        result = override_service.get_override(99999, "case_cover")
        assert result is None

    def test_save_and_get_override(self, db: None, contract: object) -> None:
        obj, created = override_service.save_override(
            contract_id=contract.id,
            template_subtype="case_cover",
            overrides={"field1": "value1"},
        )
        assert created is True
        result = override_service.get_override(contract.id, "case_cover")
        assert result is not None
        assert result.overrides == {"field1": "value1"}

    def test_delete_override(self, db: None, contract: object) -> None:
        override_service.save_override(
            contract_id=contract.id,
            template_subtype="case_cover",
            overrides={"key": "val"},
        )
        count = override_service.delete_override(contract.id, "case_cover")
        assert count == 1
        assert override_service.get_override(contract.id, "case_cover") is None


# ── contract subdir path resolver ───────────────────────────────────────────


from apps.contracts.services.folder.contract_subdir_path_resolver import (
    ContractSubdirPathResolver,
)


class TestContractSubdirPathResolver:
    def test_resolve_unknown_key_returns_none(self) -> None:
        resolver = ContractSubdirPathResolver(template_binding_service=None)
        result = resolver.resolve(case_type="civil", subdir_key="unknown")
        assert result is None

    def test_resolve_none_service_returns_none(self) -> None:
        resolver = ContractSubdirPathResolver(template_binding_service=None)
        result = resolver.resolve(case_type="civil", subdir_key="contract_documents")
        assert result is None

    def test_subdir_key_mapping(self) -> None:
        mapping = ContractSubdirPathResolver.SUBDIR_KEY_TO_CONTRACT_SUB_TYPE
        assert mapping["contract_documents"] == "contract"
        assert mapping["supplementary_agreements"] == "supplementary_agreement"
