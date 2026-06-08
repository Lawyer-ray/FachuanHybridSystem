"""文档服务测试 — 归档占位符、填充服务、分析服务。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.documents.services.placeholders.archive import (
    _ArchiveMaterialsRichText,
    unwrap_archive_rich_text,
)


class TestArchiveMaterialsRichText:
    """_ArchiveMaterialsRichText 可测试逻辑。"""

    def test_add_text(self):
        rt = _ArchiveMaterialsRichText()
        rt.add("line1")
        assert rt.plain_text == "line1"

    def test_add_break(self):
        rt = _ArchiveMaterialsRichText()
        rt.add("line1")
        rt.add_break()
        rt.add("line2")
        assert rt.plain_text == "line1\nline2"

    def test_plain_text_empty(self):
        rt = _ArchiveMaterialsRichText()
        assert rt.plain_text == ""

    def test_str_returns_plain_text(self):
        rt = _ArchiveMaterialsRichText()
        rt.add("test")
        assert str(rt) == "test"

    def test_to_listing(self):
        rt = _ArchiveMaterialsRichText()
        rt.add("test content")
        # to_listing imports Listing internally, just verify it doesn't error
        try:
            result = rt.to_listing()
            # If docxtpl is available, result should be a Listing
            assert result is not None
        except ImportError:
            # docxtpl might not be installed in test env
            pass


class TestUnwrapArchiveRichText:
    """unwrap_archive_rich_text 测试。"""

    def test_unwrap_converts_rich_text(self):
        rt = _ArchiveMaterialsRichText()
        rt.add("test")
        context = {"key": rt, "other": "plain"}
        result = unwrap_archive_rich_text(context)
        assert result["other"] == "plain"
        # key should now be a Listing, not _ArchiveMaterialsRichText
        assert not isinstance(result["key"], _ArchiveMaterialsRichText)

    def test_unwrap_preserves_non_rich_text(self):
        context = {"str_key": "value", "int_key": 42}
        result = unwrap_archive_rich_text(context)
        assert result["str_key"] == "value"
        assert result["int_key"] == 42

    def test_unwrap_empty_context(self):
        result = unwrap_archive_rich_text({})
        assert result == {}


class TestFillingServiceHelpers:
    """FillingService 数据类测试。"""

    def test_fill_preview_item(self):
        from apps.documents.services.external_template.filling_service import FillPreviewItem

        item = FillPreviewItem(
            position_description="段落1",
            semantic_label="当事人名称",
            fill_value="张某",
            value_source="auto",
            fill_type="text",
            mapping_id=1,
        )
        assert item.fill_value == "张某"
        assert item.value_source == "auto"

    def test_fill_report(self):
        from apps.documents.services.external_template.filling_service import FillReport

        report = FillReport(
            total_fields=10,
            filled_count=8,
            skipped_count=2,
            manual_needed=["field1"],
            errors=[],
        )
        assert report.total_fields == 10
        assert report.filled_count == 8
        assert len(report.manual_needed) == 1


class TestAnalysisServiceHelpers:
    """AnalysisService 常量和配置测试。"""

    def test_max_file_size(self):
        from apps.documents.services.external_template.analysis_service import AnalysisService

        assert AnalysisService.MAX_FILE_SIZE == 20 * 1024 * 1024


class TestCaseCommonPlaceholderService:
    """CaseCommonPlaceholderService 元数据测试。"""

    def test_placeholder_keys_not_empty(self):
        from apps.documents.services.placeholders.case.case_common_service import CaseCommonPlaceholderService

        assert len(CaseCommonPlaceholderService.placeholder_keys) > 0

    def test_placeholder_metadata_keys_match(self):
        from apps.documents.services.placeholders.case.case_common_service import CaseCommonPlaceholderService

        for key in CaseCommonPlaceholderService.placeholder_keys:
            assert key in CaseCommonPlaceholderService.placeholder_metadata

    def test_metadata_has_required_fields(self):
        from apps.documents.services.placeholders.case.case_common_service import CaseCommonPlaceholderService

        for key, meta in CaseCommonPlaceholderService.placeholder_metadata.items():
            assert "display_name" in meta
            assert "description" in meta
            assert "example_value" in meta

    def test_service_name(self):
        from apps.documents.services.placeholders.case.case_common_service import CaseCommonPlaceholderService

        assert CaseCommonPlaceholderService.name == "case_common_placeholder_service"

    def test_service_category(self):
        from apps.documents.services.placeholders.case.case_common_service import CaseCommonPlaceholderService

        assert CaseCommonPlaceholderService.category == "case"


class TestArchivePlaceholderService:
    """ArchivePlaceholderService 元数据测试。"""

    def test_placeholder_keys_not_empty(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        assert len(ArchivePlaceholderService.placeholder_keys) > 0

    def test_service_name(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        assert ArchivePlaceholderService.name == "archive_placeholder_service"

    def test_service_category(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        assert ArchivePlaceholderService.category == "archive"

    def test_metadata_has_required_fields(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        for key in ArchivePlaceholderService.placeholder_keys:
            if key in ArchivePlaceholderService.placeholder_metadata:
                meta = ArchivePlaceholderService.placeholder_metadata[key]
                assert "display_name" in meta


class TestFolderGenerationServiceHelpers:
    """FolderGenerationService 数据类测试。"""

    def test_document_placement(self):
        from apps.documents.services.generation.folder_generation_service import DocumentPlacement

        mock_template = MagicMock()
        placement = DocumentPlacement(
            document_template=mock_template,
            folder_path="2-案件材料/1-起诉材料",
            file_name="起诉状.docx",
        )
        assert placement.folder_path == "2-案件材料/1-起诉材料"
        assert placement.file_name == "起诉状.docx"


class TestAuthorizationMaterialGenerationServiceHelpers:
    """AuthorizationMaterialGenerationService 测试。"""

    def test_template_name_constants(self):
        from apps.documents.services.generation.authorization_material_generation_service import (
            TEMPLATE_NAME_AUTHORITY_LETTER,
            TEMPLATE_NAME_LEGAL_REP_CERT,
            TEMPLATE_NAME_POWER_OF_ATTORNEY,
        )

        assert TEMPLATE_NAME_AUTHORITY_LETTER == "所函"
        assert TEMPLATE_NAME_LEGAL_REP_CERT == "法定代表人身份证明书"
        assert TEMPLATE_NAME_POWER_OF_ATTORNEY == "授权委托书"

    def test_service_requires_injection(self):
        from apps.documents.services.generation.authorization_material_generation_service import (
            AuthorizationMaterialGenerationService,
        )

        svc = AuthorizationMaterialGenerationService()
        with pytest.raises(RuntimeError):
            _ = svc.case_service

    def test_client_service_requires_injection(self):
        from apps.documents.services.generation.authorization_material_generation_service import (
            AuthorizationMaterialGenerationService,
        )

        svc = AuthorizationMaterialGenerationService()
        with pytest.raises(RuntimeError):
            _ = svc.client_service

    def test_document_service_requires_injection(self):
        from apps.documents.services.generation.authorization_material_generation_service import (
            AuthorizationMaterialGenerationService,
        )

        svc = AuthorizationMaterialGenerationService()
        with pytest.raises(RuntimeError):
            _ = svc.document_service

    def test_service_with_injection(self):
        from apps.documents.services.generation.authorization_material_generation_service import (
            AuthorizationMaterialGenerationService,
        )

        mock_case = MagicMock()
        mock_client = MagicMock()
        mock_doc = MagicMock()
        svc = AuthorizationMaterialGenerationService(
            case_service=mock_case,
            client_service=mock_client,
            document_service=mock_doc,
        )
        assert svc.case_service is mock_case
        assert svc.client_service is mock_client
        assert svc.document_service is mock_doc
