"""Extended tests for pdf_splitting services - template_registry, job_service validation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.pdf_splitting.services.template_registry import (
    TemplateDefinition,
    SegmentTemplateRule,
    get_template_definition,
    get_segment_label,
    get_default_filename,
    FILING_MATERIALS_V1,
)


class TestTemplateRegistry:
    def test_get_template_definition_known(self):
        template = get_template_definition("filing_materials_v1")
        assert template.key == "filing_materials_v1"
        assert template.version == "1"

    def test_get_template_definition_unknown_returns_default(self):
        template = get_template_definition("unknown_key")
        assert template == FILING_MATERIALS_V1

    def test_get_segment_label_known(self):
        from apps.pdf_splitting.models import PdfSplitSegmentType

        label = get_segment_label(PdfSplitSegmentType.COMPLAINT)
        assert label == "起诉状"

    def test_get_segment_label_evidence_list(self):
        from apps.pdf_splitting.models import PdfSplitSegmentType

        label = get_segment_label(PdfSplitSegmentType.EVIDENCE_LIST)
        assert label == "证据清单及明细"

    def test_get_segment_label_unrecognized(self):
        from apps.pdf_splitting.models import PdfSplitSegmentType

        label = get_segment_label(PdfSplitSegmentType.UNRECOGNIZED)
        assert label == "未识别材料"

    def test_get_segment_label_unknown(self):
        label = get_segment_label("unknown_type")
        assert label == "unknown_type"

    def test_get_default_filename_known(self):
        from apps.pdf_splitting.models import PdfSplitSegmentType

        filename = get_default_filename(PdfSplitSegmentType.COMPLAINT)
        assert filename == "起诉状"

    def test_get_default_filename_unknown(self):
        filename = get_default_filename("unknown_type")
        assert filename == "未识别材料"

    def test_filing_materials_v1_rules(self):
        assert len(FILING_MATERIALS_V1.rules) > 0
        rule = FILING_MATERIALS_V1.rules[0]
        assert rule.segment_type is not None
        assert rule.label
        assert rule.default_filename
        assert len(rule.strong_keywords) > 0

    def test_segment_template_rule_defaults(self):
        rule = SegmentTemplateRule(
            segment_type="test",
            label="Test",
            default_filename="test.pdf",
            strong_keywords=("keyword",),
        )
        assert rule.weak_keywords == ()
        assert rule.negative_keywords == ()
        assert rule.continuation_keywords == ()

    def test_template_definition_is_frozen(self):
        with pytest.raises(AttributeError):
            FILING_MATERIALS_V1.key = "modified"  # type: ignore[misc]


class TestPdfSplitJobServiceValidation:
    def test_normalize_split_mode_valid(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        assert service._normalize_split_mode("content_analysis") == "content_analysis"

    def test_normalize_split_mode_invalid(self):
        from apps.pdf_splitting.models import PdfSplitMode
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        assert service._normalize_split_mode("invalid") == PdfSplitMode.CONTENT_ANALYSIS

    def test_normalize_split_mode_none(self):
        from apps.pdf_splitting.models import PdfSplitMode
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        assert service._normalize_split_mode(None) == PdfSplitMode.CONTENT_ANALYSIS

    def test_normalize_ocr_profile_valid(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        assert service._normalize_ocr_profile("balanced") == "balanced"

    def test_normalize_ocr_profile_invalid(self):
        from apps.pdf_splitting.models import PdfSplitOcrProfile
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        assert service._normalize_ocr_profile("invalid") == PdfSplitOcrProfile.BALANCED

    def test_is_absolute_path_unix(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        assert service._is_absolute_path("/tmp/test.pdf") is True

    def test_is_absolute_path_relative(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        assert service._is_absolute_path("relative/path.pdf") is False

    def test_is_absolute_path_windows(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        assert service._is_absolute_path("C:\\Users\\test.pdf") is True

    def test_validate_local_pdf_path_empty(self):
        from apps.core.exceptions import ValidationException
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        with pytest.raises(ValidationException, match="source_path 不能为空"):
            service._validate_local_pdf_path("")

    def test_validate_local_pdf_path_smb(self):
        from apps.core.exceptions import ValidationException
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        with pytest.raises(ValidationException, match="不支持 smb"):
            service._validate_local_pdf_path("smb://server/share/file.pdf")

    def test_validate_local_pdf_path_relative(self):
        from apps.core.exceptions import ValidationException
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        with pytest.raises(ValidationException, match="必须为绝对路径"):
            service._validate_local_pdf_path("relative/path.pdf")

    def test_save_uploaded_pdf_non_pdf(self):
        from apps.core.exceptions import ValidationException
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        mock_file = MagicMock()
        mock_file.name = "test.txt"
        with pytest.raises(ValidationException, match="仅支持 PDF"):
            service._save_uploaded_pdf(mock_file, MagicMock())

    def test_save_uploaded_pdf_empty(self):
        from apps.core.exceptions import ValidationException
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.size = 0
        with pytest.raises(ValidationException, match="上传文件为空"):
            service._save_uploaded_pdf(mock_file, MagicMock())

    def test_normalize_confirmed_segments_empty(self):
        from apps.core.exceptions import ValidationException
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        with pytest.raises(ValidationException, match="至少保留一个片段"):
            service._normalize_confirmed_segments(items=[], total_pages=10)

    def test_normalize_confirmed_segments_invalid_page(self):
        from apps.core.exceptions import ValidationException
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        with pytest.raises(ValidationException, match="页码必须为整数"):
            service._normalize_confirmed_segments(
                items=[{"page_start": "abc", "page_end": 5}],
                total_pages=10,
            )

    def test_normalize_confirmed_segments_page_range_invalid(self):
        from apps.core.exceptions import ValidationException
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        service = PdfSplitJobService()
        with pytest.raises(ValidationException, match="片段页码非法"):
            service._normalize_confirmed_segments(
                items=[{"page_start": 5, "page_end": 3}],
                total_pages=10,
            )
