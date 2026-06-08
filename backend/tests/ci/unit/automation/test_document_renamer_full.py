"""DocumentRenamer 全覆盖测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.document_renamer import DocumentRenamer


class TestDocumentRenamer:
    """DocumentRenamer 测试。"""

    def _make_renamer(self) -> DocumentRenamer:
        renamer = DocumentRenamer.__new__(DocumentRenamer)
        renamer.title_extraction_limit = 50
        return renamer

    # ─── __init__ with ollama params ───

    @patch("apps.automation.services.sms.document_renamer.get_config", return_value=50)
    def test_init_with_ollama_params(self, mock_cfg: MagicMock) -> None:
        r = DocumentRenamer(ollama_model="llama3", ollama_base_url="http://localhost")
        assert r.title_extraction_limit == 50

    @patch("apps.automation.services.sms.document_renamer.get_config", return_value=50)
    def test_init_no_params(self, mock_cfg: MagicMock) -> None:
        r = DocumentRenamer()
        assert r.title_extraction_limit == 50

    # ─── _get_title_extraction_limit ───

    @patch("apps.automation.services.sms.document_renamer.get_config", return_value="100")
    def test_get_limit_valid(self, mock_cfg: MagicMock) -> None:
        r = DocumentRenamer.__new__(DocumentRenamer)
        assert r._get_title_extraction_limit() == 100

    @patch("apps.automation.services.sms.document_renamer.get_config", return_value="invalid")
    def test_get_limit_invalid(self, mock_cfg: MagicMock) -> None:
        r = DocumentRenamer.__new__(DocumentRenamer)
        assert r._get_title_extraction_limit() == 50

    @patch("apps.automation.services.sms.document_renamer.get_config", return_value="5")
    def test_get_limit_too_small(self, mock_cfg: MagicMock) -> None:
        r = DocumentRenamer.__new__(DocumentRenamer)
        assert r._get_title_extraction_limit() == 20

    @patch("apps.automation.services.sms.document_renamer.get_config", return_value="99999")
    def test_get_limit_too_large(self, mock_cfg: MagicMock) -> None:
        r = DocumentRenamer.__new__(DocumentRenamer)
        assert r._get_title_extraction_limit() == 5000

    # ─── _normalize_title_candidate ───

    def test_normalize_empty(self) -> None:
        r = self._make_renamer()
        assert r._normalize_title_candidate("") == ""

    def test_normalize_with_quotes(self) -> None:
        r = self._make_renamer()
        result = r._normalize_title_candidate('"判决书"')
        assert result == "判决书"

    def test_normalize_with_underscore_prefix(self) -> None:
        r = self._make_renamer()
        result = r._normalize_title_candidate("prefix_判决书")
        assert result == "判决书"

    def test_normalize_with_parentheses(self) -> None:
        r = self._make_renamer()
        result = r._normalize_title_candidate("判决书（补正）")
        assert result == "判决书"

    def test_normalize_with_pdf_ext(self) -> None:
        r = self._make_renamer()
        result = r._normalize_title_candidate("判决书.pdf")
        assert result == "判决书"

    def test_normalize_with_court_prefix(self) -> None:
        r = self._make_renamer()
        result = r._normalize_title_candidate("广州市天河区人民法院民事判决书")
        assert result == "民事判决书"

    def test_normalize_with_download_prefix(self) -> None:
        r = self._make_renamer()
        result = r._normalize_title_candidate("下载判决书")
        assert result == "判决书"

    def test_normalize_with_copy_suffix(self) -> None:
        r = self._make_renamer()
        result = r._normalize_title_candidate("判决书副本")
        assert result == "判决书"

    # ─── _match_title_from_text ───

    def test_match_title_known_title(self) -> None:
        r = self._make_renamer()
        result = r._match_title_from_text("广州市天河区人民法院民事判决书")
        assert result == "民事判决书"

    def test_match_title_longest_match(self) -> None:
        r = self._make_renamer()
        # "裁判文书生效证明" is longer than "调解书"
        result = r._match_title_from_text("裁判文书生效证明")
        assert result == "裁判文书生效证明"

    def test_match_title_pattern_match(self) -> None:
        r = self._make_renamer()
        result = r._match_title_from_text("某某诉讼通知书")
        assert "通知书" in result

    def test_match_title_no_match(self) -> None:
        r = self._make_renamer()
        result = r._match_title_from_text("这是普通的文本内容")
        assert result is None

    def test_match_title_empty_normalized(self) -> None:
        r = self._make_renamer()
        result = r._match_title_from_text("   ")
        assert result is None

    # ─── _extract_title_from_text ───

    def test_extract_title_from_text(self) -> None:
        r = self._make_renamer()
        result = r._extract_title_from_text("民事判决书正文内容")
        assert result == "民事判决书"

    # ─── _extract_title_from_filename ───

    def test_extract_title_from_filename_known(self) -> None:
        r = self._make_renamer()
        result = r._extract_title_from_filename("/tmp/判决书.pdf")
        assert result == "判决书"

    def test_extract_title_from_filename_unknown(self) -> None:
        r = self._make_renamer()
        result = r._extract_title_from_filename("/tmp/some_document.pdf")
        assert result == "some_document"

    def test_extract_title_from_filename_empty_stem(self) -> None:
        r = self._make_renamer()
        # Use a path where the stem has no meaningful content after normalization
        result = r._extract_title_from_filename("/tmp/   .pdf")
        assert result == "司法文书"

    # ─── generate_filename ───

    @patch("apps.automation.services.sms.document_renamer.get_config")
    @patch("apps.automation.services.sms.document_renamer.FilenameTemplateService")
    def test_generate_filename_normal(self, mock_fts: MagicMock, mock_cfg: MagicMock) -> None:
        r = self._make_renamer()
        mock_cfg.side_effect = lambda k, d: d  # Return defaults
        mock_fts.render_court_doc.return_value = "判决书（测试案件）_20250601收"
        result = r.generate_filename("判决书", "测试案件", date(2025, 6, 1))
        assert result.endswith(".pdf")

    @patch("apps.automation.services.sms.document_renamer.get_config")
    @patch("apps.automation.services.sms.document_renamer.FilenameTemplateService")
    def test_generate_filename_empty_title(self, mock_fts: MagicMock, mock_cfg: MagicMock) -> None:
        r = self._make_renamer()
        mock_cfg.side_effect = lambda k, d: d
        mock_fts.render_court_doc.return_value = "司法文书（未知案件）_20250601收"
        result = r.generate_filename("", "", date(2025, 6, 1))
        assert "司法文书" in result

    @patch("apps.automation.services.sms.document_renamer.get_config")
    @patch("apps.automation.services.sms.document_renamer.FilenameTemplateService")
    def test_generate_filename_long_case_name(self, mock_fts: MagicMock, mock_cfg: MagicMock) -> None:
        r = self._make_renamer()
        mock_cfg.side_effect = lambda k, d: d
        mock_fts.render_court_doc.return_value = "title"
        long_name = "测试案件名称" * 20  # > 60 chars
        result = r.generate_filename("title", long_name, date(2025, 6, 1))
        assert result.endswith(".pdf")

    # ─── _sanitize_filename_part ───

    def test_sanitize_empty(self) -> None:
        r = self._make_renamer()
        assert r._sanitize_filename_part("") == ""

    def test_sanitize_none(self) -> None:
        r = self._make_renamer()
        assert r._sanitize_filename_part(None) == ""

    def test_sanitize_special_chars(self) -> None:
        r = self._make_renamer()
        result = r._sanitize_filename_part('test<>:"|?*\\file')
        assert result == "testfile"

    def test_sanitize_parentheses(self) -> None:
        r = self._make_renamer()
        result = r._sanitize_filename_part("test(abc)def")
        assert result == "testabcdef"

    def test_sanitize_control_chars(self) -> None:
        r = self._make_renamer()
        result = r._sanitize_filename_part("test\x00\x01file")
        assert result == "testfile"

    def test_sanitize_leading_trailing_spaces_dots(self) -> None:
        r = self._make_renamer()
        result = r._sanitize_filename_part(" . file . ")
        assert result == "file"

    # ─── extract_document_title ───

    def test_extract_document_title_file_not_exists(self) -> None:
        r = self._make_renamer()
        from apps.core.exceptions import ValidationException
        import pytest
        with pytest.raises(ValidationException):
            r.extract_document_title("/nonexistent/file.pdf")

    @patch("apps.automation.services.sms.document_renamer.extract_document_content")
    def test_extract_document_title_empty_content(self, mock_extract: MagicMock) -> None:
        r = self._make_renamer()
        mock_extract.return_value = MagicMock(text="")
        with patch("pathlib.Path.exists", return_value=True):
            result = r.extract_document_title("/tmp/doc.pdf")
            assert result == "doc"

    @patch("apps.automation.services.sms.document_renamer.extract_document_content")
    def test_extract_document_title_success(self, mock_extract: MagicMock) -> None:
        r = self._make_renamer()
        mock_extract.return_value = MagicMock(text="广州市天河区人民法院民事判决书")
        with patch("pathlib.Path.exists", return_value=True):
            result = r.extract_document_title("/tmp/doc.pdf")
            assert result == "民事判决书"

    @patch("apps.automation.services.sms.document_renamer.extract_document_content")
    def test_extract_document_title_no_title_found(self, mock_extract: MagicMock) -> None:
        r = self._make_renamer()
        mock_extract.return_value = MagicMock(text="普通文本内容没有标题")
        with patch("pathlib.Path.exists", return_value=True):
            result = r.extract_document_title("/tmp/unknown.pdf")
            assert result == "unknown"

    @patch("apps.automation.services.sms.document_renamer.extract_document_content")
    def test_extract_document_title_exception(self, mock_extract: MagicMock) -> None:
        r = self._make_renamer()
        mock_extract.side_effect = RuntimeError("extract failed")
        import pytest
        with patch("pathlib.Path.exists", return_value=True):
            with pytest.raises(RuntimeError):
                r.extract_document_title("/tmp/doc.pdf")

    # ─── rename ───

    def test_rename_file_not_exists(self) -> None:
        r = self._make_renamer()
        from apps.core.exceptions import ValidationException
        import pytest
        with pytest.raises(ValidationException):
            r.rename("/nonexistent/file.pdf", "case", date(2025, 6, 1))

    # ─── rename_with_fallback ───

    def test_rename_with_fallback_success(self) -> None:
        r = self._make_renamer()
        with patch.object(r, "rename", return_value="/tmp/renamed.pdf"):
            result = r.rename_with_fallback("/tmp/doc.pdf", "case", date(2025, 6, 1))
            assert result == "/tmp/renamed.pdf"

    @patch("apps.automation.services.sms.document_renamer.FilenameTemplateService")
    @patch("apps.automation.services.sms.document_renamer.get_config")
    def test_rename_with_fallback_fallback_path(self, mock_cfg: MagicMock, mock_fts: MagicMock) -> None:
        r = self._make_renamer()
        mock_cfg.side_effect = lambda k, d: d
        mock_fts.render_court_doc.return_value = "fallback_name"
        mock_fts.get_unique_filepath.return_value = (Path("/tmp/fallback.pdf"), Path("/tmp/fallback.pdf"))

        with patch.object(r, "rename", side_effect=RuntimeError("rename failed")), \
             patch("pathlib.Path.rename"):
            result = r.rename_with_fallback("/tmp/doc.pdf", "case", date(2025, 6, 1), original_name="original.pdf")
            assert "/tmp" in result

    @patch("apps.automation.services.sms.document_renamer.FilenameTemplateService")
    @patch("apps.automation.services.sms.document_renamer.get_config")
    def test_rename_with_fallback_no_original_name(self, mock_cfg: MagicMock, mock_fts: MagicMock) -> None:
        r = self._make_renamer()
        mock_cfg.side_effect = lambda k, d: d
        mock_fts.render_court_doc.return_value = "fallback"
        mock_fts.get_unique_filepath.return_value = (Path("/tmp/f.pdf"), Path("/tmp/f.pdf"))

        with patch.object(r, "rename", side_effect=RuntimeError("fail")), \
             patch("pathlib.Path.rename"):
            result = r.rename_with_fallback("/tmp/doc.pdf", "case", date(2025, 6, 1))
            assert "/tmp" in result

    @patch("apps.automation.services.sms.document_renamer.FilenameTemplateService")
    @patch("apps.automation.services.sms.document_renamer.get_config")
    def test_rename_with_fallback_also_fails(self, mock_cfg: MagicMock, mock_fts: MagicMock) -> None:
        r = self._make_renamer()
        mock_cfg.side_effect = lambda k, d: d
        mock_fts.get_unique_filepath.side_effect = RuntimeError("fail2")

        with patch.object(r, "rename", side_effect=RuntimeError("fail1")):
            result = r.rename_with_fallback("/tmp/doc.pdf", "case", date(2025, 6, 1))
            assert result == "/tmp/doc.pdf"
