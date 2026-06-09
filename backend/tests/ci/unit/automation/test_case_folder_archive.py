"""CaseFolderArchiveService 全覆盖测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.case_folder_archive_service import CaseFolderArchiveService


class TestCaseFolderArchiveService:
    """CaseFolderArchiveService 测试。"""

    def _make_service(self) -> CaseFolderArchiveService:
        return CaseFolderArchiveService()

    def _make_sms(self, case_id: int = 1, content: str = "测试短信",
                  sms_type: str = "notice", received_at=None) -> SimpleNamespace:
        from datetime import datetime
        return SimpleNamespace(
            id=100,
            case_id=case_id,
            case=SimpleNamespace(name="测试案件"),
            content=content,
            sms_type=sms_type,
            received_at=received_at or datetime(2025, 6, 1, 10, 0, 0),
            get_sms_type_display=lambda: "通知短信",
        )

    # ─── archive_sms_documents ───

    def test_archive_no_case_id(self) -> None:
        svc = self._make_service()
        sms = self._make_sms(case_id=None)
        assert svc.archive_sms_documents(sms, []) is False

    def test_archive_no_renamed_paths(self) -> None:
        svc = self._make_service()
        sms = self._make_sms()
        assert svc.archive_sms_documents(sms, []) is False

    def test_archive_no_bound_folder(self) -> None:
        svc = self._make_service()
        sms = self._make_sms()
        with patch.object(svc, "_get_bound_case_root", return_value=None):
            assert svc.archive_sms_documents(sms, ["/tmp/doc.pdf"]) is False

    def test_archive_success(self) -> None:
        svc = self._make_service()
        sms = self._make_sms()
        with tempfile.TemporaryDirectory() as tmpdir:
            case_root = Path(tmpdir) / "case_root"
            case_root.mkdir()

            with patch.object(svc, "_get_bound_case_root", return_value=case_root), \
                 patch.object(svc, "_copy_documents", return_value=1):
                result = svc.archive_sms_documents(sms, ["/tmp/doc.pdf"])
                assert result is True

    # ─── _get_bound_case_root ───

    @patch("apps.automation.services.sms.case_folder_archive_service.CaseFolderBinding")
    def test_get_bound_no_binding(self, MockBinding: MagicMock) -> None:
        svc = self._make_service()
        MockBinding.objects.filter.return_value.first.return_value = None
        assert svc._get_bound_case_root(1) is None

    @patch("apps.automation.services.sms.case_folder_archive_service.CaseFolderBinding")
    def test_get_bound_no_resolved_path(self, MockBinding: MagicMock) -> None:
        svc = self._make_service()
        binding = MagicMock()
        binding.resolved_folder_path = ""
        MockBinding.objects.filter.return_value.first.return_value = binding
        assert svc._get_bound_case_root(1) is None

    @patch("apps.automation.services.sms.case_folder_archive_service.CaseFolderBinding")
    def test_get_bound_dir_not_exists(self, MockBinding: MagicMock) -> None:
        svc = self._make_service()
        binding = MagicMock()
        binding.resolved_folder_path = "/nonexistent/path"
        MockBinding.objects.filter.return_value.first.return_value = binding
        assert svc._get_bound_case_root(1) is None

    @patch("apps.automation.services.sms.case_folder_archive_service.CaseFolderBinding")
    def test_get_bound_success(self, MockBinding: MagicMock) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            binding = MagicMock()
            binding.resolved_folder_path = tmpdir
            MockBinding.objects.filter.return_value.first.return_value = binding
            result = svc._get_bound_case_root(1)
            assert result == Path(tmpdir)

    # ─── _find_mail_folder ───

    def test_find_mail_folder_exact_match(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "1-邮件往来").mkdir()
            result = svc._find_mail_folder(root)
            assert result is not None
            assert result.name == "1-邮件往来"

    def test_find_mail_folder_no_match(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "1-其他").mkdir()
            result = svc._find_mail_folder(root)
            assert result is None

    def test_find_mail_folder_nested_match(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "1-子目录" / "邮件"
            nested.mkdir(parents=True)
            result = svc._find_mail_folder(root)
            assert result is not None
            assert "邮件" in result.name

    # ─── _mail_keyword_score ───

    def test_mail_keyword_score_exact(self) -> None:
        svc = self._make_service()
        assert svc._mail_keyword_score("邮件往来") == 120

    def test_mail_keyword_score_contains(self) -> None:
        svc = self._make_service()
        assert svc._mail_keyword_score("1-邮件往来") == 100

    def test_mail_keyword_score_mailing(self) -> None:
        svc = self._make_service()
        assert svc._mail_keyword_score("邮寄材料") == 80

    def test_mail_keyword_score_email(self) -> None:
        svc = self._make_service()
        assert svc._mail_keyword_score("邮件通知") == 60

    def test_mail_keyword_score_no_match(self) -> None:
        svc = self._make_service()
        assert svc._mail_keyword_score("其他") == 0

    # ─── _extract_leading_number ───

    def test_extract_leading_number_normal(self) -> None:
        svc = self._make_service()
        assert svc._extract_leading_number("5-邮件往来") == 5

    def test_extract_leading_number_no_number(self) -> None:
        svc = self._make_service()
        assert svc._extract_leading_number("邮件往来") == 0

    def test_extract_leading_number_with_space(self) -> None:
        svc = self._make_service()
        assert svc._extract_leading_number(" 3-邮寄") == 3

    # ─── _create_mail_folder ───

    def test_create_mail_folder(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "1-其他").mkdir()
            (root / "3-案件材料").mkdir()
            result = svc._create_mail_folder(root)
            assert result.exists()
            assert "4-邮件往来" in result.name

    # ─── _build_event_folder_name ───

    def test_build_event_folder_name(self) -> None:
        svc = self._make_service()
        sms = self._make_sms(content="收到判决书")
        name = svc._build_event_folder_name(sms, [])
        assert "2025.06.01" in name
        assert "收到法院判决书" in name

    # ─── _build_event_summary ───

    def test_build_event_summary_from_sms_content(self) -> None:
        svc = self._make_service()
        sms = self._make_sms(content="收到立案通知")
        summary = svc._build_event_summary(sms, [])
        assert summary == "收到法院立案材料"

    def test_build_event_summary_from_filename(self) -> None:
        svc = self._make_service()
        sms = self._make_sms(content="")
        summary = svc._build_event_summary(sms, ["/tmp/判决书_张三.pdf"])
        assert "判决书" in summary

    def test_build_event_summary_default(self) -> None:
        svc = self._make_service()
        sms = self._make_sms(content="")
        summary = svc._build_event_summary(sms, [])
        assert summary == "收到材料"

    # ─── _extract_title_from_filename ───

    def test_extract_title_normal(self) -> None:
        svc = self._make_service()
        assert svc._extract_title_from_filename("/tmp/判决书.pdf") == "判决书"

    def test_extract_title_with_parenthesis(self) -> None:
        svc = self._make_service()
        assert svc._extract_title_from_filename("/tmp/裁定书（补正）.pdf") == "裁定书"

    def test_extract_title_with_underscore(self) -> None:
        svc = self._make_service()
        assert svc._extract_title_from_filename("/tmp/传票_张三.pdf") == "传票"

    # ─── _infer_summary ───

    def test_infer_summary_empty(self) -> None:
        svc = self._make_service()
        assert svc._infer_summary("") == (0, "")

    def test_infer_summary_filing(self) -> None:
        svc = self._make_service()
        assert svc._infer_summary("立案通知书") == (100, "收到法院立案材料")

    def test_infer_summary_fees(self) -> None:
        svc = self._make_service()
        assert svc._infer_summary("诉讼费用缴纳通知") == (90, "收到诉讼费材料")

    def test_infer_summary_judgment(self) -> None:
        svc = self._make_service()
        assert svc._infer_summary("民事判决书") == (85, "收到法院判决书")

    def test_infer_summary_ruling(self) -> None:
        svc = self._make_service()
        assert svc._infer_summary("裁定书") == (85, "收到法院裁定书")

    def test_infer_summary_mediation(self) -> None:
        svc = self._make_service()
        assert svc._infer_summary("调解书") == (80, "收到法院调解书")

    def test_infer_summary_summons(self) -> None:
        svc = self._make_service()
        assert svc._infer_summary("传票") == (75, "收到开庭传票")

    def test_infer_summary_notice(self) -> None:
        svc = self._make_service()
        assert svc._infer_summary("通知书") == (60, "收到法院通知")

    def test_infer_summary_starts_with_received(self) -> None:
        svc = self._make_service()
        priority, summary = svc._infer_summary("收到其他材料")
        assert priority == 20

    def test_infer_summary_generic(self) -> None:
        svc = self._make_service()
        priority, summary = svc._infer_summary("其他材料")
        assert priority == 20
        assert "收到" in summary

    # ─── _sanitize_folder_name ───

    def test_sanitize_folder_name_special_chars(self) -> None:
        svc = self._make_service()
        result = svc._sanitize_folder_name('test<>:"/\\|?*file')
        assert result == "testfile"

    def test_sanitize_folder_name_empty(self) -> None:
        svc = self._make_service()
        assert svc._sanitize_folder_name("") == "收到材料"

    def test_sanitize_folder_name_whitespace(self) -> None:
        svc = self._make_service()
        assert svc._sanitize_folder_name("  hello  ") == "hello"

    def test_sanitize_folder_name_long(self) -> None:
        svc = self._make_service()
        result = svc._sanitize_folder_name("a" * 50)
        assert len(result) <= 30

    # ─── _ensure_unique_directory ───

    def test_ensure_unique_directory_no_conflict(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            result = svc._ensure_unique_directory(parent, "test_folder")
            assert result.name == "test_folder"

    def test_ensure_unique_directory_conflict(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            (parent / "test_folder").mkdir()
            (parent / "test_folder_2").mkdir()
            result = svc._ensure_unique_directory(parent, "test_folder")
            assert result.name == "test_folder_3"

    # ─── _write_sms_markdown ───

    def test_write_sms_markdown(self) -> None:
        svc = self._make_service()
        sms = self._make_sms(content="测试短信内容")
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_folder = Path(tmpdir)
            md_path = svc._write_sms_markdown(archive_folder, sms, ["/tmp/doc1.pdf", "/tmp/doc2.pdf"])
            assert md_path.exists()
            content = md_path.read_text(encoding="utf-8")
            assert "法院短信记录" in content
            assert "测试短信内容" in content
            assert "doc1.pdf" in content
            assert "doc2.pdf" in content

    # ─── _copy_documents ───

    def test_copy_documents_success(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_folder = Path(tmpdir) / "archive"
            archive_folder.mkdir()
            # Create a source file
            src = Path(tmpdir) / "test.pdf"
            src.write_bytes(b"pdf content")
            count = svc._copy_documents(archive_folder, [str(src)])
            assert count == 1
            assert (archive_folder / "test.pdf").exists()

    def test_copy_documents_missing_file(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_folder = Path(tmpdir) / "archive"
            archive_folder.mkdir()
            count = svc._copy_documents(archive_folder, ["/nonexistent/file.pdf"])
            assert count == 0

    # ─── _ensure_unique_file_path ───

    def test_ensure_unique_file_path_no_conflict(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "file.pdf"
            result = svc._ensure_unique_file_path(target)
            assert result == target

    def test_ensure_unique_file_path_conflict(self) -> None:
        svc = self._make_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "file.pdf"
            target.write_bytes(b"first")
            result = svc._ensure_unique_file_path(target)
            assert result.name == "file_2.pdf"
