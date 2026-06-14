"""Unit tests for contracts.services.archive.generation.document_generator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGenerateArchiveDocuments:
    """generate_archive_documents tests."""

    def test_no_template_items_returns_empty(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import generate_archive_documents

        contract = MagicMock()
        contract.case_type = "civil"
        contract.cases.select_related.return_value.prefetch_related.return_value.first.return_value = MagicMock()

        with (
            patch(
                "apps.contracts.services.archive.generation.document_generator.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.generation.document_generator.ARCHIVE_CHECKLIST",
                {"litigation": []},
            ),
        ):
            result = generate_archive_documents(contract)
            assert result == []

    def test_generates_for_template_items(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import generate_archive_documents

        contract = MagicMock()
        contract.case_type = "civil"
        case = MagicMock()
        contract.cases.select_related.return_value.prefetch_related.return_value.first.return_value = case

        checklist = [
            {"code": "c1", "name": "案卷封面", "template": "case_cover", "required": True,
             "auto_detect": None, "source": "template"},
        ]

        with (
            patch(
                "apps.contracts.services.archive.generation.document_generator.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.generation.document_generator.ARCHIVE_CHECKLIST",
                {"litigation": checklist},
            ),
            patch(
                "apps.contracts.services.archive.generation.document_generator._generate_single_document",
                return_value={"template_subtype": "case_cover", "filename": "test.docx", "error": None},
            ),
        ):
            result = generate_archive_documents(contract, case=case)
            assert len(result) == 1
            assert result[0]["template_subtype"] == "case_cover"


class TestGenerateSingleArchiveDocument:
    """generate_single_archive_document tests."""

    def test_unknown_code_returns_error(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import generate_single_archive_document

        contract = MagicMock()
        contract.case_type = "civil"

        with (
            patch(
                "apps.contracts.services.archive.generation.document_generator.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.generation.document_generator.ARCHIVE_CHECKLIST",
                {"litigation": []},
            ),
        ):
            result = generate_single_archive_document(contract, archive_item_code="nonexistent")
            assert result["error"] is not None
            assert "未找到检查清单项" in result["error"]

    def test_no_template_returns_error(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import generate_single_archive_document

        contract = MagicMock()
        contract.case_type = "civil"
        checklist = [
            {"code": "c1", "name": "正本", "template": None, "required": True,
             "auto_detect": None, "source": "contract"},
        ]

        with (
            patch(
                "apps.contracts.services.archive.generation.document_generator.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.generation.document_generator.ARCHIVE_CHECKLIST",
                {"litigation": checklist},
            ),
        ):
            result = generate_single_archive_document(contract, archive_item_code="c1")
            assert result["error"] is not None
            assert "不支持模板生成" in result["error"]


class TestApplyOverrides:
    """_apply_overrides tests."""

    def test_applies_overrides(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import _apply_overrides

        context = {"key1": "old"}
        contract = MagicMock()

        override_obj = MagicMock()
        override_obj.overrides = {"key1": "new_value", "key2": "extra"}

        with patch(
            "apps.contracts.models.archive_override.ArchivePlaceholderOverride"
        ) as mock_cls:
            mock_cls.objects.filter.return_value.first.return_value = override_obj
            _apply_overrides(context, contract, "test_subtype")
            assert context["key1"] == "new_value"
            assert context["key2"] == "extra"

    def test_none_override_skipped(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import _apply_overrides

        context = {"key1": "original"}
        contract = MagicMock()

        override_obj = MagicMock()
        override_obj.overrides = {"key1": None, "key2": ""}

        with patch(
            "apps.contracts.models.archive_override.ArchivePlaceholderOverride"
        ) as mock_cls:
            mock_cls.objects.filter.return_value.first.return_value = override_obj
            _apply_overrides(context, contract, "test_subtype")
            assert context["key1"] == "original"

    def test_no_override_object(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import _apply_overrides

        context = {"key1": "original"}
        contract = MagicMock()

        with patch(
            "apps.contracts.models.archive_override.ArchivePlaceholderOverride"
        ) as mock_cls:
            mock_cls.objects.filter.return_value.first.return_value = None
            _apply_overrides(context, contract, "test_subtype")
            assert context["key1"] == "original"


class TestGenerateFilename:
    """_generate_filename tests."""

    def test_returns_correct_format(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import _generate_filename

        contract = MagicMock()
        contract.name = "测试合同"
        item = {"name": "案卷封面"}

        with patch(
            "apps.contracts.services.archive.generation.document_generator.FilenameTemplateService"
        ) as mock_svc:
            mock_svc.render_generated_doc.return_value = "测试合同_案卷封面_V1_20260614"
            result = _generate_filename(contract, item)
            assert result.endswith(".docx")
            mock_svc.render_generated_doc.assert_called_once()

    def test_default_contract_name(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import _generate_filename

        contract = MagicMock()
        contract.name = ""
        item = {"name": "封面"}
        with patch(
            "apps.contracts.services.archive.generation.document_generator.FilenameTemplateService"
        ) as mock_svc:
            mock_svc.render_generated_doc.return_value = "result"
            _generate_filename(contract, item)
            call_kwargs = mock_svc.render_generated_doc.call_args
            assert call_kwargs[1]["case_name"] == "未命名合同"


class TestPreviewArchiveTemplate:
    """preview_archive_template tests."""

    def test_contract_not_found(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import preview_archive_template

        with patch(
            "apps.contracts.services.archive.generation.document_generator.Contract"
        ) as mock_cls:
            mock_cls.objects.filter.return_value.first.return_value = None
            result = preview_archive_template(1, "case_cover")
            assert result["success"] is False
            assert "合同不存在" in result["error"]

    def test_template_not_found(self) -> None:
        from apps.contracts.services.archive.generation.document_generator import preview_archive_template

        contract = MagicMock()
        with (
            patch(
                "apps.contracts.services.archive.generation.document_generator.Contract"
            ) as mock_cls,
            patch(
                "apps.contracts.services.archive.generation.document_generator.get_template_path",
                return_value=None,
            ),
        ):
            mock_cls.objects.filter.return_value.first.return_value = contract
            result = preview_archive_template(1, "nonexistent")
            assert result["success"] is False
            assert "模板文件不存在" in result["error"]
