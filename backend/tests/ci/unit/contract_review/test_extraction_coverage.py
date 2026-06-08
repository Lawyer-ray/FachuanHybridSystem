"""Coverage tests for contract_review.services.extraction.title_extractor, content_extractor, party_identifier, contract_review.tasks."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestTitleExtractor:
    def test_generate_output_filename(self):
        from apps.contract_review.services.extraction.title_extractor import TitleExtractor
        filename = TitleExtractor.generate_output_filename("买卖合同", version=2, task_id="abc12345xyz")
        assert "买卖合同" in filename
        assert "V2" in filename
        assert filename.endswith(".docx")

    def test_generate_output_filename_empty_title(self):
        from apps.contract_review.services.extraction.title_extractor import TitleExtractor
        filename = TitleExtractor.generate_output_filename("")
        assert "合同" in filename

    def test_generate_output_filename_special_chars(self):
        from apps.contract_review.services.extraction.title_extractor import TitleExtractor
        filename = TitleExtractor.generate_output_filename('Test: File/Name?*"<>|')
        assert "/" not in filename
        assert "?" not in filename

    def test_parse_title_from_filename(self):
        from apps.contract_review.services.extraction.title_extractor import TitleExtractor
        title = TitleExtractor.parse_title_from_filename("买卖合同[修订版]V1_20240101.docx")
        assert title == "买卖合同"

    def test_parse_title_no_match(self):
        from apps.contract_review.services.extraction.title_extractor import TitleExtractor
        title = TitleExtractor.parse_title_from_filename("random_file.docx")
        assert title == ""

    def test_extract_title_from_doc(self):
        from apps.contract_review.services.extraction.title_extractor import TitleExtractor
        extractor = TitleExtractor()
        mock_doc = MagicMock()
        para1 = MagicMock()
        para1.text = "  "
        para2 = MagicMock()
        para2.text = "房屋买卖合同"
        mock_doc.paragraphs = [para1, para2]
        result = extractor.extract_title(mock_doc)
        assert result == "房屋买卖合同"


class TestPartyIdentifier:
    def test_identify_parties_abbrev_format(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier
        identifier = PartyIdentifier()
        paragraphs = ["甲方：张三公司（以下简称甲方）", "乙方：李四公司（以下简称乙方）"]
        result = identifier.identify_parties(paragraphs)
        assert "party_a" in result
        assert "party_b" in result

    def test_identify_parties_empty(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier
        identifier = PartyIdentifier()
        result = identifier.identify_parties(["没有当事人的文本"])
        assert isinstance(result, dict)

    def test_find_party_static(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier
        import re
        patterns = [re.compile(r"甲\s*方[：:]\s*(.+?)(?:\s*$|[\s（(])")]
        result = PartyIdentifier._find_party("甲方：张三公司", patterns)
        assert "张三公司" in result

    def test_find_party_no_match(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier
        import re
        patterns = [re.compile(r"甲\s*方[：:]\s*(.+?)(?:\s*$|[\s（(])")]
        result = PartyIdentifier._find_party("无匹配文本", patterns)
        assert result == ""


class TestContractReviewTasks:
    @patch("apps.contract_review.tasks.ReviewTask")
    @patch("apps.contract_review.tasks.timezone")
    def test_cleanup_old_files_no_tasks(self, mock_tz, mock_model):
        from apps.contract_review.tasks import cleanup_old_files
        mock_tz.now.return_value = MagicMock()
        mock_model.objects.filter.return_value.exclude.return_value = []
        result = cleanup_old_files(days=30)
        assert "upload_files" in result
        assert "output_files" in result
        assert "tasks" in result
