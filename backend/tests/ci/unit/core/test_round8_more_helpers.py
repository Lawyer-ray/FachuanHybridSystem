"""Tests for evidence access policy, document recognition helpers, and other pure-logic modules."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.material_classification_service import MaterialClassificationService


# ---------------------------------------------------------------------------
# MaterialClassificationService — archive methods
# ---------------------------------------------------------------------------


class TestMatchArchiveByKeywordMapping:
    """Test the keyword mapping fallback in archive classification."""

    def test_with_mapping(self):
        svc = MaterialClassificationService()
        # Mock the import of CASE_MATERIAL_KEYWORD_MAPPING
        mock_mapping = {
            "litigation": {
                "lt_7": ["起诉状", "起诉书"],
            }
        }
        with patch(
            "apps.core.services.material_classification_service.MaterialClassificationService._match_archive_by_keyword_mapping"
        ) as mock_method:
            mock_method.return_value = {
                "archive_item_code": "lt_7",
                "archive_item_name": "起诉状/上诉状/答辩状",
                "category": "case_material",
                "confidence": 0.80,
                "reason": "匹配",
            }
            result = mock_method(
                filename="test.pdf",
                source_path="/案件/起诉状/test.pdf",
                archive_category="litigation",
            )
            assert result is not None
            assert result["archive_item_code"] == "lt_7"

    def test_get_archive_item_name(self):
        svc = MaterialClassificationService()
        # Test with a mock checklist
        with patch(
            "apps.core.services.material_classification_service.MaterialClassificationService._get_archive_item_name"
        ) as mock_method:
            mock_method.return_value = "起诉状/上诉状/答辩状"
            result = mock_method("litigation", "lt_7")
            assert result == "起诉状/上诉状/答辩状"


class TestGetArchiveItemName:
    """Test _get_archive_item_name with mocked ARCHIVE_CHECKLIST."""

    def test_found(self):
        svc = MaterialClassificationService()
        mock_checklist = [{"code": "lt_7", "name": "起诉状"}]
        with patch(
            "apps.contracts.services.archive.constants.ARCHIVE_CHECKLIST",
            {"litigation": mock_checklist},
        ):
            result = svc._get_archive_item_name("litigation", "lt_7")
            assert result == "起诉状"

    def test_not_found(self):
        svc = MaterialClassificationService()
        mock_checklist = [{"code": "lt_7", "name": "起诉状"}]
        with patch(
            "apps.contracts.services.archive.constants.ARCHIVE_CHECKLIST",
            {"litigation": mock_checklist},
        ):
            result = svc._get_archive_item_name("litigation", "nonexistent")
            assert result == ""


class TestMatchArchiveByFolder:
    """Test _match_archive_by_folder with various inputs."""

    def test_no_rules_for_category(self):
        svc = MaterialClassificationService()
        result = svc._match_archive_by_folder(
            source_path="/test/path.pdf",
            archive_category="nonexistent",
        )
        assert result is None

    def test_no_match(self):
        svc = MaterialClassificationService()
        result = svc._match_archive_by_folder(
            source_path="/random/path/test.pdf",
            archive_category="litigation",
        )
        assert result is None

    def test_match_in_folder_name(self):
        svc = MaterialClassificationService()
        with patch.object(svc, "_get_archive_item_name", return_value="起诉状"):
            result = svc._match_archive_by_folder(
                source_path="/案件/起诉状/test.pdf",
                archive_category="litigation",
            )
            assert result is not None
            assert result["archive_item_code"] == "lt_7"

    def test_match_with_parent_folder_hint(self):
        svc = MaterialClassificationService()
        with patch.object(svc, "_get_archive_item_name", return_value="辩护意见"):
            result = svc._match_archive_by_folder(
                source_path="/test/path.pdf",
                archive_category="criminal",
                parent_folder_hint="辩护意见",
            )
            assert result is not None
            assert result["archive_item_code"] == "cr_12"


class TestInferCaseSideContext:
    """Test _infer_case_side with context party names."""

    def test_our_party_name_in_context(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(
            match_text="原告张三的委托书",
            context={"our_party_names": ["张三"]},
        )
        assert result == "our"

    def test_opponent_party_name_in_context(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(
            match_text="被告李四的身份证",
            context={"opponent_party_names": ["李四"]},
        )
        assert result == "opponent"

    def test_both_names_in_context(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(
            match_text="原告张三与被告李四",
            context={
                "our_party_names": ["张三"],
                "opponent_party_names": ["李四"],
            },
        )
        assert result == "unknown"
