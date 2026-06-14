"""Unit tests for contracts.services.archive.learning_service (additional coverage)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestArchiveLearningServiceInit:
    """Test class instantiation."""

    def test_instantiation(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        svc = ArchiveLearningService()
        assert svc is not None


class TestArchiveLearningServiceGenerateCodeFile:
    """_generate_code_file tests."""

    def test_empty_grouped(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        svc = ArchiveLearningService()
        result = svc._generate_code_file({})
        assert "LEARNED_FILENAME_KEYWORD_TO_ARCHIVE_CODE" in result
        assert "= {}" in result

    def test_with_rules(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        svc = ArchiveLearningService()
        grouped = {
            "litigation": {
                "lt_1": ["起诉状", "答辩状"],
                "lt_2": ["判决书"],
            }
        }
        result = svc._generate_code_file(grouped)
        assert "litigation" in result
        assert "lt_1" in result
        assert "起诉状" in result
        assert "答辩状" in result
        assert "判决书" in result
        assert "lt_2" in result


class TestArchiveLearningServiceLearnFromArchivedMaterials:
    """learn_from_archived_materials tests."""

    def test_no_materials(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        svc = ArchiveLearningService()
        with patch(
            "apps.contracts.services.archive.learning_service.FinalizedMaterial"
        ) as mock_fm:
            mock_fm.objects.filter.return_value.select_related.return_value = []
            result = svc.learn_from_archived_materials()
            assert result["learned"] == 0
            assert result["skipped"] == 0

    def test_material_already_classified_correctly_skipped(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        svc = ArchiveLearningService()
        material = MagicMock()
        material.id = 1
        material.contract.case_type = "civil"
        material.original_filename = "起诉状.pdf"
        material.archive_item_code = "lt_1"
        material.file_path = "/path/起诉状.pdf"

        with (
            patch(
                "apps.contracts.services.archive.learning_service.FinalizedMaterial"
            ) as mock_fm,
            patch(
                "apps.contracts.services.archive.learning_service.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.learning_service.classify_archive_material",
                return_value={"archive_item_code": "lt_1"},
            ),
        ):
            mock_fm.objects.filter.return_value.select_related.return_value = [material]
            result = svc.learn_from_archived_materials()
            assert result["skipped"] >= 1

    def test_material_needs_learning(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        svc = ArchiveLearningService()
        material = MagicMock()
        material.id = 2
        material.contract.case_type = "civil"
        material.original_filename = "起诉状.pdf"
        material.archive_item_code = "lt_2"
        material.file_path = "/path/起诉状.pdf"

        with (
            patch(
                "apps.contracts.services.archive.learning_service.FinalizedMaterial"
            ) as mock_fm,
            patch(
                "apps.contracts.services.archive.learning_service.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.learning_service.classify_archive_material",
                return_value={"archive_item_code": "lt_wrong"},
            ),
            patch(
                "apps.contracts.services.archive.learning_service.ArchiveClassificationRule"
            ) as mock_rule,
        ):
            mock_fm.objects.filter.return_value.select_related.return_value = [material]
            mock_rule.objects.get_or_create.return_value = (MagicMock(), True)
            result = svc.learn_from_archived_materials()
            assert result["learned"] >= 1

    def test_ambiguous_keywords_detected(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        svc = ArchiveLearningService()
        mat1 = MagicMock()
        mat1.id = 10
        mat1.contract.case_type = "civil"
        mat1.original_filename = "合同正本.pdf"
        mat1.archive_item_code = "lt_a"
        mat1.file_path = "/a/合同正本.pdf"

        mat2 = MagicMock()
        mat2.id = 11
        mat2.contract.case_type = "civil"
        mat2.original_filename = "合同正本.pdf"
        mat2.archive_item_code = "lt_b"
        mat2.file_path = "/b/合同正本.pdf"

        materials = [mat1, mat2]

        with (
            patch(
                "apps.contracts.services.archive.learning_service.FinalizedMaterial"
            ) as mock_fm,
            patch(
                "apps.contracts.services.archive.learning_service.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.learning_service.classify_archive_material",
                return_value={"archive_item_code": "lt_wrong"},
            ),
        ):
            mock_fm.objects.filter.return_value.select_related.return_value = materials
            result = svc.learn_from_archived_materials()
            assert result["ambiguous"] >= 1


class TestContainsDocumentKeyword:
    """_contains_document_keyword tests."""

    def test_with_keyword(self) -> None:
        from apps.contracts.services.archive.learning_service import _contains_document_keyword

        assert _contains_document_keyword("起诉状") is True

    def test_without_keyword(self) -> None:
        from apps.contracts.services.archive.learning_service import _contains_document_keyword

        assert _contains_document_keyword("张福裕案件") is False

    def test_empty_string(self) -> None:
        from apps.contracts.services.archive.learning_service import _contains_document_keyword

        assert _contains_document_keyword("") is False


class TestIsNonKeywordAttachment:
    """_is_non_keyword_attachment tests."""

    def test_empty_returns_false(self) -> None:
        from apps.contracts.services.archive.learning_service import _is_non_keyword_attachment

        assert _is_non_keyword_attachment("") is False

    def test_pure_symbols_returns_false(self) -> None:
        from apps.contracts.services.archive.learning_service import _is_non_keyword_attachment

        assert _is_non_keyword_attachment("abc123") is False

    def test_keyword_overlap_returns_false(self) -> None:
        from apps.contracts.services.archive.learning_service import _is_non_keyword_attachment

        assert _is_non_keyword_attachment("起诉状") is False

    def test_non_keyword_chinese_returns_true(self) -> None:
        from apps.contracts.services.archive.learning_service import _is_non_keyword_attachment

        assert _is_non_keyword_attachment("张三") is True


class TestStripNonKeywordParts:
    """_strip_non_keyword_parts tests."""

    def test_exact_whitelist_match(self) -> None:
        from apps.contracts.services.archive.learning_service import _strip_non_keyword_parts

        assert _strip_non_keyword_parts("起诉状") == "起诉状"

    def test_prefix_stripped(self) -> None:
        from apps.contracts.services.archive.learning_service import _strip_non_keyword_parts

        result = _strip_non_keyword_parts("张三起诉状")
        assert result == "起诉状"

    def test_no_non_keyword_prefix_kept(self) -> None:
        from apps.contracts.services.archive.learning_service import _strip_non_keyword_parts

        # "缴纳保全费" is a non-keyword prefix; "通知" is the longest match keyword
        result = _strip_non_keyword_parts("缴纳保全费通知书")
        assert result == "通知"

    def test_company_prefix_stripped(self) -> None:
        from apps.contracts.services.archive.learning_service import _strip_non_keyword_parts

        result = _strip_non_keyword_parts("佛山市某某公司起诉状")
        assert result == "起诉状"
